"""
Tests for the 1-minute Sell Scenarios 1-4 (SELL_STRATEGY_PROMPT.md §11).

Fixtures are USDCAD prices with spread 0, ENTRY_FILL = next_bar_open and default
parameters unless a test says otherwise:
- HTF fixtures (15m): HX + HY_eq -> EQUAL_TOP, HX + HY_sw -> WICK_SWEEP.
- Positive cases T1-T6, negative cases N1-N11, exit cases E1-E3.
- No look-ahead: a streaming replay equals the batch run, and changing candles after
  time T leaves every signal before T unchanged.
- Live bridge: TP is priced from the live bid, and no order is sent when the bid is at
  or above the SL.
"""

import json
import os
import random
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from bridge.dwx_client import DWXClient
from bridge.executor import BridgeExecutor, build_sell_scenario_engine
from config import AppConfig, load_config
from engine.models import Candle, TradeSignal
from engine.rule_engine import resample_m1_to_htf
from engine.sell_scenarios import (
    HTF_DELTAS,
    M1,
    CandleKind,
    PointCandle,
    SellScenarioEngine,
    SellScenarioParams,
    SkipReason,
    TopPattern,
    candle_kind,
    top_pattern,
)
from engine.sell_scenarios_backtest import (
    JOURNAL_COLUMNS,
    SellBacktestSettings,
    journal_rows,
    run_sell_backtest,
)

UTC = timezone.utc
DAY = datetime(2026, 10, 15, tzinfo=UTC)  # a Thursday, inside the 07:00-21:00 UTC session

# HTF fixtures (15m): open, high, low, close
HX = (1.40050, 1.40100, 1.40040, 1.40090)
HY_EQ = (1.40090, 1.40100, 1.40030, 1.40040)
HY_SW = (1.40090, 1.40115, 1.40030, 1.40040)

# 1m fixtures
A = (1.40060, 1.40080, 1.40055, 1.40075)
B1_EQ = (1.40075, 1.40080, 1.40060, 1.40062)
B1_SW = (1.40075, 1.40088, 1.40060, 1.40062)
B1_DOJI = (1.40070, 1.40080, 1.40060, 1.40070)
B2 = (1.40062, 1.40064, 1.40050, 1.40052)
B2_DOJI = (1.40062, 1.40066, 1.40056, 1.40062)
B3 = (1.40052, 1.40054, 1.40040, 1.40042)
B3_DOJI = (1.40052, 1.40056, 1.40046, 1.40052)


def at(hour: int, minute: int) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


def bars(start: datetime, *ohlcs: tuple) -> list:
    """Adjacent 1m candles starting at `start`."""
    return [Candle(start + i * M1, *ohlc) for i, ohlc in enumerate(ohlcs)]


def quiet(close: float) -> tuple:
    """A bearish bar opening at `close` that touches neither the SL nor the TP of the fixtures."""
    return (close, round(close + 0.00003, 5), round(close - 0.00004, 5), round(close - 0.00002, 5))


def entry_sequence(start: datetime, b1=B1_EQ, b2=B2, b3=B3, after=()) -> list:
    """A, B1, B2, B3 from `start`, then the next bar (open = close of B3), then `after`."""
    return bars(start, A, b1, b2, b3, quiet(b3[3]), *after)


def htf(y=HY_EQ, x=HX, start=None) -> dict:
    """The 15m pair X, Y; X opens at `start` (default 10:00)."""
    start = start or at(10, 0)
    return {"M15": [Candle(start, *x), Candle(start + HTF_DELTAS["M15"], *y)], "M5": []}


def backtest(m1, htf_bars, settings=None, **params):
    return run_sell_backtest(m1, htf_bars, SellScenarioParams(**params), settings or SellBacktestSettings())


def pc(ohlc: tuple) -> PointCandle:
    return PointCandle.of(Candle(at(10, 0), *ohlc), 0.00001)


def armed_engine(params=None, y=HY_EQ) -> SellScenarioEngine:
    engine = SellScenarioEngine(params)
    engine.on_htf_candle(Candle(at(10, 0), *HX), "M15")
    engine.on_htf_candle(Candle(at(10, 15), *y), "M15")
    return engine


