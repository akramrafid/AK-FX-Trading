"""
Tests for the 1-minute Buy Scenarios 1-2 (BUY_STRATEGY_PROMPT.md §12) and for sell + buy together.

Fixtures are USDCAD prices with spread 0, ENTRY_FILL = signal_close and default parameters
unless a test says otherwise:
- HTF fixtures (15m): HX + HY_eq -> EQUAL_LOW, HX + HY_sw -> SWEEP_LOW, HX + HY_none -> nothing.
- Positive cases B1-B9, negative cases N1-N12, exit cases E1-E3, fills and setup rules.
- No look-ahead: a streaming replay equals the batch run, and changing candles after
  time T leaves every decision before T unchanged.
- ak_scenarios: no hedging, the same-bar conflict, and a sell-only run equal to run_sell_backtest.
- Live bridge: TP from the live ask, no order when the bid is at or below the SL, and the daily
  loss limit and spread ceiling read from the account snapshot the EA writes.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridge.day_start import DayStartBalances
from bridge.dwx_client import DWXClient, account_spread_pips, open_positions_by_side
from bridge.executor import BridgeExecutor, BridgeOrderRecord, build_ak_scenarios_engine, build_buy_scenario_engine
from config import AppConfig
from database.sqlite_manager import TradingDatabase
from engine.ak_scenarios import HEDGE_BLOCK, SAME_BAR_CONFLICT, AkScenariosEngine, no_hedging_params
from engine.buy_scenarios import (
    BuyHtfPattern,
    BuyScenarioEngine,
    BuyScenarioParams,
    BuySkipReason,
    bottom_pattern,
    candle_kind_pct,
)
from engine.models import Candle, Direction, TradeSignal
from engine.scenarios_backtest import BUY_JOURNAL_COLUMNS, BacktestSettings, journal_rows, run_scenarios_backtest
from engine.sell_scenarios import HTF_DELTAS, M1, CandleKind, PointCandle, SellScenarioEngine, SellScenarioParams
from engine.sell_scenarios_backtest import run_sell_backtest
from risk.guardrails import RiskGuardrails
from risk.models import DailyPnLTracker, RiskLimits
from test_sell_scenarios import synthetic_history

UTC = timezone.utc
DAY = datetime(2026, 10, 15, tzinfo=UTC)  # a Thursday, inside the 07:00-21:00 UTC session

# HTF fixtures (15m): open, high, low, close
HX = (1.40100, 1.40110, 1.40050, 1.40060)
HY_EQ = (1.40060, 1.40120, 1.40050, 1.40110)
HY_SW = (1.40060, 1.40120, 1.40035, 1.40110)
HY_NONE = (1.40060, 1.40120, 1.40052, 1.40110)

# 1m fixtures
FIX = {
    "P1": (1.40110, 1.40112, 1.40085, 1.40090),
    "P2": (1.40090, 1.40093, 1.40060, 1.40065),
    "P": (1.40070, 1.40072, 1.40040, 1.40045),
    "R1_eq": (1.40045, 1.40060, 1.40040, 1.40055),
    "R1_sw": (1.40045, 1.40060, 1.40033, 1.40055),
    "R1_miss": (1.40045, 1.40060, 1.40041, 1.40055),
    "D1": (1.40048, 1.40060, 1.40040, 1.40048),
    "D1_hi": (1.40050, 1.40056, 1.40045, 1.40050),
    "R2": (1.40055, 1.40070, 1.40050, 1.40065),
    "R2_low": (1.40055, 1.40070, 1.40035, 1.40065),
    "Dm": (1.40055, 1.40062, 1.40050, 1.40055),
    "Dx": (1.40050, 1.40056, 1.40044, 1.40050),
    "R3": (1.40065, 1.40080, 1.40060, 1.40075),
    "D3": (1.40065, 1.40072, 1.40058, 1.40065),
    "D5": (1.40055, 1.40065, 1.40045, 1.40056),
    "D10": (1.40055, 1.40065, 1.40045, 1.40057),
}
B1_SEQ = ("P", "R1_eq", "R2", "R3")


def at(hour: int, minute: int) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


def bars(start: datetime, *ohlcs: tuple) -> list:
    """Adjacent 1m candles starting at `start`."""
    return [Candle(start + i * M1, *ohlc) for i, ohlc in enumerate(ohlcs)]


def quiet(close: float) -> tuple:
    """A small bar opening at `close` that touches neither the SL nor the TP of the fixtures."""
    return (close, round(close + 0.00003, 5), round(close - 0.00002, 5), round(close + 0.00001, 5))


def sequence(names, start=None, after=None) -> list:
    """The fixture candles from `start` (P at 10:30, or P1 at 10:28), then `after` (default: one quiet bar)."""
    start = start or (at(10, 28) if names[0] == "P1" else at(10, 30))
    after = [quiet(FIX[names[-1]][3])] if after is None else after
    return bars(start, *(FIX[n] for n in names), *after)


def htf(y=HY_EQ, x=HX, start=None) -> dict:
    """The 15m pair X, Y; X opens at `start` (default 10:00)."""
    start = start or at(10, 0)
    return {"M15": [Candle(start, *x), Candle(start + HTF_DELTAS["M15"], *y)], "M5": []}


def buy_engine(**params) -> AkScenariosEngine:
    return AkScenariosEngine(buy=BuyScenarioEngine(BuyScenarioParams(**params)))


def backtest(m1, htf_bars, settings=None, **params):
    return run_scenarios_backtest(m1, htf_bars, buy_engine(**params), settings or BacktestSettings())


def pc(ohlc: tuple) -> PointCandle:
    return PointCandle.of(Candle(at(10, 0), *ohlc), 0.00001)


def both_sides_engine(**buy_params) -> AkScenariosEngine:
    return AkScenariosEngine(
        sell=SellScenarioEngine(no_hedging_params(SellScenarioParams())),
        buy=BuyScenarioEngine(no_hedging_params(BuyScenarioParams(**buy_params))),
    )


def arm(engine, y=HY_EQ) -> None:
    engine.on_htf_candle(Candle(at(10, 0), *HX), "M15")
    engine.on_htf_candle(Candle(at(10, 15), *y), "M15")


class TestPrimitives(unittest.TestCase):
    """Spec §4.1 candle kind and §4.2 HTF pattern, on integer points."""

    def test_d5_is_a_doji_and_d10_bullish(self):
        self.assertIs(candle_kind_pct(pc(FIX["D5"]), 5.0), CandleKind.DOJI)
        self.assertIs(candle_kind_pct(pc(FIX["D10"]), 5.0), CandleKind.BULL)

    def test_hx_against_each_y(self):
        self.assertIs(bottom_pattern(pc(HX), pc(HY_EQ), 0), BuyHtfPattern.EQUAL_LOW)
        self.assertIs(bottom_pattern(pc(HX), pc(HY_SW), 0), BuyHtfPattern.SWEEP_LOW)
        self.assertIs(bottom_pattern(pc(HX), pc(HY_NONE), 0), BuyHtfPattern.NONE)

    def test_x_must_be_bearish_and_y_bullish(self):
        self.assertIs(bottom_pattern(pc(HY_EQ), pc(HY_EQ), 0), BuyHtfPattern.NONE)
        self.assertIs(bottom_pattern(pc(HX), pc(HX), 0), BuyHtfPattern.NONE)

    def test_body_bottoms_would_accept_a_pair_whose_lows_do_not_match(self):
        """Why EQUAL_LOW_MODE stays "low": Y opens at X's close, so body bottoms are almost always equal."""
        self.assertIs(bottom_pattern(pc(HX), pc(HY_NONE), 0, mode="body"), BuyHtfPattern.EQUAL_LOW)
        self.assertIs(bottom_pattern(pc(HX), pc(HY_NONE), 0, mode="either"), BuyHtfPattern.EQUAL_LOW)
        self.assertIs(bottom_pattern(pc(HX), pc(HY_NONE), 0, mode="low"), BuyHtfPattern.NONE)


