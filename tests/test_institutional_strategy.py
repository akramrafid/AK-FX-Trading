"""
Unit and Integration Tests for Institutional 5-Pillar Strategy Architecture.

Validates:
Pillar 1: Key Liquidity Pools (Asian Session 00:00-07:00 UTC High/Low & PDH/PDL sweeps with >= 2.0 pips depth).
Pillar 2: True Invalidation Stop-Loss (anchored at HTF sweep wick extreme with min 6.0 pips distance).
Pillar 3: Confirmation Quality (Displacement candle body >= 1.2x average M1 body).
Pillar 4: Higher-Timeframe Trend Filter (H1 50 EMA directional alignment).
Pillar 5: Dynamic Scaling & Breakeven (Bank 70% partial at +2.0R, move SL to BE, trail 30% runner to +5.0R).
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.models import Candle, Direction, SweepType, TradeSignal
from engine.sweep_detector import detect_key_liquidity_sweep
from engine.confirmation import evaluate_3_candles
from engine.rule_engine import RuleEngine
from engine.backtester import BacktestConfig, BacktestEngine, BacktestTrade


def make_candle(
    dt: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    vol: float = 100.0,
) -> Candle:
    return Candle(
        timestamp=dt,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
    )


class TestPillar1KeyLiquidityPools(unittest.TestCase):
    """Pillar 1: Asian Session & PDH/PDL Key Liquidity Sweeps with Depth Filter."""

    def test_asian_session_high_sweep_with_depth(self):
        asia_high = 1.0850
        asia_low = 1.0800
        min_depth = 2.0 * 0.0001  # 2.0 pips

        # Candle penetrates Asian high by 2.5 pips and closes back below
        sweep_candle = make_candle(
            datetime(2023, 1, 2, 8, 15, tzinfo=timezone.utc),
            o=1.0845,
            h=1.08525,  # 2.5 pips above 1.0850
            l=1.0840,
            c=1.0848,  # Closes back below 1.0850
        )
        event = detect_key_liquidity_sweep(
            candle=sweep_candle,
            asia_high=asia_high,
            asia_low=asia_low,
            pdh=None,
            pdl=None,
            min_sweep_dist=min_depth,
            candle_index=10,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, Direction.SELL)
        self.assertEqual(event.sweep_type, SweepType.ASIAN_RANGE)
        self.assertEqual(event.swept_level, asia_high)
        self.assertEqual(event.extreme_price, 1.08525)

    def test_asian_session_low_sweep_rejected_if_depth_insufficient(self):
        asia_high = 1.0850
        asia_low = 1.0800
        min_depth = 2.0 * 0.0001  # 2.0 pips

        # Candle penetrates by only 0.8 pips (< 2.0 pips)
        shallow_candle = make_candle(
            datetime(2023, 1, 2, 8, 15, tzinfo=timezone.utc),
            o=1.0805,
            l=1.07992,  # 0.8 pips below 1.0800
            h=1.0810,
            c=1.0802,
        )
        event = detect_key_liquidity_sweep(
            candle=shallow_candle,
            asia_high=asia_high,
            asia_low=asia_low,
            pdh=None,
            pdl=None,
            min_sweep_dist=min_depth,
            candle_index=10,
        )
        self.assertIsNone(event)

    def test_previous_day_high_sweep(self):
        pdh = 1.0920
        min_depth = 2.0 * 0.0001

        sweep_candle = make_candle(
            datetime(2023, 1, 2, 14, 30, tzinfo=timezone.utc),
            o=1.0915,
            h=1.09230,  # 3.0 pips above PDH
            l=1.0910,
            c=1.0918,  # Closes back below PDH
        )
        event = detect_key_liquidity_sweep(
            candle=sweep_candle,
            asia_high=None,
            asia_low=None,
            pdh=pdh,
            pdl=None,
            min_sweep_dist=min_depth,
            candle_index=20,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, Direction.SELL)
        self.assertEqual(event.sweep_type, SweepType.PREV_DAY)
        self.assertEqual(event.swept_level, pdh)
        self.assertEqual(event.extreme_price, 1.09230)


class TestPillar2TrueInvalidationSL(unittest.TestCase):
    """Pillar 2: True Invalidation SL Anchored at HTF Sweep Wick Extreme."""

    def test_sweep_wick_sl_sell(self):
        # 3 confirming bearish M1 candles
        c1 = make_candle(datetime(2023, 1, 2, 8, 21, tzinfo=timezone.utc), 1.0850, 1.0851, 1.0845, 1.0846)
        c2 = make_candle(datetime(2023, 1, 2, 8, 22, tzinfo=timezone.utc), 1.0846, 1.0847, 1.0840, 1.0841)
        c3 = make_candle(datetime(2023, 1, 2, 8, 23, tzinfo=timezone.utc), 1.0841, 1.0842, 1.0834, 1.0835)

        sweep_high = 1.08650  # HTF sweep wick high
        spread = 1.0  # 1 pip spread buffer

        signal = evaluate_3_candles(
            confirming_candles=[c1, c2, c3],
            direction=Direction.SELL,
            buffer_pips=0.0,
            spread_pips=spread,
            pip_size=0.0001,
            reward_risk_ratio=5.0,
            sweep_extreme_price=sweep_high,
            use_sweep_wick_sl=True,
            min_risk_pips=6.0,
        )
        self.assertIsNotNone(signal)
        # For SELL with sweep wick SL: SL = sweep_high + spread = 1.08650 + 0.00010 = 1.08660
        expected_sl = 1.08660
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)
        # Entry at c3.close = 1.0835
        expected_risk = expected_sl - 1.0835  # 0.0031 (31 pips)
        self.assertAlmostEqual(signal.risk_distance, expected_risk, places=5)
        self.assertAlmostEqual(signal.take_profit, 1.0835 - (5.0 * expected_risk), places=5)

    def test_minimum_risk_distance_clamping(self):
        # Very tight setup where risk distance would be only 2 pips
        c1 = make_candle(datetime(2023, 1, 2, 8, 21, tzinfo=timezone.utc), 1.0840, 1.0842, 1.0839, 1.0841)
        c2 = make_candle(datetime(2023, 1, 2, 8, 22, tzinfo=timezone.utc), 1.0841, 1.0843, 1.0840, 1.0842)
        c3 = make_candle(datetime(2023, 1, 2, 8, 23, tzinfo=timezone.utc), 1.0842, 1.0844, 1.0841, 1.0843)

        sweep_low = 1.08410  # Only 2 pips below entry 1.0843
        signal = evaluate_3_candles(
            confirming_candles=[c1, c2, c3],
            direction=Direction.BUY,
            pip_size=0.0001,
            reward_risk_ratio=5.0,
            sweep_extreme_price=sweep_low,
            use_sweep_wick_sl=True,
            min_risk_pips=6.0,  # Minimum 6 pips enforced
        )
        self.assertIsNotNone(signal)
        # Clamped to 6.0 pips minimum risk
        self.assertGreaterEqual(signal.risk_distance, 0.00060 - 1e-9)
        self.assertAlmostEqual(signal.stop_loss, signal.entry_price - 0.00060, places=5)


class TestPillar3ConfirmationDisplacement(unittest.TestCase):
    """Pillar 3: Confirmation Quality with Displacement Ratio."""

    def test_displacement_accepted_when_body_exceeds_threshold(self):
        # Avg M1 body is 2.0 pips. We require >= 1.2x (2.4 pips).
        # C2 has 3.0 pips body (1.0835 -> 1.0838).
        c1 = make_candle(datetime(2023, 1, 2, 8, 21, tzinfo=timezone.utc), 1.0830, 1.0833, 1.0829, 1.0832)
        c2 = make_candle(datetime(2023, 1, 2, 8, 22, tzinfo=timezone.utc), 1.0832, 1.0839, 1.0831, 1.0838)  # body = 6 pips
        c3 = make_candle(datetime(2023, 1, 2, 8, 23, tzinfo=timezone.utc), 1.0838, 1.0842, 1.0837, 1.0841)

        signal = evaluate_3_candles(
            confirming_candles=[c1, c2, c3],
            direction=Direction.BUY,
            pip_size=0.0001,
            min_displacement_ratio=1.2,
            avg_candle_body=0.00020,  # 2.0 pips avg body
        )
        self.assertIsNotNone(signal)

    def test_displacement_rejected_when_all_bodies_are_tiny(self):
        # Avg M1 body is 3.0 pips. We require >= 1.2x (3.6 pips).
        # All 3 candles have tiny 0.5 pip bodies (doji / indecision).
        c1 = make_candle(datetime(2023, 1, 2, 8, 21, tzinfo=timezone.utc), 1.0830, 1.0832, 1.0829, 1.08305)
        c2 = make_candle(datetime(2023, 1, 2, 8, 22, tzinfo=timezone.utc), 1.08305, 1.0832, 1.0830, 1.08310)
        c3 = make_candle(datetime(2023, 1, 2, 8, 23, tzinfo=timezone.utc), 1.08310, 1.0833, 1.0830, 1.08315)

        signal = evaluate_3_candles(
            confirming_candles=[c1, c2, c3],
            direction=Direction.BUY,
            pip_size=0.0001,
            min_displacement_ratio=1.2,
            avg_candle_body=0.00030,
        )
        self.assertIsNone(signal)


class TestPillar4HTFTrendFilter(unittest.TestCase):
    """Pillar 4: Higher-Timeframe Trend Alignment (H1 50 EMA Filter)."""

    def test_counter_trend_sweep_filtered_out(self):
        engine = RuleEngine.institutional_preset(h1_trend_filter=True)
        # Set running H1 EMA 50 at 1.0900 (downtrend relative to price 1.085x)
        engine.latest_h1_ema = 1.0900

        # Asian session candle (04:00 UTC) establishes asia_low = 1.0855
        asian_candle = make_candle(
            datetime(2023, 1, 2, 4, 0, tzinfo=timezone.utc),
            o=1.0860, h=1.0865, l=1.0855, c=1.0860,
        )
        engine.on_htf_candle(asian_candle, timeframe="M5")

        prev_candle = make_candle(
            datetime(2023, 1, 2, 10, 10, tzinfo=timezone.utc),
            o=1.0860, h=1.0865, l=1.0856, c=1.0858,
        )
        engine.on_htf_candle(prev_candle, timeframe="M5")

        # Attempt to arm a BUY sweep when candle closed at 1.0858 (< 1.0900 downtrend)
        sweep_candle = make_candle(
            datetime(2023, 1, 2, 10, 15, tzinfo=timezone.utc),
            o=1.0853,
            h=1.0860,
            l=1.0850,  # Sweeps asia_low (1.0855) by 5 pips (min depth 2.0 pips)
            c=1.0858,  # Below 1.0900 H1 EMA
        )
        armed = engine.on_htf_candle(sweep_candle, timeframe="M5")
        # Counter-trend BUY into H1 downtrend must be rejected
        self.assertIsNone(armed)

    def test_pro_trend_sweep_accepted(self):
        engine = RuleEngine.institutional_preset(h1_trend_filter=True)
        engine.latest_h1_ema = 1.0800  # Uptrend (price above 1.0800)

        # Asian session candle (04:00 UTC) establishes asia_low = 1.0840
        asian_candle = make_candle(
            datetime(2023, 1, 2, 4, 0, tzinfo=timezone.utc),
            o=1.0845, h=1.0850, l=1.0840, c=1.0845,
        )
        engine.on_htf_candle(asian_candle, timeframe="M5")

        prev_candle = make_candle(
            datetime(2023, 1, 2, 10, 10, tzinfo=timezone.utc),
            o=1.0850, h=1.0855, l=1.0845, c=1.0848,
        )
        engine.on_htf_candle(prev_candle, timeframe="M5")

        sweep_candle = make_candle(
            datetime(2023, 1, 2, 10, 15, tzinfo=timezone.utc),
            o=1.0842,
            h=1.0850,
            l=1.0835,  # Sweeps asia_low (1.0840) by 5 pips
            c=1.0845,  # 1.0845 > 1.0800 -> Pro-trend
        )
        armed = engine.on_htf_candle(sweep_candle, timeframe="M5")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.BUY)


class TestPillar5DynamicScalingAndBacktest(unittest.TestCase):
    """Pillar 5: Dynamic Scaling & Breakeven in Backtester."""

    def test_partial_bank_and_breakeven_milestone_buy(self):
        # Configure backtester with 70% partial at +2.0R, BE at +2.0R, runner to +5.0R
        config = BacktestConfig.institutional_preset(
            initial_balance=10000.0,
            risk_pct=1.0,
            partial_bank_trigger_r=2.0,
            partial_bank_pct=0.70,
            breakeven_trigger_r=2.0,
            breakeven_buffer_pips=0.5,
            spread_pips=0.0,
            slippage_pips=0.0,
        )
        engine = BacktestEngine(config=config)

        # Create active BUY trade: entry = 1.0800, SL = 1.0790 (risk = 10 pips), TP = 1.0850 (+5R)
        signal = TradeSignal(
            direction="BUY",
            entry_price=1.0800,
            stop_loss=1.0790,
            take_profit=1.0850,
            risk_distance=0.0010,  # 10 pips
            reward_distance=0.0050,  # 50 pips (+5R)
            reward_risk_ratio=5.0,
            partial_bank_r=2.0,
            partial_bank_pct=0.70,
            breakeven_trigger_r=2.0,
        )

        active = engine._create_active_trade(1, signal, datetime(2023, 1, 2, 9, 0, tzinfo=timezone.utc), 10000.0)
        self.assertEqual(active["partial_bank_r"], 2.0)
        self.assertEqual(active["partial_bank_pct"], 0.70)
        self.assertFalse(active["partial_banked"])

        # Bar 1: Price rallies to +2.5R (1.0825). Partial bank triggered!
        bar1 = make_candle(datetime(2023, 1, 2, 9, 1, tzinfo=timezone.utc), 1.0805, 1.0825, 1.0802, 1.0822)
        closed, balance, active = engine._manage_position_on_bar(bar1, active, 10000.0)
        self.assertIsNone(closed)  # Trade still open (runner remaining)
        self.assertTrue(active["partial_banked"])
        self.assertTrue(active["sl_moved_to_be"])
        # SL moved to entry + 0.5 pip buffer = 1.08005
        self.assertAlmostEqual(active["stop_loss"], 1.08005, places=5)
        # Banked cash was added to balance
        self.assertGreater(balance, 10000.0)

        # Bar 2: Price retraces back down to 1.0800, hitting the breakeven SL (1.08005)
        bar2 = make_candle(datetime(2023, 1, 2, 9, 2, tzinfo=timezone.utc), 1.0820, 1.0821, 1.0799, 1.0800)
        closed, final_balance, active = engine._manage_position_on_bar(bar2, active, balance)
        self.assertIsNotNone(closed)
        self.assertIsNone(active)
        self.assertEqual(closed.exit_reason, "BE")
        self.assertTrue(closed.partial_banked)
        # Realized R = (2.0 * 0.70) + (0.0 * 0.30) = +1.40R!
        self.assertAlmostEqual(closed.realized_r, 1.40, places=2)
        self.assertGreater(closed.pnl_currency, 0.0)

    def test_full_take_profit_with_partial_bank_sell(self):
        config = BacktestConfig.institutional_preset(
            initial_balance=10000.0,
            risk_pct=1.0,
            partial_bank_trigger_r=2.0,
            partial_bank_pct=0.70,
            breakeven_trigger_r=2.0,
            breakeven_buffer_pips=0.5,
            spread_pips=0.0,
            slippage_pips=0.0,
        )
        engine = BacktestEngine(config=config)

        # SELL trade: entry = 1.0850, SL = 1.0860 (risk = 10 pips), TP = 1.0800 (+5R)
        signal = TradeSignal(
            direction="SELL",
            entry_price=1.0850,
            stop_loss=1.0860,
            take_profit=1.0800,
            risk_distance=0.0010,
            reward_distance=0.0050,
            reward_risk_ratio=5.0,
            partial_bank_r=2.0,
            partial_bank_pct=0.70,
            breakeven_trigger_r=2.0,
        )

        active = engine._create_active_trade(1, signal, datetime(2023, 1, 2, 9, 0, tzinfo=timezone.utc), 10000.0)

        # Bar 1: Drops to 1.0828 (+2.2R), triggers partial bank & BE
        bar1 = make_candle(datetime(2023, 1, 2, 9, 1, tzinfo=timezone.utc), 1.0845, 1.0848, 1.0828, 1.0830)
        closed, balance, active = engine._manage_position_on_bar(bar1, active, 10000.0)
        self.assertIsNone(closed)
        self.assertTrue(active["partial_banked"])

        # Bar 2: Drops all the way to 1.0795, hitting full TP (1.0800)
        bar2 = make_candle(datetime(2023, 1, 2, 9, 2, tzinfo=timezone.utc), 1.0830, 1.0832, 1.0795, 1.0798)
        closed, final_balance, active = engine._manage_position_on_bar(bar2, active, balance)
        self.assertIsNotNone(closed)
        self.assertEqual(closed.exit_reason, "TP")
        # Realized R = (2.0 * 0.70) + (5.0 * 0.30) = 1.40 + 1.50 = +2.90R!
        self.assertAlmostEqual(closed.realized_r, 2.90, places=2)
        self.assertGreater(final_balance, balance)


if __name__ == "__main__":
    unittest.main()