class TestPrimitives(unittest.TestCase):
    """Spec §3.1 candle kind and §3.2 top_pattern, on integer points."""

    def test_candle_kind_checks_doji_first(self):
        self.assertIs(candle_kind(pc(B1_DOJI)), CandleKind.DOJI)
        self.assertIs(candle_kind(pc(A)), CandleKind.BULL)
        self.assertIs(candle_kind(pc(B3)), CandleKind.BEAR)

    def test_doji_tolerance_widens_the_no_body_band(self):
        one_point_body = (1.40070, 1.40080, 1.40060, 1.40071)
        self.assertIs(candle_kind(pc(one_point_body)), CandleKind.BULL)
        self.assertIs(candle_kind(pc(one_point_body), doji_tol_pts=1), CandleKind.DOJI)

    def test_equal_top_and_wick_sweep(self):
        self.assertIs(top_pattern(pc(A), pc(B1_EQ), 0), TopPattern.EQUAL_TOP)
        self.assertIs(top_pattern(pc(A), pc(B1_SW), 0), TopPattern.WICK_SWEEP)

    def test_x_must_be_bullish(self):
        self.assertIs(top_pattern(pc(B3), pc(B1_EQ), 0), TopPattern.NONE)

    def test_sweep_needs_open_at_or_below_and_close_below_x_high(self):
        opened_above = (1.40085, 1.40090, 1.40060, 1.40062)
        closed_at_x_high = (1.40078, 1.40090, 1.40060, 1.40080)
        self.assertIs(top_pattern(pc(A), pc(opened_above), 0), TopPattern.NONE)
        self.assertIs(top_pattern(pc(A), pc(closed_at_x_high), 0), TopPattern.NONE)

    def test_equal_top_and_sweep_are_mutually_exclusive(self):
        two_points_above = (1.40075, 1.40082, 1.40060, 1.40062)
        self.assertIs(top_pattern(pc(A), pc(two_points_above), 2), TopPattern.EQUAL_TOP)
        self.assertIs(top_pattern(pc(A), pc(two_points_above), 1), TopPattern.WICK_SWEEP)


class TestHtfFixtures(unittest.TestCase):
    """Spec §11 HTF fixtures and §5 arming."""

    def arm(self, y):
        engine = SellScenarioEngine()
        self.assertIsNone(engine.on_htf_candle(Candle(at(10, 0), *HX), "M15"))
        return engine.on_htf_candle(Candle(at(10, 15), *y), "M15")

    def test_hx_hy_eq_is_equal_top_confirmed_10_30_expiring_11_15(self):
        setup = self.arm(HY_EQ)
        self.assertIs(setup.pattern, TopPattern.EQUAL_TOP)
        self.assertEqual(setup.t_conf, at(10, 30))
        self.assertEqual(setup.t_exp, at(11, 15))
        self.assertAlmostEqual(setup.setup_high, 1.40100, places=5)

    def test_hx_hy_sw_is_wick_sweep(self):
        self.assertIs(self.arm(HY_SW).pattern, TopPattern.WICK_SWEEP)

    def test_htf_candles_must_be_adjacent(self):
        engine = SellScenarioEngine()
        engine.on_htf_candle(Candle(at(9, 45), *HX), "M15")
        self.assertIsNone(engine.on_htf_candle(Candle(at(10, 15), *HY_EQ), "M15"))