class TestHtfFixtures(unittest.TestCase):
    """Spec §12 HTF fixtures and §6 arming."""

    def arm(self, y):
        engine = BuyScenarioEngine()
        self.assertIsNone(engine.on_htf_candle(Candle(at(10, 0), *HX), "M15"))
        return engine.on_htf_candle(Candle(at(10, 15), *y), "M15")

    def test_hx_hy_eq_is_equal_low_confirmed_10_30_expiring_11_15(self):
        setup = self.arm(HY_EQ)
        self.assertIs(setup.pattern, BuyHtfPattern.EQUAL_LOW)
        self.assertEqual((setup.t_conf, setup.t_exp), (at(10, 30), at(11, 15)))
        self.assertAlmostEqual(setup.setup_low, 1.40050, places=5)

    def test_hx_hy_sw_is_sweep_low_with_the_lower_low(self):
        setup = self.arm(HY_SW)
        self.assertIs(setup.pattern, BuyHtfPattern.SWEEP_LOW)
        self.assertAlmostEqual(setup.setup_low, 1.40035, places=5)

    def test_hx_hy_none_arms_nothing(self):
        self.assertIsNone(self.arm(HY_NONE))

    def test_htf_candles_must_be_adjacent(self):
        engine = BuyScenarioEngine()
        engine.on_htf_candle(Candle(at(9, 45), *HX), "M15")
        self.assertIsNone(engine.on_htf_candle(Candle(at(10, 15), *HY_EQ), "M15"))


class TestPositiveCases(unittest.TestCase):
    """Spec §12 B1-B9."""

    def assert_trade(self, result, scenario, signal_bar, entry, sl, tp, risk_pips=None, dojis=()):
        self.assertEqual(len(result.trades), 1, result.skips)
        trade = result.trades[0]
        self.assertEqual((trade.side, trade.scenario), ("BUY", scenario))
        self.assertEqual(trade.decision.run.signal.timestamp, signal_bar)
        self.assertEqual(trade.entry_time, signal_bar + M1)
        self.assertEqual(trade.decision.run.doji_positions, dojis)
        self.assertAlmostEqual(trade.entry_price, entry, places=5)
        self.assertAlmostEqual(trade.stop_loss, sl, places=5)
        self.assertAlmostEqual(trade.take_profit, tp, places=5)
        if risk_pips is not None:
            self.assertAlmostEqual(trade.risk_pips, risk_pips, places=6)
        return trade

    def test_b1_scenario_1(self):
        trade = self.assert_trade(backtest(sequence(B1_SEQ), htf(HY_EQ)), 1, at(10, 33), 1.40075, 1.40039, 1.40435, 3.6)
        self.assertEqual(trade.decision.ltf_type, "EQUAL")

    def test_b2_scenario_2(self):
        result = backtest(sequence(("P", "R1_sw", "R2", "R3")), htf(HY_SW))
        trade = self.assert_trade(result, 2, at(10, 33), 1.40075, 1.40032, 1.40505, 4.3)
        self.assertEqual(trade.decision.ltf_type, "SWEEP")

    def test_b3_doji_is_candle_1(self):
        trade = self.assert_trade(
            backtest(sequence(("P", "D1", "R2", "R3")), htf(HY_EQ)), 1, at(10, 33), 1.40075, 1.40039, 1.40435, dojis=(1,)
        )
        self.assertEqual(trade.decision.run.first.timestamp, at(10, 31))

    def test_b4_doji_in_position_2_signals_on_the_4th_bar(self):
        result = backtest(sequence(("P", "R1_eq", "Dm", "R2", "R3")), htf(HY_SW))
        self.assert_trade(result, 2, at(10, 34), 1.40075, 1.40039, 1.40435, dojis=(2,))

    def test_b5_doji_completes_the_run(self):
        result = backtest(sequence(("P", "R1_eq", "R2", "D3")), htf(HY_EQ))
        self.assert_trade(result, 1, at(10, 33), 1.40065, 1.40039, 1.40325, 2.6, dojis=(3,))

    def test_b6_doji_doji_bull(self):
        result = backtest(sequence(("P1", "P2", "P", "D1", "Dm", "R3")), htf(HY_EQ))
        trade = self.assert_trade(result, 1, at(10, 33), 1.40075, 1.40039, 1.40435, dojis=(1, 2))
        self.assertEqual(trade.decision.run.prior_members[0].candle.timestamp, at(10, 28))  # the prior run starts before t_conf

    def test_b7_bull_doji_doji(self):
        result = backtest(sequence(("P", "R1_eq", "Dm", "D3")), htf(HY_SW))
        self.assert_trade(result, 2, at(10, 33), 1.40065, 1.40039, 1.40325, dojis=(2, 3))

    def test_b8_doji_bull_doji(self):
        result = backtest(sequence(("P", "D1", "R2", "D3")), htf(HY_EQ))
        self.assert_trade(result, 1, at(10, 33), 1.40065, 1.40039, 1.40325, dojis=(1, 3))

    def test_b9_signal_bar_closing_at_t_exp_still_trades(self):
        result = backtest(sequence(B1_SEQ, start=at(11, 11)), htf(HY_EQ))
        self.assert_trade(result, 1, at(11, 14), 1.40075, 1.40039, 1.40435)


class TestNegativeCases(unittest.TestCase):
    """Spec §12 N1-N12."""

    def assert_no_trade(self, result, skip_reason=None):
        self.assertEqual(result.trades, ())
        if skip_reason is None:
            self.assertEqual(result.decisions, ())
        else:
            self.assertEqual([s.reason for s in result.skips], [skip_reason.value])

    def test_n1_no_htf_pattern(self):
        self.assert_no_trade(backtest(sequence(B1_SEQ), htf(HY_NONE)))

    def test_n2_one_tick_miss_of_the_prior_low(self):
        self.assert_no_trade(backtest(sequence(("P", "R1_miss", "R2", "R3")), htf(HY_EQ)))

    def test_n3_dojis_complete_a_one_candle_bearish_run(self):
        self.assert_no_trade(backtest(sequence(("P", "D1", "Dm", "R3")), htf(HY_EQ)))

    def test_n4_first_doji_misses_and_the_later_sweep_does_not_count(self):
        self.assert_no_trade(backtest(sequence(("P", "D1_hi", "R1_sw", "R2")), htf(HY_SW)))

    def test_n5_first_candle_not_the_lowest_is_skipped_and_logged(self):
        result = backtest(sequence(("P", "R1_eq", "R2_low", "R3")), htf(HY_EQ))
        self.assert_no_trade(result, BuySkipReason.FIRST_NOT_LOWEST)

    def test_n6_run_starts_before_t_conf(self):
        self.assert_no_trade(backtest(sequence(B1_SEQ, start=at(10, 28)), htf(HY_EQ)))

    def test_n7_setup_expired(self):
        self.assert_no_trade(backtest(sequence(B1_SEQ, start=at(11, 12)), htf(HY_EQ)))

    def test_n8_no_setup_while_hy_is_still_forming(self):
        engine = BuyScenarioEngine()
        engine.on_htf_candle(Candle(at(10, 0), *HX), "M15")
        for bar in sequence(B1_SEQ, start=at(10, 25), after=[]):
            self.assertIsNone(engine.on_m1_candle(bar))
        self.assertEqual(engine.armed_setups, ())
        # Even when runs may start before t_conf, a signal closing before HY closes (10:30) is not traded;
        # the same run two minutes later, after HY closed, is.
        early = backtest(sequence(B1_SEQ, start=at(10, 25)), htf(HY_EQ), run_must_start_after_htf=False)
        self.assert_no_trade(early)
        late = backtest(sequence(B1_SEQ, start=at(10, 27)), htf(HY_EQ), run_must_start_after_htf=False)
        self.assertEqual(len(late.trades), 1)

    def test_n9_htf_doji_is_neither_bearish_nor_bullish(self):
        x_doji = (1.40060, 1.40110, 1.40050, 1.40058)  # body 2 of range 60
        y_doji = (1.40060, 1.40120, 1.40050, 1.40063)  # body 3 of range 70
        self.assert_no_trade(backtest(sequence(B1_SEQ), htf(HY_EQ, x=x_doji)))
        self.assert_no_trade(backtest(sequence(B1_SEQ), htf(y_doji)))

    def test_n10_third_doji_drops_the_pending_dojis(self):
        names = ("P1", "P2", "P", "D1", "Dm", "Dx", "R2", "R3", "R3")
        self.assert_no_trade(backtest(sequence(names), htf(HY_EQ)))

    def test_n11_open_sell_blocks_the_buy_and_keeps_the_setup(self):
        engine = both_sides_engine()
        arm(engine)
        for bar in sequence(B1_SEQ):
            self.assertIsNone(engine.on_m1_candle(bar, open_positions=(0, 1)))
        (decision,) = engine.buy.decisions
        self.assertIs(decision.skip_reason, BuySkipReason.POSITION_OPEN)
        self.assertEqual(len(engine.buy.armed_setups), 1)

    def test_n11_open_buy_blocks_only_with_a_position_limit(self):
        limited = BuyScenarioEngine(BuyScenarioParams(max_open_positions=1))  # the spec default
        arm(limited)
        self.assertEqual([limited.on_m1_candle(bar, open_positions=1) for bar in sequence(B1_SEQ)], [None] * 5)
        self.assertIs(limited.decisions[-1].skip_reason, BuySkipReason.POSITION_OPEN)
        unlimited = both_sides_engine()  # the trader's setting: no limit within one side
        arm(unlimited)
        signals = [unlimited.on_m1_candle(bar, open_positions=(1, 0)) for bar in sequence(B1_SEQ)]
        self.assertEqual(signals[3].direction, "BUY")

    def test_n12_disabled_scenario_is_skipped_and_logged(self):
        result = backtest(sequence(B1_SEQ), htf(HY_EQ), enabled_scenarios=(2,))
        self.assert_no_trade(result, BuySkipReason.SCENARIO_DISABLED)