class TestPositiveCases(unittest.TestCase):
    """Spec §11 T1-T6."""

    def assert_trade(self, result, scenario, entry, sl, tp, risk_pips=None, doji="none"):
        self.assertEqual(len(result.trades), 1, result.skips)
        trade = result.trades[0]
        self.assertEqual(trade.scenario, scenario)
        self.assertEqual(trade.decision.doji_position, doji)
        self.assertAlmostEqual(trade.entry_price, entry, places=5)
        self.assertAlmostEqual(trade.stop_loss, sl, places=5)
        self.assertAlmostEqual(trade.take_profit, tp, places=5)
        if risk_pips is not None:
            self.assertAlmostEqual(trade.risk_pips, risk_pips, places=6)
        return trade

    def test_t1_scenario_1(self):
        result = backtest(entry_sequence(at(10, 30)), htf(HY_EQ))
        trade = self.assert_trade(result, 1, 1.40042, 1.40081, 1.39652, risk_pips=3.9)
        self.assertEqual(trade.entry_time, at(10, 34))
        self.assertIs(trade.decision.ltf_pattern, TopPattern.EQUAL_TOP)

    def test_t2_scenario_2(self):
        result = backtest(entry_sequence(at(10, 30), b1=B1_SW), htf(HY_SW))
        trade = self.assert_trade(result, 2, 1.40042, 1.40089, 1.39572, risk_pips=4.7)
        self.assertIs(trade.decision.ltf_pattern, TopPattern.WICK_SWEEP)

    def test_t3_scenario_3_doji_in_position_2(self):
        result = backtest(entry_sequence(at(10, 30), b1=B1_SW, b2=B2_DOJI), htf(HY_EQ))
        self.assert_trade(result, 3, 1.40042, 1.40089, 1.39572, doji="2")

    def test_t4_scenario_4_doji_in_position_3(self):
        result = backtest(entry_sequence(at(10, 30), b3=B3_DOJI), htf(HY_SW))
        self.assert_trade(result, 4, 1.40052, 1.40081, 1.39762, risk_pips=2.9, doji="3")

    def test_t5_doji_in_position_1_forms_the_equal_top(self):
        result = backtest(entry_sequence(at(10, 30), b1=B1_DOJI), htf(HY_EQ))
        self.assert_trade(result, 3, 1.40042, 1.40081, 1.39652, doji="1")

    def test_t6_b3_closing_at_t_exp_still_trades(self):
        result = backtest(entry_sequence(at(11, 11)), htf(HY_EQ))
        self.assert_trade(result, 1, 1.40042, 1.40081, 1.39652)


class TestNegativeCases(unittest.TestCase):
    """Spec §11 N1-N11: no trade."""

    def assert_no_trade(self, result):
        self.assertEqual(result.trades, ())
        self.assertEqual(result.skips, ())

    def test_n1_bullish_candle_inside_the_three(self):
        b2_bullish = (1.40052, 1.40064, 1.40050, 1.40062)
        self.assert_no_trade(backtest(entry_sequence(at(10, 30), b2=b2_bullish), htf()))

    def test_n2_two_dojis(self):
        self.assert_no_trade(backtest(entry_sequence(at(10, 30), b2=B2_DOJI, b3=B3_DOJI), htf()))

    def test_n3_neither_equal_top_nor_sweep(self):
        b1_one_point_low = (1.40075, 1.40079, 1.40060, 1.40062)
        self.assert_no_trade(backtest(entry_sequence(at(10, 30), b1=b1_one_point_low), htf()))

    def test_n4_pattern_starts_before_t_conf(self):
        self.assert_no_trade(backtest(entry_sequence(at(10, 29)), htf()))

    def test_n5_setup_expired(self):
        self.assert_no_trade(backtest(entry_sequence(at(11, 12)), htf()))

    def test_n6_b1_no_longer_the_highest(self):
        b2_above_b1 = (1.40062, 1.40085, 1.40050, 1.40052)
        self.assert_no_trade(backtest(entry_sequence(at(10, 30), b2=b2_above_b1), htf()))

    def test_n7_disabled_scenario_is_skipped_and_logged(self):
        result = backtest(
            entry_sequence(at(10, 30), b1=B1_SW, b2=B2_DOJI), htf(HY_EQ), enabled_scenarios=(1, 2)
        )
        self.assertEqual(result.trades, ())
        self.assertEqual(
            [(s.decision.scenario, s.reason) for s in result.skips], [(3, SkipReason.SCENARIO_DISABLED)]
        )

    def test_n8_no_setup_while_hy_is_still_forming(self):
        engine = SellScenarioEngine()
        engine.on_htf_candle(Candle(at(10, 0), *HX), "M15")
        for candle in bars(at(10, 25), A, B1_EQ, B2, B3):  # B3 closes at 10:29
            self.assertIsNone(engine.on_m1_candle(candle))
        self.assertEqual(engine.armed_setups, ())
        setup = engine.on_htf_candle(Candle(at(10, 15), *HY_EQ), "M15")  # HY closes at 10:30
        self.assertEqual(setup.t_conf, at(10, 30))
        self.assertEqual(engine.decisions, [])
        self.assert_no_trade(backtest(entry_sequence(at(10, 25)), htf()))

    def test_n9_b1_opened_above_a_high(self):
        b1_opened_above = (1.40085, 1.40090, 1.40060, 1.40062)
        self.assert_no_trade(backtest(entry_sequence(at(10, 30), b1=b1_opened_above), htf()))

    def test_n10_bullish_hy(self):
        hy_bullish = (1.40040, 1.40100, 1.40030, 1.40090)
        self.assert_no_trade(backtest(entry_sequence(at(10, 30)), htf(hy_bullish)))

    def test_n11_position_open_is_skipped_logged_and_keeps_the_setup(self):
        engine = armed_engine(SellScenarioParams(max_open_positions=1))
        for candle in bars(at(10, 30), A, B1_EQ, B2, B3):
            self.assertIsNone(engine.on_m1_candle(candle, open_positions=1))
        self.assertEqual(
            [(d.scenario, d.skip_reason) for d in engine.decisions], [(1, SkipReason.POSITION_OPEN)]
        )
        self.assertEqual(len(engine.armed_setups), 1)


class TestExits(unittest.TestCase):
    """Spec §11 E1-E3, plus the short closing at the ask."""

    def exit_of(self, exit_bar, settings=None):
        result = backtest(entry_sequence(at(10, 30), after=(exit_bar,)), htf(), settings)
        self.assertEqual(len(result.trades), 1)
        return result.trades[0]

    def test_e1_low_reaches_tp(self):
        trade = self.exit_of((1.40040, 1.40041, 1.39650, 1.39700))
        self.assertEqual(trade.exit_reason, "TP")
        self.assertAlmostEqual(trade.r_multiple, 10.0)
        self.assertEqual(trade.exit_time, at(10, 35))

    def test_e2_high_reaches_sl(self):
        trade = self.exit_of((1.40040, 1.40081, 1.40030, 1.40050))
        self.assertEqual(trade.exit_reason, "SL")
        self.assertAlmostEqual(trade.r_multiple, -1.0)

    def test_e3_sl_and_tp_in_one_bar_count_as_sl(self):
        trade = self.exit_of((1.40040, 1.40081, 1.39650, 1.39700))
        self.assertEqual(trade.exit_reason, "SL")
        self.assertAlmostEqual(trade.r_multiple, -1.0)

    def test_bar_opening_through_the_sl_fills_at_its_open(self):
        trade = self.exit_of((1.40090, 1.40095, 1.40085, 1.40090))
        self.assertEqual(trade.exit_reason, "SL")
        self.assertAlmostEqual(trade.exit_price, 1.40090, places=5)
        self.assertAlmostEqual(trade.r_multiple, -48 / 39)

    def test_short_closes_at_the_ask(self):
        bid_high_two_points_under_sl = (1.40040, 1.40079, 1.40030, 1.40050)
        self.assertEqual(self.exit_of(bid_high_two_points_under_sl).exit_reason, "END_OF_DATA")
        trade = self.exit_of(bid_high_two_points_under_sl, SellBacktestSettings(spread_pips=0.2))
        self.assertEqual(trade.exit_reason, "SL")
        self.assertAlmostEqual(trade.r_multiple, -1.0)