class TestExits(unittest.TestCase):
    """Spec §12 E1-E3 (after B1, long, spread 0) and the long side's bid/ask handling."""

    def run_b1(self, *after, spread=0.0):
        return backtest(sequence(B1_SEQ, after=list(after)), htf(HY_EQ), BacktestSettings(spread_pips=spread))

    def assert_exit(self, result, reason, price, r):
        (trade,) = result.trades
        self.assertEqual(trade.exit_reason, reason)
        self.assertAlmostEqual(trade.exit_price, price, places=5)
        self.assertAlmostEqual(trade.r_multiple, r, places=6)

    def test_e1_high_reaches_tp(self):
        self.assert_exit(self.run_b1((1.40075, 1.40435, 1.40070, 1.40400)), "TP", 1.40435, 10.0)

    def test_e2_low_reaches_sl(self):
        self.assert_exit(self.run_b1((1.40075, 1.40080, 1.40039, 1.40045)), "SL", 1.40039, -1.0)

    def test_e3_sl_and_tp_in_one_bar_count_as_sl(self):
        self.assert_exit(self.run_b1((1.40075, 1.40435, 1.40039, 1.40100)), "SL", 1.40039, -1.0)

    def test_bar_opening_through_the_sl_fills_at_its_open(self):
        self.assert_exit(self.run_b1((1.40030, 1.40035, 1.40020, 1.40025)), "SL", 1.40030, -1.25)

    def test_long_enters_at_the_ask_and_exits_at_the_bid(self):
        result = self.run_b1((1.40100, 1.40485, 1.40090, 1.40480), (1.40480, 1.40490, 1.40470, 1.40489), spread=0.5)
        (trade,) = result.trades
        self.assertAlmostEqual(trade.entry_price, 1.40080, places=5)  # close 1.40075 + 0.5 pip
        self.assertAlmostEqual(trade.take_profit, 1.40490, places=5)  # 10 x 4.1 pips from the fill
        self.assertEqual(trade.exit_time, at(10, 35))  # bid 1.40485 is short of the TP; 1.40490 reaches it
        self.assertAlmostEqual(trade.r_multiple, 10.0, places=6)