class TestFillsAndSetups(unittest.TestCase):
    """Spec §5-§6 behaviour around fills, sessions and armed setups."""

    def test_fill_at_or_above_sl_is_skipped_and_logged(self):
        m1 = bars(at(10, 30), A, B1_EQ, B2, B3, (1.40081, 1.40085, 1.40075, 1.40080))
        result = backtest(m1, htf())
        self.assertEqual(result.trades, ())
        self.assertEqual([s.reason for s in result.skips], [SkipReason.FILL_AT_OR_ABOVE_SL])

    def test_fill_whose_ask_reaches_the_sl_is_skipped(self):
        # Bid 1.40079 + 0.2 pip spread = ask 1.40081 = SL: the broker would reject the stop.
        m1 = bars(at(10, 30), A, B1_EQ, B2, B3, (1.40079, 1.40080, 1.40070, 1.40075))
        self.assertEqual(len(backtest(m1, htf()).trades), 1)
        result = backtest(m1, htf(), SellBacktestSettings(spread_pips=0.2))
        self.assertEqual(result.trades, ())
        self.assertEqual([s.reason for s in result.skips], [SkipReason.FILL_AT_OR_ABOVE_SL])

    def test_no_fill_across_a_feed_gap(self):
        m1 = bars(at(10, 30), A, B1_EQ, B2, B3) + [Candle(at(10, 50), *quiet(B3[3]))]
        result = backtest(m1, htf())
        self.assertEqual(result.trades, ())
        self.assertEqual([s.reason for s in result.skips], [SkipReason.NO_NEXT_BAR])

    def test_b3_close_fill(self):
        trade = backtest(entry_sequence(at(10, 30)), htf(), entry_fill="b3_close").trades[0]
        self.assertEqual(trade.entry_time, at(10, 34))
        self.assertAlmostEqual(trade.entry_price, 1.40042, places=5)
        self.assertAlmostEqual(trade.take_profit, 1.39652, places=5)

    def test_outside_session_is_skipped_and_logged(self):
        # The 15m pair closes at 21:00, so B3 opens at 21:03: past the 07:00-21:00 UTC session.
        result = backtest(entry_sequence(at(21, 0)), htf(start=at(20, 30)))
        self.assertEqual(result.trades, ())
        self.assertEqual([s.reason for s in result.skips], [SkipReason.OUTSIDE_SESSION])

    def test_15m_setup_labels_the_trade_before_a_5m_setup(self):
        m5_sweep = [
            Candle(at(10, 20), 1.40050, 1.40080, 1.40045, 1.40075),
            Candle(at(10, 25), 1.40075, 1.40090, 1.40040, 1.40045),
        ]
        trade = backtest(entry_sequence(at(10, 30)), {"M15": htf()["M15"], "M5": m5_sweep}).trades[0]
        self.assertEqual(trade.scenario, 1)
        self.assertEqual(
            trade.decision.matching_setup_ids, ("M15@2026-10-15T10:15", "M5@2026-10-15T10:25")
        )

    def test_one_trade_per_setup(self):
        drift = [quiet(1.40040), quiet(1.40038), quiet(1.40036), quiet(1.40034), quiet(1.40032)]
        second_entry = [A, B1_EQ, B2, B3, quiet(B3[3])]
        result = backtest(entry_sequence(at(10, 30), after=drift + second_entry), htf())
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(len(result.decisions), 1)

    def test_close_above_htf_high_cancels_the_setup_only_when_enabled(self):
        breakout = (1.40060, 1.40110, 1.40055, 1.40105)
        m1 = [Candle(at(10, 30), *breakout)] + entry_sequence(at(10, 31))
        self.assertEqual(len(backtest(m1, htf()).trades), 1)
        self.assertEqual(backtest(m1, htf(), invalidate_on_close_above_htf_high=True).trades, ())

    def test_proximity_filter_only_when_enabled(self):
        # B1's high 1.40080 sits 2.0 pips under the 15m setup high 1.40100.
        m1 = entry_sequence(at(10, 30))
        self.assertEqual(backtest(m1, htf(), ltf_near_htf_high_pips=1.9).trades, ())
        self.assertEqual(len(backtest(m1, htf(), ltf_near_htf_high_pips=2.0).trades), 1)

    def test_invalid_parameters_are_rejected(self):
        for bad in (
            {"entry_fill": "limit"},
            {"same_bar_sl_tp": "TP_FIRST"},
            {"enabled_scenarios": (5,)},
            {"max_open_positions": 0},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                SellScenarioParams(**bad)


class TestJournal(unittest.TestCase):
    """Spec §10: one row per trade and per skipped signal, in UTC and UTC+6."""

    def test_trade_row_carries_every_column_in_both_time_zones(self):
        result = backtest(entry_sequence(at(10, 30), after=((1.40040, 1.40041, 1.39650, 1.39700),)), htf())
        (row,) = journal_rows(result)
        self.assertEqual(set(JOURNAL_COLUMNS) - set(row), set())
        self.assertEqual(row["event"], "TRADE")
        self.assertEqual(row["scenario"], 1)
        self.assertEqual(row["entry_time_utc"], "2026-10-15 10:34")
        self.assertEqual(row["entry_time_utc6"], "2026-10-15 16:34")
        self.assertEqual(row["exit_reason"], "TP")
        self.assertEqual(row["skip_reason"], "")

    def test_skip_row_names_the_reason(self):
        result = backtest(entry_sequence(at(10, 30), b1=B1_SW, b2=B2_DOJI), htf(), enabled_scenarios=(1, 2))
        (row,) = journal_rows(result)
        self.assertEqual(row["event"], "SKIPPED")
        self.assertEqual(row["skip_reason"], "SCENARIO_DISABLED")
        self.assertEqual(row["doji_position"], "2")


def synthetic_history(seed: int, days: int = 3):
    """Random walk in whole pips over the 07:00-21:00 UTC session, with 5m and 15m bars built from it."""
    rng = random.Random(seed)
    m1 = []
    price = 140000  # points
    monday = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)
    for day in range(days):
        start = monday + timedelta(days=day)
        for minute in range(14 * 60):
            o = price
            c = o + rng.choice((-20, -10, 0, 10, 20))
            h = max(o, c) + rng.choice((0, 0, 10, 20))
            low = min(o, c) - rng.choice((0, 0, 10, 20))
            m1.append(Candle(start + minute * M1, o / 1e5, h / 1e5, low / 1e5, c / 1e5))
            price = c
    return m1, {"M5": resample_m1_to_htf(m1, 5), "M15": resample_m1_to_htf(m1, 15)}


def signature(decision) -> tuple:
    return (
        decision.signal_time,
        decision.scenario,
        decision.setup.setup_id,
        decision.stop_loss,
        decision.skip_reason,
    )


class TestNoLookAhead(unittest.TestCase):
    """Spec §11 replay and mutation tests."""

    @classmethod
    def setUpClass(cls):
        cls.m1, cls.htf = synthetic_history(seed=7)
        cls.batch = [signature(d) for d in run_sell_backtest(cls.m1, cls.htf).decisions]

    def test_history_has_enough_signals_for_the_checks(self):
        self.assertGreaterEqual(len(self.batch), 5)

    def test_streaming_replay_matches_batch(self):
        engine = SellScenarioEngine()
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

    def test_changing_candles_after_t_leaves_earlier_signals_unchanged(self):
        cut = self.m1[len(self.m1) // 2].timestamp

        def bump(c):
            return Candle(c.timestamp, c.open + 0.00037, c.high + 0.00052, c.low + 0.00037, c.close + 0.00037)

        def mutate(candles, duration):
            return [c if c.timestamp + duration <= cut else bump(c) for c in candles]

        m1 = mutate(self.m1, M1)
        htf_bars = {tf: mutate(candles, HTF_DELTAS[tf]) for tf, candles in self.htf.items()}
        after = [signature(d) for d in run_sell_backtest(m1, htf_bars).decisions]
        before_cut = [s for s in self.batch if s[0] <= cut]
        self.assertTrue(before_cut)
        self.assertEqual([s for s in after if s[0] <= cut], before_cut)


class TestLiveBridge(unittest.TestCase):
    """bridge/executor.py with the Sell Scenarios engine: TP from the live bid, never from close(B3)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_sell_scenarios_")
        self.client = DWXClient(mt4_files_dir=self.temp_dir, initial_backoff_ms=10, max_backoff_ms=100)
        now = datetime.now(UTC)
        self.client.write_mock_account(balance=5000.00, equity=5000.00, timestamp=now)
        self.executor = BridgeExecutor(
            symbol="USDCAD",
            dwx_client=self.client,
            rule_engine=SellScenarioEngine(),
            exact_risk_sizing=True,
            confirmation_timeout_sec=0.01,
        )
        self.signal = TradeSignal(
            direction="SELL",
            entry_price=1.40042,
            stop_loss=1.40081,
            take_profit=1.39652,
            risk_distance=0.00039,
            reward_distance=0.00390,
            reward_risk_ratio=10.0,
            sweep_type="SELL_S1",
            timeframe="M1",
            timestamp=now,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tp_is_ten_times_the_risk_from_the_live_bid(self):
        self.client.write_mock_market_data("USDCAD", bid=1.40040, ask=1.40041)
        record = self.executor._execute_signal(self.signal)
        self.assertEqual(record.sl_price, Decimal("1.40081"))
        self.assertEqual(record.tp_price, Decimal("1.39630"))

    def test_no_order_when_the_ask_is_at_or_above_the_sl(self):
        for bid, ask in ((1.40081, 1.40082), (1.40080, 1.40081)):
            with self.subTest(bid=bid, ask=ask):
                self.executor.processed_signal_keys.clear()  # same signal twice: lift the duplicate guard
                self.client.write_mock_market_data("USDCAD", bid=bid, ask=ask)
                record = self.executor._execute_signal(self.signal)
                self.assertEqual(record.status, "REJECTED")
                self.assertEqual(record.rejection_reason, "SL_NOT_ABOVE_ASK")
                self.assertFalse(self.client.commands_file.exists())

    def write_ea_account(self, symbol, bid, ask, usdcad_pair=None):
        """DWX_Account.txt as DWX_Server.mq4 writes it: chart quote on top, pairs keyed with "m"."""
        data = {
            "account_number": 1, "company": "Exness", "account_name": "test", "currency": "USD",
            "balance": 5000.00, "equity": 5000.00, "margin": 0.0, "free_margin": 5000.00, "profit": 0.0,
            "leverage": 2000, "symbol": symbol, "bid": bid, "ask": ask, "spread_pips": 0.1, "digits": 5,
            "pairs": {
                "EURUSDm": {"bid": 1.16000, "ask": 1.16002, "spread_pips": 0.2},
                "USDCADm": {**(usdcad_pair or {"bid": bid, "ask": ask}), "spread_pips": 0.1},
            },
            "timestamp": "2026-10-26 10:34:00", "open_orders_count": 0, "orders": [],
        }
        self.client.write_mock_account(raw_json_str=json.dumps(data) + "\n")

    def test_tp_from_the_quote_the_ea_writes(self):
        self.write_ea_account("USDCAD", 1.40040, 1.40041)  # no DWX_Market_Data.txt, as in production
        self.assertEqual(self.executor._execute_signal(self.signal).tp_price, Decimal("1.39630"))

    def test_quote_from_pairs_when_the_chart_shows_another_symbol(self):
        self.write_ea_account("EURUSDm", 1.16000, 1.16002, usdcad_pair={"bid": 1.40040, "ask": 1.40041})
        self.assertEqual(self.executor._execute_signal(self.signal).tp_price, Decimal("1.39630"))

    def test_ea_ask_at_the_sl_sends_nothing(self):
        self.write_ea_account("USDCAD", 1.40080, 1.40081)
        record = self.executor._execute_signal(self.signal)
        self.assertEqual(record.rejection_reason, "SL_NOT_ABOVE_ASK")
        self.assertFalse(self.client.commands_file.exists())

    def test_no_live_quote_sends_nothing(self):
        self.write_ea_account("EURUSDm", 1.16000, 1.16002, usdcad_pair={"bid": 0.0, "ask": 0.0})
        record = self.executor._execute_signal(self.signal)
        self.assertEqual(record.status, "REJECTED")
        self.assertEqual(record.rejection_reason, "NO_LIVE_QUOTE")
        self.assertFalse(self.client.commands_file.exists())

    def test_stale_account_file_gives_no_quote(self):
        self.write_ea_account("USDCAD", 1.40040, 1.40041)
        self.assertEqual(self.client.read_account_quote("USDCADm", 5.0), (Decimal("1.4004"), Decimal("1.40041")))
        old = time.time() - 60
        os.utime(self.client.account_file, (old, old))
        self.assertIsNone(self.client.read_account_quote("USDCAD", 5.0))

    def test_factory_takes_session_and_position_limit_from_config(self):
        cfg = AppConfig(
            mt4_files_dir=Path(self.temp_dir),
            session_start_hour=7,
            session_end_hour=21,
            max_open_trades=None,
        )
        engine = build_sell_scenario_engine(cfg, "USDCADm")
        self.assertEqual((engine.params.session_start_hour, engine.params.session_end_hour), (7, 21))
        self.assertIsNone(engine.params.max_open_positions)

    def test_max_open_trades_zero_means_no_limit(self):
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text(f"MT4_FILES_DIR={self.temp_dir}\nMAX_OPEN_TRADES=0\n", encoding="utf-8")
        self.assertIsNone(load_config(env_file).max_open_trades)


if __name__ == "__main__":
    unittest.main()