class TestFillsAndSetups(unittest.TestCase):
    """Fill options, skips and the §6 setup rules."""

    def test_next_bar_open_fill(self):
        result = backtest(sequence(B1_SEQ, after=[(1.40077, 1.40080, 1.40070, 1.40078)]), htf(), entry_fill="next_bar_open")
        (trade,) = result.trades
        self.assertEqual(trade.entry_time, at(10, 34))
        self.assertAlmostEqual(trade.entry_price, 1.40077, places=5)
        self.assertAlmostEqual(trade.take_profit, 1.40457, places=5)

    def test_bid_at_or_below_the_sl_at_the_fill_is_skipped(self):
        result = backtest(sequence(B1_SEQ, after=[(1.40039, 1.40045, 1.40030, 1.40040)]), htf(), entry_fill="next_bar_open")
        self.assertEqual(result.trades, ())
        self.assertEqual([s.reason for s in result.skips], [BuySkipReason.FILL_AT_OR_BELOW_SL.value])

    def test_no_fill_across_a_feed_gap(self):
        m1 = sequence(B1_SEQ, after=[]) + bars(at(10, 44), quiet(1.40075))
        result = backtest(m1, htf(), entry_fill="next_bar_open")
        self.assertEqual([s.reason for s in result.skips], [BuySkipReason.NO_NEXT_BAR.value])

    def test_outside_session_is_skipped_and_logged(self):
        result = backtest(sequence(B1_SEQ, start=at(21, 30)), htf(start=at(21, 0)))
        self.assertEqual([s.reason for s in result.skips], [BuySkipReason.OUTSIDE_SESSION.value])

    def test_15m_setup_labels_the_trade_before_a_5m_setup(self):
        htf_bars = htf(HY_EQ)
        htf_bars["M5"] = [
            Candle(at(10, 20), 1.40080, 1.40085, 1.40045, 1.40050),
            Candle(at(10, 25), 1.40050, 1.40070, 1.40042, 1.40065),
        ]
        (trade,) = backtest(sequence(B1_SEQ), htf_bars).trades  # the 5m pair is a SWEEP_LOW
        self.assertEqual((trade.scenario, trade.decision.setup.timeframe), (1, "M15"))
        self.assertEqual(trade.decision.matching_setup_ids, ("M15@2026-10-15T10:15", "M5@2026-10-15T10:25"))

    def test_one_trade_per_setup(self):
        result = backtest(sequence(B1_SEQ + B1_SEQ), htf())
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(len(result.decisions), 1)

    def test_close_below_htf_low_cancels_the_setup_only_when_enabled(self):
        self.assertEqual(len(backtest(sequence(B1_SEQ), htf()).trades), 1)  # P closes 1.40045, below 1.40050
        self.assertEqual(backtest(sequence(B1_SEQ), htf(), invalidate_on_close_below_htf_low=True).trades, ())

    def test_proximity_filter_only_when_enabled(self):
        self.assertEqual(backtest(sequence(B1_SEQ), htf(), ltf_near_htf_low_pips=0.5).trades, ())  # 1 pip away
        self.assertEqual(len(backtest(sequence(B1_SEQ), htf(), ltf_near_htf_low_pips=1.0).trades), 1)

    def test_every_doji_counts_alternative(self):
        result = backtest(sequence(("P", "R1_eq", "Dm", "R2")), htf(), doji_counting="every_doji_counts")
        self.assertEqual(result.trades[0].decision.run.signal.timestamp, at(10, 33))

    def test_run_may_start_before_t_conf_only_when_allowed(self):
        result = backtest(sequence(B1_SEQ, start=at(10, 28)), htf(), run_must_start_after_htf=False)
        self.assertEqual(len(result.trades), 1)

    def test_too_many_dojis_is_skipped_when_the_limit_is_lowered(self):
        result = backtest(sequence(("P1", "P2", "P", "D1", "Dm", "R3")), htf(), max_doji_in_run=1)
        self.assertEqual([s.reason for s in result.skips], [BuySkipReason.TOO_MANY_DOJIS.value])

    def test_feed_gap_resets_the_run(self):
        m1 = sequence(("P", "R1_eq"), after=[]) + bars(at(10, 38), FIX["R2"], FIX["R3"], quiet(1.40075))
        self.assertEqual(backtest(m1, htf()).decisions, ())

    def test_a_bar_seen_twice_counts_once(self):
        engine = BuyScenarioEngine()
        arm(engine)
        p, r1, r2, r3, _ = sequence(B1_SEQ)
        signals = [engine.on_m1_candle(bar) for bar in (p, r1, r2, r2, r3)]
        self.assertEqual([s is not None for s in signals], [False, False, False, False, True])
        self.assertAlmostEqual(signals[-1].entry_price, 1.40075, places=5)

    def test_invalid_parameters_are_rejected(self):
        for bad in (
            {"enabled_scenarios": (3,)},
            {"entry_fill": "b3_close"},
            {"doji_counting": "count_some"},
            {"equal_low_mode": "wick"},
            {"doji_body_pct": 100},
            {"max_open_positions": 0},
            {"same_bar_sl_tp": "TP_FIRST"},
            {"session_start_hour": 21, "session_end_hour": 7},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                BuyScenarioParams(**bad)


class TestJournal(unittest.TestCase):
    """Spec §11 fields, in UTC and UTC+6."""

    def test_trade_row_carries_every_column_in_both_time_zones(self):
        result = backtest(sequence(("P", "R1_eq", "Dm", "R2", "R3")), htf(HY_SW))
        (row,) = journal_rows(result)
        self.assertEqual(set(BUY_JOURNAL_COLUMNS) - set(row), set())
        expected = {
            "side": "BUY", "event": "TRADE", "scenario": 2, "htf_pattern": "SWEEP_LOW", "ltf_type": "EQUAL",
            "doji_count": 1, "doji_positions": "2", "run2_kind": "DOJI", "risk_pips": 3.6, "exit_reason": "END_OF_DATA",
            "prior_run_start_utc": "2026-10-15 10:30", "first_candle_time_utc": "2026-10-15 10:31",
            "first_candle_time_utc6": "2026-10-15 16:31", "signal_bar_time_utc": "2026-10-15 10:34",
            "entry_time_utc": "2026-10-15 10:35", "entry_time_utc6": "2026-10-15 16:35",
        }
        self.assertEqual({k: row[k] for k in expected}, expected)
        self.assertAlmostEqual(row["prior_low"], 1.40040, places=5)
        self.assertAlmostEqual(row["setup_low"], 1.40035, places=5)
        self.assertAlmostEqual(row["run4_close"], 1.40075, places=5)

    def test_skip_row_names_the_reason(self):
        (row,) = journal_rows(backtest(sequence(B1_SEQ), htf(), enabled_scenarios=(2,)))
        self.assertEqual((row["event"], row["skip_reason"], row["doji_positions"]), ("SKIPPED", "SCENARIO_DISABLED", "none"))


def signature(decision) -> tuple:
    return (
        decision.signal_time,
        decision.scenario,
        decision.setup.setup_id,
        decision.stop_loss,
        decision.skip_reason,
    )


class TestNoLookAhead(unittest.TestCase):
    """Spec §12 replay and mutation tests."""

    @classmethod
    def setUpClass(cls):
        cls.m1, cls.htf = synthetic_history(seed=7)
        cls.batch = [signature(d) for d in backtest(cls.m1, cls.htf).decisions]

    def test_history_has_enough_signals_for_the_checks(self):
        self.assertGreaterEqual(len(self.batch), 5)

    def test_streaming_replay_matches_batch(self):
        engine = BuyScenarioEngine()
        htf_closes = sorted(
            ((c.timestamp + HTF_DELTAS[tf], tf, c) for tf, candles in self.htf.items() for c in candles),
            key=lambda event: (event[0], event[1] != "M15"),
        )
        i = 0
        for bar in self.m1:
            while i < len(htf_closes) and htf_closes[i][0] <= bar.timestamp + M1:
                engine.on_htf_candle(htf_closes[i][2], htf_closes[i][1])
                i += 1
            engine.on_m1_candle(bar)
        self.assertEqual([signature(d) for d in engine.decisions], self.batch)

    def test_changing_candles_after_t_leaves_earlier_decisions_unchanged(self):
        cut = self.m1[len(self.m1) // 2].timestamp

        def bump(c):
            return Candle(c.timestamp, c.open - 0.00037, c.high - 0.00037, c.low - 0.00052, c.close - 0.00037)

        def mutate(candles, duration):
            return [c if c.timestamp + duration <= cut else bump(c) for c in candles]

        m1 = mutate(self.m1, M1)
        htf_bars = {tf: mutate(candles, HTF_DELTAS[tf]) for tf, candles in self.htf.items()}
        after = [signature(d) for d in backtest(m1, htf_bars).decisions]
        before_cut = [s for s in self.batch if s[0] <= cut]
        self.assertTrue(before_cut)
        self.assertEqual([s for s in after if s[0] <= cut], before_cut)


class FakeEngine:
    """Signals on every 1m candle: just enough of a scenario engine for AkScenariosEngine."""

    def __init__(self, direction):
        self.direction = direction
        self.params = SimpleNamespace(rr=10.0, point_size=0.00001, max_open_positions=HEDGE_BLOCK)
        self.decisions = []
        self.armed_setups = ()

    def reset(self):
        self.decisions = []

    def on_htf_candle(self, raw_candle, timeframe):
        return None

    def on_m1_candle(self, raw_candle, open_positions=0):
        setup = SimpleNamespace(setup_id=f"{self.direction}-setup")
        self.decisions.append(SimpleNamespace(scenario=1, setup=setup, signal_time=raw_candle.timestamp + M1))
        return TradeSignal(self.direction, 1.4, 1.4, 1.4, 0.0, 0.0)


class TestAkScenarios(unittest.TestCase):
    """Sell + buy on one symbol: no hedging, the same-bar conflict, and sell-only parity."""

    def test_buy_trades_once_the_sell_is_closed(self):
        engine = both_sides_engine()
        arm(engine)
        p, r1, r2, r3, _ = sequence(B1_SEQ)
        self.assertIsNone(engine.on_m1_candle(p, open_positions=(0, 1)))
        for bar in (r1, r2):
            self.assertIsNone(engine.on_m1_candle(bar, open_positions=(0, 0)))
        self.assertEqual(engine.on_m1_candle(r3, open_positions=(0, 0)).direction, "BUY")
        self.assertIs(engine.last_decision, engine.buy.decisions[-1])

    def test_unknown_positions_block_both_sides(self):
        for counter in (lambda: None, lambda: 1 / 0):
            with self.subTest(counter=counter):
                engine = both_sides_engine()
                engine.position_counter = counter
                arm(engine)
                self.assertEqual([engine.on_m1_candle(bar) for bar in sequence(B1_SEQ)], [None] * 5)
                self.assertIs(engine.buy.decisions[-1].skip_reason, BuySkipReason.POSITION_OPEN)

    def test_same_bar_sell_and_buy_send_neither(self):
        records = []
        engine = AkScenariosEngine(sell=FakeEngine("SELL"), buy=FakeEngine("BUY"), event_sink=records.append)
        self.assertIsNone(engine.on_m1_candle(Candle(at(10, 33), 1.4, 1.4, 1.4, 1.4)))
        self.assertIsNone(engine.last_decision)
        self.assertEqual(len(engine.conflicts), 1)
        self.assertEqual(
            {k: records[0][k] for k in ("event", "sell_setup_id", "buy_setup_id", "signal_time_utc")},
            {"event": SAME_BAR_CONFLICT, "sell_setup_id": "SELL-setup", "buy_setup_id": "BUY-setup",
             "signal_time_utc": "2026-10-15 10:34"},
        )

    def test_constructor_rules(self):
        with self.assertRaises(ValueError):
            AkScenariosEngine()
        with self.assertRaises(ValueError):  # no hedging needs a position limit on both engines
            AkScenariosEngine(sell=SellScenarioEngine(), buy=BuyScenarioEngine())
        with self.assertRaises(ValueError):
            AkScenariosEngine(
                sell=SellScenarioEngine(no_hedging_params(SellScenarioParams(rr=5.0))),
                buy=BuyScenarioEngine(no_hedging_params(BuyScenarioParams())),
            )
        self.assertIsNotNone(AkScenariosEngine(sell=SellScenarioEngine(), buy=BuyScenarioEngine(), no_hedging=False))

    def test_sell_only_run_matches_run_sell_backtest(self):
        m1, htf_bars = synthetic_history(seed=7)

        def fills(trades):
            return [(t.entry_time, t.entry_price, t.stop_loss, t.take_profit, t.exit_time, t.exit_price, t.r_multiple)
                    for t in trades]

        expected = run_sell_backtest(m1, htf_bars)
        actual = run_scenarios_backtest(m1, htf_bars, AkScenariosEngine(sell=SellScenarioEngine()))
        self.assertTrue(expected.trades)
        self.assertEqual(fills(actual.trades), fills(expected.trades))
        self.assertEqual(len(actual.skips), len(expected.skips))

    def test_combined_run_never_holds_both_sides(self):
        m1, htf_bars = synthetic_history(seed=7)
        result = run_scenarios_backtest(m1, htf_bars, both_sides_engine())
        self.assertEqual({t.side for t in result.trades}, {"BUY", "SELL"})
        for buy in (t for t in result.trades if t.side == "BUY"):
            for sell in (t for t in result.trades if t.side == "SELL"):
                self.assertFalse(buy.entry_time < sell.exit_time and sell.entry_time < buy.exit_time, (buy, sell))


class TestLiveBridge(unittest.TestCase):
    """bridge/executor.py with the buy engine, the guardrails and the EA's account snapshot."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_buy_scenarios_")
        self.client = DWXClient(mt4_files_dir=self.temp_dir, initial_backoff_ms=10, max_backoff_ms=100)
        self.signal = TradeSignal(
            direction="BUY",
            entry_price=1.40075,
            stop_loss=1.40039,
            take_profit=1.40435,
            risk_distance=0.00036,
            reward_distance=0.00360,
            reward_risk_ratio=10.0,
            sweep_type="BUY_S1",
            timeframe="M1",
            timestamp=datetime.now(UTC),
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def executor(self, guardrails=None, db=None):
        return BridgeExecutor(
            symbol="USDCAD",
            dwx_client=self.client,
            rule_engine=BuyScenarioEngine(),
            risk_guardrails=guardrails,
            db=db,
            exact_risk_sizing=True,
            confirmation_timeout_sec=0.01,
        )

    @staticmethod
    def guardrails(max_spread=Decimal("2.5")):
        limits = RiskLimits(
            max_daily_loss_pct=Decimal("0.03"), max_open_trades=None, max_spread_pips=max_spread, session_filter_enabled=False
        )
        return RiskGuardrails(limits=limits, tracker=DailyPnLTracker(initial_balance=Decimal("5000.00")))

    @staticmethod
    def ea_account(bid=1.40074, ask=1.40075, balance=5000.0, equity=5000.0, spread=0.1, orders=()) -> dict:
        """DWX_Account.txt as DWX_Server.mq4 writes it: chart quote on top, pairs keyed with "m"."""
        return {
            "account_number": 1, "company": "Exness", "account_name": "test", "currency": "USD",
            "balance": balance, "equity": equity, "margin": 0.0, "free_margin": equity, "profit": equity - balance,
            "leverage": 2000, "symbol": "USDCADm", "bid": bid, "ask": ask, "spread_pips": spread, "digits": 5,
            "pairs": {
                "EURUSDm": {"bid": 1.16000, "ask": 1.16002, "spread_pips": 0.2},
                "USDCADm": {"bid": bid, "ask": ask, "spread_pips": spread},
            },
            "timestamp": "2026-10-26 10:34:00", "open_orders_count": len(orders), "orders": list(orders),
        }

    def write_ea_account(self, data=None, **fields):
        self.client.write_mock_account(raw_json_str=json.dumps(data or self.ea_account(**fields)) + "\n")

    def ak_bridge(self):
        cfg = AppConfig(mt4_files_dir=Path(self.temp_dir), session_start_hour=7, session_end_hour=21, max_open_trades=None)
        engine = build_ak_scenarios_engine(cfg, "USDCADm")
        executor = BridgeExecutor(
            symbol="USDCAD", dwx_client=self.client, rule_engine=engine, exact_risk_sizing=True, confirmation_timeout_sec=0.01
        )
        return engine, executor

    def test_tp_is_ten_times_the_risk_from_the_live_ask(self):
        self.write_ea_account()
        record = self.executor()._execute_signal(self.signal)
        self.assertEqual((record.sl_price, record.tp_price), (Decimal("1.40039"), Decimal("1.40435")))

    def test_no_order_when_the_bid_is_at_or_below_the_sl(self):
        for bid in (1.40039, 1.40038):
            with self.subTest(bid=bid):
                self.write_ea_account(bid=bid, ask=round(bid + 0.00001, 5))
                record = self.executor()._execute_signal(self.signal)
                self.assertEqual((record.status, record.rejection_reason), ("REJECTED", "SL_NOT_BELOW_BID"))
                self.assertFalse(self.client.commands_file.exists())

    def test_daily_loss_counts_closed_and_floating_losses(self):
        executor = self.executor(self.guardrails())
        self.write_ea_account(balance=5000.0, equity=5000.0)
        executor.step()  # the day's first account reading
        self.write_ea_account(balance=4900.0, equity=4840.0)  # -100 closed, -60 floating: 3.2% of 5000
        record = executor._execute_signal(self.signal)
        self.assertEqual(record.status, "REJECTED")
        self.assertIn("DAILY_LOSS_LIMIT_EXCEEDED", record.rejection_reason)
        self.assertFalse(self.client.commands_file.exists())

    def test_loss_below_the_limit_passes_the_guardrails(self):
        executor = self.executor(self.guardrails())
        self.write_ea_account(balance=5000.0, equity=5000.0)
        executor.step()
        self.write_ea_account(balance=4900.0, equity=4900.0)  # 2%
        record = executor._execute_signal(self.signal)
        self.assertNotIn("RISK", record.rejection_reason or "")
        self.assertTrue(self.client.commands_file.exists())

    def test_day_start_survives_a_restart(self):
        db = TradingDatabase(Path(self.temp_dir) / "journal.db")
        self.write_ea_account(balance=5000.0, equity=5000.0)
        self.executor(self.guardrails(), db).step()
        self.write_ea_account(balance=4900.0, equity=4840.0)
        record = self.executor(self.guardrails(), db)._execute_signal(self.signal)  # a fresh bridge process
        self.assertIn("DAILY_LOSS_LIMIT_EXCEEDED", record.rejection_reason)

    def test_spread_above_the_ceiling_is_rejected(self):
        self.write_ea_account(spread=3.0)
        record = self.executor(self.guardrails())._execute_signal(self.signal)
        self.assertIn("SPREAD_EXCEEDS_MAX", record.rejection_reason)

    def test_unreadable_snapshot_at_the_guardrails_sends_nothing(self):
        executor = self.executor(self.guardrails())
        self.write_ea_account()
        executor._account_snapshot = lambda fresh=False: None  # the gate's read caught the file half-written
        record = executor._execute_signal(self.signal)
        self.assertEqual((record.status, record.rejection_reason), ("REJECTED", "ACCOUNT_SNAPSHOT_UNREADABLE"))
        self.assertFalse(self.client.commands_file.exists())

    def test_snapshot_without_equity_sends_nothing(self):
        data = self.ea_account()
        del data["equity"]
        self.write_ea_account(data)
        record = self.executor(self.guardrails())._execute_signal(self.signal)
        self.assertEqual(record.rejection_reason, "ACCOUNT_SNAPSHOT_UNREADABLE")
        self.assertFalse(self.client.commands_file.exists())

    def test_half_written_snapshot_is_read_again(self):
        executor = self.executor()
        self.write_ea_account()
        snapshot = self.client.read_account_info()
        with mock.patch.object(self.client, "read_account_info", side_effect=[None, snapshot]) as read:
            self.assertEqual(executor._account_snapshot(), snapshot)
        self.assertEqual(read.call_count, 2)

    def test_buy_factory_takes_session_and_position_limit_from_config(self):
        cfg = AppConfig(mt4_files_dir=Path(self.temp_dir), session_start_hour=7, session_end_hour=21, max_open_trades=None)
        engine = build_buy_scenario_engine(cfg, "USDCADm")
        self.assertEqual((engine.params.session_start_hour, engine.params.session_end_hour), (7, 21))
        self.assertIsNone(engine.params.max_open_positions)

    def test_buy_factory_journals_signals(self):
        cfg = AppConfig(mt4_files_dir=Path(self.temp_dir), session_start_hour=7, session_end_hour=21, max_open_trades=None)
        db = TradingDatabase(Path(self.temp_dir) / "journal.db")
        engine = build_buy_scenario_engine(cfg, "USDCADm", db)
        arm(engine)
        for bar in sequence(B1_SEQ):
            engine.on_m1_candle(bar)
        (log,) = [r for r in db.get_audit_logs() if r["event_type"] == "BUY_SCENARIO_SIGNAL"]
        self.assertEqual(log["source_component"], "buy_scenarios")
        self.assertEqual(json.loads(log["details"])["first_candle_time_utc"], "2026-10-15 10:31")

    def test_ak_bridge_blocks_a_buy_while_the_ea_lists_a_sell(self):
        engine, executor = self.ak_bridge()
        self.assertEqual((engine.sell.params.max_open_positions, engine.buy.params.max_open_positions), (HEDGE_BLOCK,) * 2)
        self.assertEqual(engine.position_counter, executor.open_positions_by_side)
        self.write_ea_account(orders=[{"ticket": 7, "symbol": "USDCADm", "type": "SELL"}])
        self.assertEqual(engine.position_counter(), (0, 1))
        arm(engine)
        self.assertEqual([engine.on_m1_candle(bar) for bar in sequence(B1_SEQ)], [None] * 5)
        self.assertIs(engine.buy.decisions[-1].skip_reason, BuySkipReason.POSITION_OPEN)

    def test_an_order_the_ea_has_not_listed_yet_counts_as_open(self):
        _, executor = self.ak_bridge()
        executor.order_records.append(
            BridgeOrderRecord(
                magic=1, signal_id="USDCAD_BUY", symbol="USDCAD", direction=Direction.BUY, lots=Decimal("0.10"),
                entry_price=Decimal("1.40075"), sl_price=Decimal("1.40039"), tp_price=Decimal("1.40435"),
                risk_pips=Decimal("3.6"), reward_pips=Decimal("36.0"), dispatched_at=datetime.now(UTC),
                ticket=7, status="FILLED",
            )
        )
        self.write_ea_account()  # the fill is not in the EA's order list yet
        self.assertEqual(executor.open_positions_by_side(), (1, 0))
        self.write_ea_account(orders=[{"ticket": 7, "symbol": "USDCADm", "type": "BUY"}])
        self.assertEqual(executor.open_positions_by_side(), (1, 0))  # listed now: counted once

    def test_positions_are_unknown_without_a_fresh_account_file(self):
        _, executor = self.ak_bridge()
        self.assertIsNone(executor.open_positions_by_side())
        self.write_ea_account()
        old = time.time() - 60
        os.utime(self.client.account_file, (old, old))
        self.assertIsNone(executor.open_positions_by_side())

    def test_open_positions_by_side_counts_this_symbol_only(self):
        orders = [
            {"symbol": "USDCADm", "type": "BUY"},
            {"symbol": "USDCADm", "type": "SELL"},
            {"symbol": "EURUSDm", "type": "BUY"},
            {"symbol": "USDCADm", "type": "PENDING"},
        ]
        self.assertEqual(open_positions_by_side({"orders": orders}, "USDCAD"), (1, 1))
        self.assertIsNone(open_positions_by_side({"balance": 5000.0}, "USDCAD"))
        self.assertIsNone(open_positions_by_side(None, "USDCAD"))

    def test_account_spread_from_the_chart_or_the_pair(self):
        self.assertEqual(account_spread_pips({"symbol": "USDCAD", "spread_pips": 0.2}, "USDCADm"), Decimal("0.2"))
        pairs = {"symbol": "EURUSDm", "spread_pips": 0.9, "pairs": {"USDCADm": {"spread_pips": 0.3}}}
        self.assertEqual(account_spread_pips(pairs, "USDCAD"), Decimal("0.3"))
        self.assertIsNone(account_spread_pips({"symbol": "EURUSDm", "spread_pips": 0.9}, "USDCAD"))
        self.assertIsNone(account_spread_pips("not a snapshot", "USDCAD"))


class TestDayStartBalances(unittest.TestCase):
    """bridge/day_start.py: the daily loss limit's baseline per UTC day and MT4 account."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_day_start_")
        self.db = TradingDatabase(Path(self.temp_dir) / "journal.db")
        self.now = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def starts(self, db="shared"):
        return DayStartBalances(self.db if db == "shared" else db, clock=lambda: self.now)

    def test_the_days_first_reading_is_its_start(self):
        starts = self.starts()
        self.assertEqual(starts.balance_at_start(Decimal("5000"), "111"), Decimal("5000"))
        self.assertEqual(starts.balance_at_start(Decimal("4900"), "111"), Decimal("5000"))

    def test_a_new_utc_day_starts_from_its_first_reading(self):
        starts = self.starts()
        starts.balance_at_start(Decimal("5000"), "111")
        self.now = datetime(2026, 10, 27, 0, 0, tzinfo=UTC)
        self.assertEqual(starts.balance_at_start(Decimal("4900"), "111"), Decimal("4900"))

    def test_a_restart_keeps_the_days_start(self):
        self.starts().balance_at_start(Decimal("5000"), "111")
        self.assertEqual(self.starts().balance_at_start(Decimal("4900"), "111"), Decimal("5000"))

    def test_each_account_has_its_own_start(self):
        starts = self.starts()
        starts.balance_at_start(Decimal("5000"), "111")
        self.assertEqual(starts.balance_at_start(Decimal("150"), "222"), Decimal("150"))  # a switch to another account
        self.assertEqual(self.starts().balance_at_start(Decimal("140"), "222"), Decimal("150"))  # after a restart
        self.assertEqual(starts.balance_at_start(Decimal("4800"), "111"), Decimal("5000"))  # and back

    def test_without_a_database_the_start_lives_in_memory(self):
        starts = self.starts(db=None)
        starts.balance_at_start(Decimal("5000"), "111")
        self.assertEqual(starts.balance_at_start(Decimal("4900"), "111"), Decimal("5000"))
        self.assertEqual(self.starts(db=None).balance_at_start(Decimal("4900"), "111"), Decimal("4900"))


if __name__ == "__main__":
    unittest.main()
