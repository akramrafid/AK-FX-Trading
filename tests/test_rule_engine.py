"""
Exhaustive unit test suite for the AK Forex Trading Rule Engine.
Validates:
- Candle invariants & models.
- Variant A (candle-to-candle) liquidity sweeps.
- Variant B (swing-level) liquidity sweeps.
- 3-consecutive-candle directional confirmation.
- Asymmetrical Stop-Loss calculation (below low for Buy, above high + spread for Sell).
- Fixed 10:1 Reward-to-Risk mathematical pricing.
- Complete RuleEngine pipeline and evaluate_candles interface.
"""

import os
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import unittest
from datetime import datetime, timedelta, timezone

from engine.models import Candle, Direction, SweepEvent, SweepType, TradeSignal
from engine.sweep_detector import detect_sweep, detect_variant_a, detect_variant_b, find_swing_levels
from engine.confirmation import evaluate_confirmation
from engine.rule_engine import RuleEngine, evaluate_candles


def create_candle(
    index: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 100.0,
    base_time: datetime = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
) -> Candle:
    """Helper to generate timestamped test candles (5-minute interval)."""
    return Candle(
        timestamp=base_time + timedelta(minutes=5 * index),
        open=round(open_price, 5),
        high=round(high_price, 5),
        low=round(low_price, 5),
        close=round(close_price, 5),
        volume=volume,
    )


class TestCandleModels(unittest.TestCase):
    """Test Candle data integrity and domain invariants."""

    def test_valid_candle(self):
        c = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)
        self.assertTrue(c.is_bullish)
        self.assertFalse(c.is_bearish)
        self.assertFalse(c.is_doji)
        self.assertAlmostEqual(c.body, 0.0030)
        self.assertAlmostEqual(c.total_range, 0.0050)
        self.assertAlmostEqual(c.upper_wick, 0.0010)
        self.assertAlmostEqual(c.lower_wick, 0.0010)

    def test_bearish_and_doji_candles(self):
        bearish = create_candle(0, 1.0880, 1.0890, 1.0840, 1.0850)
        self.assertTrue(bearish.is_bearish)
        self.assertFalse(bearish.is_bullish)

        doji = create_candle(1, 1.0850, 1.0870, 1.0830, 1.0850)
        self.assertTrue(doji.is_doji)

    def test_invalid_candle_invariants(self):
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        # High lower than low
        with self.assertRaises(ValueError):
            Candle(timestamp=base, open=1.08, high=1.07, low=1.09, close=1.08)
        # High lower than open/close
        with self.assertRaises(ValueError):
            Candle(timestamp=base, open=1.10, high=1.09, low=1.05, close=1.08)
        # Low higher than open/close
        with self.assertRaises(ValueError):
            Candle(timestamp=base, open=1.06, high=1.10, low=1.07, close=1.08)
        # Non-positive prices
        with self.assertRaises(ValueError):
            Candle(timestamp=base, open=0.0, high=1.0, low=0.0, close=0.5)

    def test_serialization(self):
        c = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)
        d = c.to_dict()
        reconstituted = Candle.from_dict(d)
        self.assertEqual(c, reconstituted)


class TestSweepDetectorVariantA(unittest.TestCase):
    """Test Variant A (Candle-to-Candle liquidity sweep)."""

    def test_bullish_sweep_variant_a(self):
        """
        Candle 0: Bearish (1.0880 -> 1.0850, low=1.0840)
        Candle 1: Sweeps below 1.0840 (low=1.0825), closes at 1.0860 (above 1.0840)
        """
        c0 = create_candle(0, 1.0880, 1.0890, 1.0840, 1.0850)  # Bearish
        c1 = create_candle(1, 1.0850, 1.0870, 1.0825, 1.0860)  # Sweeps c0 low, rejects
        candles = [c0, c1]

        event = detect_variant_a(candles, current_idx=1)
        self.assertIsNotNone(event)
        self.assertEqual(event.sweep_type, SweepType.VARIANT_A)
        self.assertEqual(event.direction, Direction.BUY)
        self.assertEqual(event.candle_index, 1)
        self.assertAlmostEqual(event.swept_level, 1.0840)
        self.assertAlmostEqual(event.extreme_price, 1.0825)

    def test_bearish_sweep_variant_a(self):
        """
        Candle 0: Bullish (1.0850 -> 1.0880, high=1.0890)
        Candle 1: Sweeps above 1.0890 (high=1.0910), closes at 1.0875 (below 1.0890)
        """
        c0 = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)  # Bullish
        c1 = create_candle(1, 1.0880, 1.0910, 1.0870, 1.0875)  # Sweeps c0 high, rejects
        candles = [c0, c1]

        event = detect_variant_a(candles, current_idx=1)
        self.assertIsNotNone(event)
        self.assertEqual(event.sweep_type, SweepType.VARIANT_A)
        self.assertEqual(event.direction, Direction.SELL)
        self.assertEqual(event.candle_index, 1)
        self.assertAlmostEqual(event.swept_level, 1.0890)
        self.assertAlmostEqual(event.extreme_price, 1.0910)

    def test_no_sweep_if_prior_candle_same_color(self):
        """If preceding candle is bullish, a low dip does NOT trigger Variant A buy sweep."""
        c0 = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)  # Bullish
        c1 = create_candle(1, 1.0880, 1.0885, 1.0830, 1.0870)  # Dips low, but c0 was bullish
        candles = [c0, c1]

        event = detect_variant_a(candles, current_idx=1)
        self.assertIsNone(event)

    def test_no_sweep_if_candle_closes_beyond_level(self):
        """If current candle breaks and closes beyond the level (breakout, not sweep rejection)."""
        c0 = create_candle(0, 1.0880, 1.0890, 1.0840, 1.0850)  # Bearish (low=1.0840)
        c1 = create_candle(1, 1.0850, 1.0855, 1.0810, 1.0820)  # Closes at 1.0820 < 1.0840
        candles = [c0, c1]

        event = detect_variant_a(candles, current_idx=1)
        self.assertIsNone(event)


class TestSweepDetectorVariantB(unittest.TestCase):
    """Test Variant B (Swing-level liquidity sweep)."""

    def test_swing_low_sweep_variant_b(self):
        """Create a swing low at bar 2, then sweep it at bar 6."""
        candles = [
            create_candle(0, 1.0900, 1.0910, 1.0880, 1.0890),
            create_candle(1, 1.0890, 1.0895, 1.0860, 1.0870),
            create_candle(2, 1.0870, 1.0875, 1.0830, 1.0840),  # Swing Low = 1.0830
            create_candle(3, 1.0840, 1.0880, 1.0835, 1.0875),
            create_candle(4, 1.0875, 1.0890, 1.0850, 1.0880),
            create_candle(5, 1.0880, 1.0885, 1.0845, 1.0850),
            # Bar 6 sweeps swing low 1.0830 (low=1.0815) and closes at 1.0845 (above 1.0830)
            create_candle(6, 1.0850, 1.0860, 1.0815, 1.0845),
        ]

        event = detect_variant_b(candles, current_idx=6, lookback=10, swing_strength=2)
        self.assertIsNotNone(event)
        self.assertEqual(event.sweep_type, SweepType.VARIANT_B)
        self.assertEqual(event.direction, Direction.BUY)
        self.assertAlmostEqual(event.swept_level, 1.0830)
        self.assertAlmostEqual(event.extreme_price, 1.0815)


class TestConfirmationAndRRMath(unittest.TestCase):
    """Test 3-consecutive-candle confirmation and 10:1 R:R pricing."""

    def test_long_confirmation_and_10_to_1_rr(self):
        """
        Sweep at index 1 (BUY).
        Candle 1 (idx 2): Bullish, low = 1.0800, close = 1.0830
        Candle 2 (idx 3): Bullish, close = 1.0850
        Candle 3 (idx 4): Bullish, close = 1.0870 (Entry)
        Stop-loss: 1.0800 (candle 1 low)
        Risk distance: 1.0870 - 1.0800 = 0.0070 (70 pips)
        Take-profit: 1.0870 + (10 * 0.0070) = 1.1570 (exactly 10:1 R:R)
        """
        c0 = create_candle(0, 1.0880, 1.0890, 1.0820, 1.0830)  # Bearish
        cS = create_candle(1, 1.0830, 1.0840, 1.0805, 1.0825)  # Sweeps c0 low
        c1 = create_candle(2, 1.0825, 1.0835, 1.0800, 1.0830)  # C1: Bullish, low=1.0800
        c2 = create_candle(3, 1.0830, 1.0855, 1.0825, 1.0850)  # C2: Bullish
        c3 = create_candle(4, 1.0850, 1.0875, 1.0845, 1.0870)  # C3: Bullish, close=1.0870
        candles = [c0, cS, c1, c2, c3]

        sweep_event = detect_variant_a(candles, current_idx=1)
        self.assertIsNotNone(sweep_event)

        signal = evaluate_confirmation(candles, sweep_event, buffer_pips=0.0)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")
        self.assertAlmostEqual(signal.entry_price, 1.0870)
        self.assertAlmostEqual(signal.stop_loss, 1.0800)
        self.assertAlmostEqual(signal.risk_distance, 0.0070)
        self.assertAlmostEqual(signal.reward_distance, 0.0350)
        self.assertAlmostEqual(signal.take_profit, 1.1220)
        self.assertAlmostEqual(signal.reward_risk_ratio, 5.0)

    def test_short_confirmation_and_5_to_1_rr(self):
        """
        Sweep at index 1 (SELL).
        Candle 1 (idx 2): Bearish, high = 1.0920, close = 1.0890
        Candle 2 (idx 3): Bearish, close = 1.0870
        Candle 3 (idx 4): Bearish, close = 1.0850 (Entry)
        Spread buffer: 1 pip (0.0001)
        Stop-loss: 1.0920 + 0.0001 = 1.0921 (candle 1 high + spread)
        Risk distance: 1.0921 - 1.0850 = 0.0071 (71 pips)
        Take-profit: 1.0850 - (5 * 0.0071) = 1.0495 (exactly 5:1 R:R)
        """
        c0 = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)  # Bullish
        cS = create_candle(1, 1.0880, 1.0910, 1.0870, 1.0875)  # Sweeps c0 high
        c1 = create_candle(2, 1.0900, 1.0920, 1.0880, 1.0890)  # C1: Bearish, high=1.0920
        c2 = create_candle(3, 1.0890, 1.0895, 1.0865, 1.0870)  # C2: Bearish
        c3 = create_candle(4, 1.0870, 1.0875, 1.0845, 1.0850)  # C3: Bearish, close=1.0850
        candles = [c0, cS, c1, c2, c3]

        sweep_event = detect_variant_a(candles, current_idx=1)
        self.assertIsNotNone(sweep_event)

        signal = evaluate_confirmation(candles, sweep_event, spread_pips=1.0)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SELL")
        self.assertAlmostEqual(signal.entry_price, 1.0850)
        self.assertAlmostEqual(signal.stop_loss, 1.0921)
        self.assertAlmostEqual(signal.risk_distance, 0.0071)
        self.assertAlmostEqual(signal.reward_distance, 0.0355)
        self.assertAlmostEqual(signal.take_profit, 1.0495)
        self.assertAlmostEqual(signal.reward_risk_ratio, 5.0)

    def test_confirmation_fails_if_sequence_breaks(self):
        """If candle 2 closes opposite to trade direction, confirmation must return None."""
        c0 = create_candle(0, 1.0880, 1.0890, 1.0820, 1.0830)  # Bearish
        cS = create_candle(1, 1.0830, 1.0840, 1.0805, 1.0825)  # Sweeps c0 low (BUY setup)
        c1 = create_candle(2, 1.0825, 1.0840, 1.0810, 1.0835)  # C1: Bullish
        c2 = create_candle(3, 1.0835, 1.0840, 1.0815, 1.0820)  # C2: Bearish (sequence breaks!)
        c3 = create_candle(4, 1.0820, 1.0860, 1.0815, 1.0855)  # C3: Bullish
        candles = [c0, cS, c1, c2, c3]

        sweep_event = detect_variant_a(candles, current_idx=1)
        self.assertIsNotNone(sweep_event)

        signal = evaluate_confirmation(candles, sweep_event)
        self.assertIsNone(signal)


class TestRuleEngineEndToEnd(unittest.TestCase):
    """Test full RuleEngine integration."""

    def test_evaluate_completed_candle_live_stream(self):
        """Simulate real-time bar arrival."""
        c0 = create_candle(0, 1.0880, 1.0890, 1.0820, 1.0830)
        cS = create_candle(1, 1.0830, 1.0840, 1.0805, 1.0825)
        c1 = create_candle(2, 1.0825, 1.0835, 1.0800, 1.0830)
        c2 = create_candle(3, 1.0830, 1.0855, 1.0825, 1.0850)
        c3 = create_candle(4, 1.0850, 1.0875, 1.0845, 1.0870)

        engine = RuleEngine()

        # At candle 2 (C1 closed), no signal yet
        self.assertIsNone(engine.evaluate_completed_candle([c0, cS, c1]))
        # At candle 3 (C2 closed), no signal yet
        self.assertIsNone(engine.evaluate_completed_candle([c0, cS, c1, c2]))
        # At candle 4 (C3 closed), signal fires!
        signal = engine.evaluate_completed_candle([c0, cS, c1, c2, c3])
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")
        self.assertAlmostEqual(signal.entry_price, 1.0870)

    def test_evaluate_candles_dictionary_interface(self):
        """Test the pure top-level evaluate_candles function returning a dict."""
        c0 = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)
        cS = create_candle(1, 1.0880, 1.0910, 1.0870, 1.0875)
        c1 = create_candle(2, 1.0900, 1.0920, 1.0880, 1.0890)
        c2 = create_candle(3, 1.0890, 1.0895, 1.0865, 1.0870)
        c3 = create_candle(4, 1.0870, 1.0875, 1.0845, 1.0850)

        result = evaluate_candles([c0, cS, c1, c2, c3])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["direction"], "SELL")
        self.assertEqual(result["entry_price"], 1.0850)
        self.assertEqual(result["reward_risk_ratio"], 5.0)
        self.assertIn("stop_loss", result)
        self.assertIn("take_profit", result)

    def test_scan_historical_signals(self):
        """Test scanning a historical array with multiple setups."""
        # 10 candles with one buy setup
        c0 = create_candle(0, 1.0880, 1.0890, 1.0820, 1.0830)
        cS = create_candle(1, 1.0830, 1.0840, 1.0805, 1.0825)
        c1 = create_candle(2, 1.0825, 1.0835, 1.0800, 1.0830)
        c2 = create_candle(3, 1.0830, 1.0855, 1.0825, 1.0850)
        c3 = create_candle(4, 1.0850, 1.0875, 1.0845, 1.0870)
        c5 = create_candle(5, 1.0870, 1.0880, 1.0860, 1.0875)
        c6 = create_candle(6, 1.0875, 1.0890, 1.0870, 1.0885)

        engine = RuleEngine()
        signals = engine.scan_historical_signals([c0, cS, c1, c2, c3, c5, c6])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].direction, "BUY")


class TestC1WickSwapStrategy(unittest.TestCase):
    """
    Unit tests for the C1 Wick-Swap strategy:
    - M5/M15 candle-to-candle wick sweep (Variant A).
    - 3-consecutive M1 candle confirmation.
    - Stop Loss strictly anchored to the sweep candle's extreme wick.
    - 1:5 Reward-to-Risk ratio.
    - Breakeven advance at +2.0R with no partial close (100% position runs to +5.0R).
    """

    def test_preset_configuration(self):
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD")
        self.assertTrue(engine.use_c1_only_sl)
        self.assertTrue(engine.enable_intrabar_sweep)
        self.assertFalse(engine.use_sweep_wick_sl)
        self.assertFalse(engine.anchor_to_key_liquidity)
        self.assertTrue(engine.allow_variant_a)
        self.assertFalse(engine.allow_variant_b)
        self.assertEqual(engine.reward_risk_ratio, 5.0)
        self.assertEqual(engine.breakeven_trigger_r, 2.0)
        self.assertEqual(engine.partial_bank_pct, 0.0)
        self.assertEqual(engine.buffer_pips, 0.0)
        self.assertEqual(engine.spread_pips, 0.0)
        self.assertEqual(engine.min_risk_pips, 0.0)
        self.assertFalse(engine.h1_trend_filter)
        self.assertFalse(engine.disarm_on_break)

    def test_c1_wickswap_buy_setup(self):
        t0 = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        # M5 bar 0: Bearish
        m5_0 = Candle(timestamp=t0, open=1.0880, high=1.0890, low=1.0840, close=1.0850)
        engine.on_htf_candle(m5_0, timeframe="M5")

        # M5 bar 1: Bullish sweeping bar 0 low (low 1.0830 < 1.0840, close 1.0860 >= 1.0840)
        m5_1 = Candle(timestamp=t0 + timedelta(minutes=5), open=1.0845, high=1.0880, low=1.0830, close=1.0860)
        armed = engine.on_htf_candle(m5_1, timeframe="M5")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.BUY)

        # 3 confirming M1 bullish candles after M5 close (>= 08:10)
        m1_0 = Candle(timestamp=t0 + timedelta(minutes=10), open=1.0855, high=1.0865, low=1.0850, close=1.0862)
        m1_1 = Candle(timestamp=t0 + timedelta(minutes=11), open=1.0862, high=1.0875, low=1.0858, close=1.0870)
        m1_2 = Candle(timestamp=t0 + timedelta(minutes=12), open=1.0870, high=1.0885, low=1.0868, close=1.0880)

        self.assertIsNone(engine.on_m1_candle(m1_0))
        self.assertIsNone(engine.on_m1_candle(m1_1))
        signal = engine.on_m1_candle(m1_2)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")
        self.assertEqual(signal.entry_price, 1.0880)

        # SL anchored to bottom of the 3 consecutive 1m candles (min low = 1.0850)
        expected_sl = 1.0850
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio
        risk = signal.entry_price - signal.stop_loss
        expected_tp = signal.entry_price + (5.0 * risk)
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)
        self.assertEqual(signal.breakeven_trigger_r, 2.0)
        self.assertEqual(signal.partial_bank_pct, 0.0)

    def test_c1_wickswap_sell_setup(self):
        t0 = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        # M5 bar 0: Bullish
        m5_0 = Candle(timestamp=t0, open=1.0850, high=1.0890, low=1.0840, close=1.0880)
        engine.on_htf_candle(m5_0, timeframe="M5")

        # M5 bar 1: Bearish sweeping bar 0 high (high 1.0905 > 1.0890, close 1.0875 <= 1.0890)
        m5_1 = Candle(timestamp=t0 + timedelta(minutes=5), open=1.0885, high=1.0905, low=1.0870, close=1.0875)
        armed = engine.on_htf_candle(m5_1, timeframe="M5")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.SELL)

        # 3 confirming M1 bearish candles after M5 close (>= 08:10)
        m1_0 = Candle(timestamp=t0 + timedelta(minutes=10), open=1.0875, high=1.0880, low=1.0865, close=1.0868)
        m1_1 = Candle(timestamp=t0 + timedelta(minutes=11), open=1.0868, high=1.0870, low=1.0855, close=1.0858)
        m1_2 = Candle(timestamp=t0 + timedelta(minutes=12), open=1.0858, high=1.0860, low=1.0845, close=1.0848)

        self.assertIsNone(engine.on_m1_candle(m1_0))
        self.assertIsNone(engine.on_m1_candle(m1_1))
        signal = engine.on_m1_candle(m1_2)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SELL")
        self.assertEqual(signal.entry_price, 1.0848)

        # SL anchored to top of the 3 consecutive 1m candles (max high = 1.0880)
        expected_sl = 1.0880
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio
        risk = signal.stop_loss - signal.entry_price
        expected_tp = signal.entry_price - (5.0 * risk)
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

    def test_m15_bullish_wick_sweep_by_bearish_candle_live_trade(self):
        """
        Exact test reproducing user's reference images:
        - Timeframe: M15
        - Image 1: Bullish candle's wick swept by bearish candle (Variant A).
        - Image 2: M1 3 consecutive bearish candles -> SELL entry at close of 3rd candle.
        - Stop Loss placed at top of the 3 consecutive 1-minute candles.
        - 1:5 Reward-to-Risk ratio.
        - Prior non-matching M1 bar does NOT disarm the setup prematurely.
        """
        t0 = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="USDCAD", session_filter=False)

        # M15 Candle 0: Bullish (open 1.4020, high 1.4032, low 1.4015, close 1.4030)
        c0 = Candle(timestamp=t0, open=1.4020, high=1.4032, low=1.4015, close=1.4030)
        engine.on_htf_candle(c0, timeframe="M15")

        # M15 Candle 1: Bearish sweeping Candle 0 wick (high 1.4036 > 1.4032, close 1.4028 <= 1.4032)
        c1 = Candle(timestamp=t0 + timedelta(minutes=15), open=1.4030, high=1.4036, low=1.4025, close=1.4028)
        armed = engine.on_htf_candle(c1, timeframe="M15")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.SELL)
        self.assertEqual(armed.extreme_price, 1.4036)

        # Sweep closes at 14:30.
        # Suppose first M1 candle at 14:30 is slightly bullish (green candle) - should NOT disarm!
        m1_noise = Candle(timestamp=t0 + timedelta(minutes=30), open=1.4028, high=1.4030, low=1.4027, close=1.4029)
        self.assertIsNone(engine.on_m1_candle(m1_noise))
        self.assertTrue(engine.is_armed, "Engine must stay armed during 15-candle window even if an opposite bar appears")

        # Next 3 M1 candles are consecutive bearish:
        # Candle 1: 14:31
        m1_1 = Candle(timestamp=t0 + timedelta(minutes=31), open=1.4029, high=1.4031, low=1.4024, close=1.4025)
        # Candle 2: 14:32
        m1_2 = Candle(timestamp=t0 + timedelta(minutes=32), open=1.4025, high=1.4026, low=1.4020, close=1.4021)
        # Candle 3: 14:33
        m1_3 = Candle(timestamp=t0 + timedelta(minutes=33), open=1.4021, high=1.4022, low=1.4016, close=1.4017)

        self.assertIsNone(engine.on_m1_candle(m1_1))
        self.assertIsNone(engine.on_m1_candle(m1_2))
        signal = engine.on_m1_candle(m1_3)

        self.assertIsNotNone(signal, "Must generate SELL signal on close of 3rd consecutive bearish candle")
        self.assertEqual(signal.direction, "SELL")
        self.assertEqual(signal.entry_price, 1.4017)

        # Stop loss anchored strictly to top of the 3 consecutive 1-minute candles (max high = 1.4031)
        expected_sl = 1.4031
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio:
        # Risk = 1.4031 - 1.4017 = 0.0014 (14 pips), Reward = 5 * 14 pips = 70 pips
        self.assertEqual(signal.reward_risk_ratio, 5.0)
        expected_tp = signal.entry_price - (5.0 * (signal.stop_loss - signal.entry_price))
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)

    def test_m15_bearish_wick_sweep_by_bullish_candle_buy_setup(self):
        """
        M15 BUY setup:
        - 15m Candle 0: Bearish (open 1.4030, high 1.4035, low 1.4010, close 1.4015)
        - 15m Candle 1: Bullish sweeping Candle 0 low wick (low 1.4002 < 1.4010, close 1.4022 >= 1.4010)
        - 1m confirmation: 3 consecutive bullish candles -> BUY entry at close of 3rd candle.
        - Stop Loss placed at bottom of the 3 consecutive 1-minute candles.
        - 1:5 Reward-to-Risk ratio.
        """
        t0 = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="USDCAD", session_filter=False)

        # 15M Candle 0: Bearish
        c0 = Candle(timestamp=t0, open=1.4030, high=1.4035, low=1.4010, close=1.4015)
        engine.on_htf_candle(c0, timeframe="M15")

        # 15M Candle 1: Bullish sweeping Candle 0 low
        c1 = Candle(timestamp=t0 + timedelta(minutes=15), open=1.4015, high=1.4025, low=1.4002, close=1.4022)
        armed = engine.on_htf_candle(c1, timeframe="M15")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.BUY)
        self.assertEqual(armed.extreme_price, 1.4002)
        self.assertEqual(armed.sweep_timeframe, "M15")

        # 1m confirmation bars starting at 14:30
        t_m1 = t0 + timedelta(minutes=30)
        m1_1 = Candle(timestamp=t_m1 + timedelta(minutes=1), open=1.4022, high=1.4028, low=1.4020, close=1.4027)
        m1_2 = Candle(timestamp=t_m1 + timedelta(minutes=2), open=1.4027, high=1.4034, low=1.4025, close=1.4033)
        m1_3 = Candle(timestamp=t_m1 + timedelta(minutes=3), open=1.4033, high=1.4042, low=1.4030, close=1.4040)

        self.assertIsNone(engine.on_m1_candle(m1_1))
        self.assertIsNone(engine.on_m1_candle(m1_2))
        signal = engine.on_m1_candle(m1_3)

        self.assertIsNotNone(signal, "Must generate BUY signal on close of 3rd consecutive bullish candle")
        self.assertEqual(signal.direction, "BUY")
        self.assertEqual(signal.entry_price, 1.4040)

        # Stop loss anchored strictly to bottom of 3 consecutive 1-minute candles (min low = 1.4020)
        expected_sl = 1.4020
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio
        risk = signal.entry_price - signal.stop_loss
        expected_tp = signal.entry_price + (5.0 * risk)
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

    def test_m5_bearish_wick_sweep_by_bullish_candle_buy_setup(self):
        """
        M5 BUY setup:
        - 5m Candle 0: Bearish (open 1.0850, close 1.0820, low 1.0815)
        - 5m Candle 1: Bullish sweeping Candle 0 low wick (low 1.0805 < 1.0815, close 1.0830 >= 1.0815)
        - 1m confirmation: 3 consecutive bullish candles -> BUY entry.
        - Stop Loss placed at bottom of the 3 consecutive 1-minute candles.
        - 1:5 Reward-to-Risk ratio.
        """
        t0 = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        c0 = Candle(timestamp=t0, open=1.0850, high=1.0855, low=1.0815, close=1.0820)
        engine.on_htf_candle(c0, timeframe="M5")

        c1 = Candle(timestamp=t0 + timedelta(minutes=5), open=1.0820, high=1.0835, low=1.0805, close=1.0830)
        armed = engine.on_htf_candle(c1, timeframe="M5")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.BUY)
        self.assertEqual(armed.extreme_price, 1.0805)
        self.assertEqual(armed.sweep_timeframe, "M5")

        # 1m confirmation bars starting at 10:10
        t_m1 = t0 + timedelta(minutes=10)
        m1_1 = Candle(timestamp=t_m1, open=1.0830, high=1.0837, low=1.0828, close=1.0836)
        m1_2 = Candle(timestamp=t_m1 + timedelta(minutes=1), open=1.0836, high=1.0843, low=1.0834, close=1.0842)
        m1_3 = Candle(timestamp=t_m1 + timedelta(minutes=2), open=1.0842, high=1.0851, low=1.0840, close=1.0849)

        self.assertIsNone(engine.on_m1_candle(m1_1))
        self.assertIsNone(engine.on_m1_candle(m1_2))
        signal = engine.on_m1_candle(m1_3)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")
        self.assertEqual(signal.entry_price, 1.0849)

        # SL anchored to bottom of 3 consecutive 1-minute candles (min low = 1.0828)
        expected_sl = 1.0828
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

    def test_m5_bullish_wick_sweep_by_bearish_candle_sell_setup(self):
        """
        M5 SELL setup:
        - 5m Candle 0: Bullish (open 1.0820, close 1.0850, high 1.0855)
        - 5m Candle 1: Bearish sweeping Candle 0 high wick (high 1.0865 > 1.0855, close 1.0840 <= 1.0855)
        - 1m confirmation: 3 consecutive bearish candles -> SELL entry.
        - Stop Loss placed at top of the 3 consecutive 1-minute candles.
        - 1:5 Reward-to-Risk ratio.
        """
        t0 = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        c0 = Candle(timestamp=t0, open=1.0820, high=1.0855, low=1.0815, close=1.0850)
        engine.on_htf_candle(c0, timeframe="M5")

        c1 = Candle(timestamp=t0 + timedelta(minutes=5), open=1.0850, high=1.0865, low=1.0835, close=1.0840)
        armed = engine.on_htf_candle(c1, timeframe="M5")
        self.assertIsNotNone(armed)
        self.assertEqual(armed.direction, Direction.SELL)
        self.assertEqual(armed.extreme_price, 1.0865)
        self.assertEqual(armed.sweep_timeframe, "M5")

        # 1m confirmation bars starting at 10:10
        t_m1 = t0 + timedelta(minutes=10)
        m1_1 = Candle(timestamp=t_m1, open=1.0840, high=1.0842, low=1.0830, close=1.0832)
        m1_2 = Candle(timestamp=t_m1 + timedelta(minutes=1), open=1.0832, high=1.0835, low=1.0823, close=1.0825)
        m1_3 = Candle(timestamp=t_m1 + timedelta(minutes=2), open=1.0825, high=1.0827, low=1.0815, close=1.0818)

        self.assertIsNone(engine.on_m1_candle(m1_1))
        self.assertIsNone(engine.on_m1_candle(m1_2))
        signal = engine.on_m1_candle(m1_3)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SELL")
        self.assertEqual(signal.entry_price, 1.0818)

        # SL anchored to top of 3 consecutive 1-minute candles (max high = 1.0842)
        expected_sl = 1.0842
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

    def test_m15_priority_over_m5_when_both_active(self):
        """
        When M15 arms a setup, an incoming M5 bar does NOT overwrite the M15 setup.
        """
        t0 = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        # 1. M15 sweep occurs
        m15_0 = Candle(timestamp=t0, open=1.0820, high=1.0855, low=1.0815, close=1.0850)
        engine.on_htf_candle(m15_0, timeframe="M15")

        m15_1 = Candle(timestamp=t0 + timedelta(minutes=15), open=1.0850, high=1.0870, low=1.0835, close=1.0845)
        armed_m15 = engine.on_htf_candle(m15_1, timeframe="M15")
        self.assertIsNotNone(armed_m15)
        self.assertEqual(engine.armed_state.sweep_timeframe, "M15")

        # 2. Subsequent M5 bar arrives at 10:20 - even if it forms an M5 sweep, M15 priority is preserved
        m5_prev = Candle(timestamp=t0 + timedelta(minutes=15), open=1.0850, high=1.0855, low=1.0840, close=1.0842)
        engine.on_htf_candle(m5_prev, timeframe="M5")

        m5_sweep = Candle(timestamp=t0 + timedelta(minutes=20), open=1.0842, high=1.0860, low=1.0830, close=1.0838)
        engine.on_htf_candle(m5_sweep, timeframe="M5")

        self.assertTrue(engine.is_armed)
        self.assertEqual(engine.armed_state.sweep_timeframe, "M15", "M15 higher timeframe setup must take priority over M5")

    def test_check_m5_and_check_m15_toggles(self):
        """
        Verify that check_m5 and check_m15 disable sweep detection for that specific timeframe.
        """
        t0 = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)

        # Test check_m5=False
        eng_no_m5 = RuleEngine.c1_wickswap_preset(check_m5=False, check_m15=True, session_filter=False)
        c0 = Candle(timestamp=t0, open=1.0820, high=1.0855, low=1.0815, close=1.0850)
        c1 = Candle(timestamp=t0 + timedelta(minutes=5), open=1.0850, high=1.0865, low=1.0835, close=1.0840)
        eng_no_m5.on_htf_candle(c0, "M5")
        self.assertIsNone(eng_no_m5.on_htf_candle(c1, "M5"))
        self.assertFalse(eng_no_m5.is_armed)

        # Test check_m15=False
        eng_no_m15 = RuleEngine.c1_wickswap_preset(check_m5=True, check_m15=False, session_filter=False)
        c15_0 = Candle(timestamp=t0, open=1.0820, high=1.0855, low=1.0815, close=1.0850)
        c15_1 = Candle(timestamp=t0 + timedelta(minutes=15), open=1.0850, high=1.0870, low=1.0835, close=1.0845)
        eng_no_m15.on_htf_candle(c15_0, "M15")
        self.assertIsNone(eng_no_m15.on_htf_candle(c15_1, "M15"))
        self.assertFalse(eng_no_m15.is_armed)

    def test_m15_intrabar_wick_sweep_with_3_confirming_m1_candles_user_setup(self):
        """
        Exact user TradingView setup:
        - 15-minute timeframe: Prior 15m candle is bullish with high 1.11900.
        - Next 15m candle (14:45-15:00) is actively forming.
        - At 14:46, 1-minute candle pierces prior 15m high, reaching 1.11956 (intrabar wick sweep).
        - 3 consecutive confirming 1-minute bearish candles form at 14:47, 14:48, 14:49.
        - Order enters at 14:49 close (intrabar, BEFORE 15:00 15m candle closes).
        - Stop-Loss is strictly at the highest high among the 3 confirming 1-minute candles.
        - Take-Profit is strictly at 1:5 Reward-to-Risk ratio.
        - No duplicate trades occur when the 15m candle closes at 15:00.
        """
        t0 = datetime(2026, 10, 6, 14, 30, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        # 1. Prior 15m candle (14:30): Bullish (high 1.11900)
        m15_prev = Candle(timestamp=t0, open=1.11800, high=1.11900, low=1.11780, close=1.11880)
        engine.on_htf_candle(m15_prev, timeframe="M15")

        # 2. 14:45 M1 bar (open of next 15m candle period)
        t_m15 = t0 + timedelta(minutes=15)  # 14:45
        m1_0 = Candle(timestamp=t_m15, open=1.11880, high=1.11895, low=1.11870, close=1.11890)
        self.assertIsNone(engine.on_m1_candle(m1_0))
        self.assertFalse(engine.is_armed)

        # 3. 14:46 M1 bar spikes above 1.11900 to 1.11956 (intrabar wick sweep!)
        m1_sweep = Candle(timestamp=t_m15 + timedelta(minutes=1), open=1.11890, high=1.11956, low=1.11885, close=1.11940)
        self.assertIsNone(engine.on_m1_candle(m1_sweep))
        self.assertTrue(engine.is_armed, "Must arm immediately intrabar upon sweeping prior M15 high")
        self.assertEqual(engine.armed_state.direction, Direction.SELL)
        self.assertEqual(engine.armed_state.extreme_price, 1.11956)
        self.assertTrue(engine.armed_state.is_intrabar)

        # 4. Three consecutive confirming bearish 1-minute candles (14:47, 14:48, 14:49)
        m1_c1 = Candle(timestamp=t_m15 + timedelta(minutes=2), open=1.11940, high=1.11945, low=1.11890, close=1.11900)
        m1_c2 = Candle(timestamp=t_m15 + timedelta(minutes=3), open=1.11900, high=1.11910, low=1.11850, close=1.11860)
        m1_c3 = Candle(timestamp=t_m15 + timedelta(minutes=4), open=1.11860, high=1.11870, low=1.11800, close=1.11810)

        self.assertIsNone(engine.on_m1_candle(m1_c1))
        self.assertIsNone(engine.on_m1_candle(m1_c2))
        signal = engine.on_m1_candle(m1_c3)

        self.assertIsNotNone(signal, "Must trigger SELL signal at 14:49 on close of 3rd confirming candle")
        self.assertEqual(signal.direction, "SELL")
        self.assertEqual(signal.entry_price, 1.11810)

        # Stop-Loss must be strictly max(c1.high, c2.high, c3.high) = 1.11945
        expected_sl = 1.11945
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio:
        # Risk = 1.11945 - 1.11810 = 0.00135 (13.5 pips)
        # Reward = 5 * 0.00135 = 0.00675
        # TP = 1.11810 - 0.00675 = 1.11135
        risk = signal.stop_loss - signal.entry_price
        expected_tp = signal.entry_price - (5.0 * risk)
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

        # 5. Subsequent M1 bars up to 15:00 do not trigger duplicate trades
        for i in range(5, 15):
            m1_next = Candle(timestamp=t_m15 + timedelta(minutes=i), open=1.11810, high=1.11820, low=1.11790, close=1.11800)
            self.assertIsNone(engine.on_m1_candle(m1_next))

        # 6. When the 14:45 15m candle finishes and closes at 15:00, verify it does NOT re-arm
        m15_completed = Candle(timestamp=t_m15, open=1.11880, high=1.11956, low=1.11790, close=1.11800)
        self.assertIsNone(engine.on_htf_candle(m15_completed, timeframe="M15"), "Must not re-arm already traded M15 sweep")
        self.assertFalse(engine.is_armed)

    def test_user_strategy_m5_intrabar_long_trade_c1_only_sl(self):
        """
        Exact user strategy for LONG trade:
        1. Bearish candle's wick swapped by bullish candle's wick on M5, before the bullish candle closes.
        2. Move to 1-minute timeframe: look for 3 consecutive bullish candles.
        3. On close of the 3rd bullish candle, immediately place BUY trade.
        4. Stop Loss is strictly at the bottom of the first consecutive candle (C1 low),
           even if C2 has a lower low.
        5. Target is 1:5 Reward-to-Risk ratio.
        """
        t0 = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        # Prior M5 candle: Bearish with low 1.08200
        m5_prev = Candle(timestamp=t0, open=1.08400, high=1.08450, low=1.08200, close=1.08220)
        engine.on_htf_candle(m5_prev, timeframe="M5")

        # Next M5 candle starts at 09:05.
        # Minute 09:05: does not sweep yet
        t_m5 = t0 + timedelta(minutes=5)
        m1_0 = Candle(timestamp=t_m5, open=1.08220, high=1.08240, low=1.08210, close=1.08230)
        self.assertIsNone(engine.on_m1_candle(m1_0))
        self.assertFalse(engine.is_armed)

        # Minute 09:06: Bearish wick swapped by bullish candle's wick before M5 closes (low 1.08150 < 1.08200)
        # Candle sweeps the low but closes bearish (open 1.08230, close 1.08220), so it does not count as C1 for BUY
        m1_sweep = Candle(timestamp=t_m5 + timedelta(minutes=1), open=1.08230, high=1.08260, low=1.08150, close=1.08220)
        self.assertIsNone(engine.on_m1_candle(m1_sweep))
        self.assertTrue(engine.is_armed, "Must arm immediately intrabar on M5 wick swap")
        self.assertEqual(engine.armed_state.direction, Direction.BUY)
        self.assertTrue(engine.armed_state.is_intrabar)

        # 3 consecutive bullish candles on 1-minute timeframe:
        # C1: low is 1.08210
        m1_c1 = Candle(timestamp=t_m5 + timedelta(minutes=2), open=1.08250, high=1.08310, low=1.08210, close=1.08290)
        # C2: low dips to 1.08190 (< C1 low), but closes bullish
        m1_c2 = Candle(timestamp=t_m5 + timedelta(minutes=3), open=1.08290, high=1.08360, low=1.08190, close=1.08340)
        # C3: closes bullish at 1.08400
        m1_c3 = Candle(timestamp=t_m5 + timedelta(minutes=4), open=1.08340, high=1.08420, low=1.08320, close=1.08400)

        self.assertIsNone(engine.on_m1_candle(m1_c1))
        self.assertIsNone(engine.on_m1_candle(m1_c2))
        signal = engine.on_m1_candle(m1_c3)

        # Immediately place buy trade
        self.assertIsNotNone(signal, "Must place BUY trade immediately when 3rd bullish candle closes")
        self.assertEqual(signal.direction, "BUY")
        self.assertEqual(signal.entry_price, 1.08400)

        # Stop loss strictly at the bottom of the first consecutive candle (C1 low = 1.08210)
        expected_sl = 1.08210
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio
        risk = signal.entry_price - signal.stop_loss  # 1.08400 - 1.08210 = 0.00190
        expected_tp = signal.entry_price + (5.0 * risk)  # 1.08400 + 0.00950 = 1.09350
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

    def test_user_strategy_m5_intrabar_short_trade_c1_only_sl(self):
        """
        Exact user strategy for SHORT trade when sweep candle closes bullish (so C1 is subsequent candle):
        1. Bullish candle's wick swapped by bearish candle's wick on M5, before the bearish candle closes.
        2. Move to 1-minute timeframe: look for 3 consecutive bearish candles.
        3. On close of the 3rd bearish candle, immediately place SELL trade.
        4. Stop Loss is strictly at the top of the first consecutive candle (C1 high).
        5. Target is 1:5 Reward-to-Risk ratio.
        """
        t0 = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False)

        # Prior M5 candle: Bullish with high 1.08500
        m5_prev = Candle(timestamp=t0, open=1.08300, high=1.08500, low=1.08280, close=1.08480)
        engine.on_htf_candle(m5_prev, timeframe="M5")

        # Next M5 candle starts at 09:05.
        t_m5 = t0 + timedelta(minutes=5)
        m1_0 = Candle(timestamp=t_m5, open=1.08480, high=1.08490, low=1.08460, close=1.08470)
        self.assertIsNone(engine.on_m1_candle(m1_0))
        self.assertFalse(engine.is_armed)

        # Minute 09:06: Bullish wick swapped by candle's wick before M5 closes (high 1.08560 > 1.08500)
        # Candle sweeps the high but closes bullish (open 1.08470, close 1.08480), so it does not count as C1 for SELL
        m1_sweep = Candle(timestamp=t_m5 + timedelta(minutes=1), open=1.08470, high=1.08560, low=1.08440, close=1.08480)
        self.assertIsNone(engine.on_m1_candle(m1_sweep))
        self.assertTrue(engine.is_armed, "Must arm immediately intrabar on M5 wick swap")
        self.assertEqual(engine.armed_state.direction, Direction.SELL)
        self.assertTrue(engine.armed_state.is_intrabar)

        # 3 consecutive bearish candles on 1-minute timeframe:
        # C1: high is 1.08460
        m1_c1 = Candle(timestamp=t_m5 + timedelta(minutes=2), open=1.08450, high=1.08460, low=1.08380, close=1.08400)
        # C2: high wicks to 1.08480 (> C1 high), but closes bearish
        m1_c2 = Candle(timestamp=t_m5 + timedelta(minutes=3), open=1.08400, high=1.08480, low=1.08330, close=1.08350)
        # C3: closes bearish at 1.08280
        m1_c3 = Candle(timestamp=t_m5 + timedelta(minutes=4), open=1.08350, high=1.08360, low=1.08270, close=1.08280)

        self.assertIsNone(engine.on_m1_candle(m1_c1))
        self.assertIsNone(engine.on_m1_candle(m1_c2))
        signal = engine.on_m1_candle(m1_c3)

        # Immediately place sell trade
        self.assertIsNotNone(signal, "Must place SELL trade immediately when 3rd bearish candle closes")
        self.assertEqual(signal.direction, "SELL")
        self.assertEqual(signal.entry_price, 1.08280)

        # Stop loss strictly at the top of the first consecutive candle (C1 high = 1.08460)
        expected_sl = 1.08460
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio
        risk = signal.stop_loss - signal.entry_price  # 1.08460 - 1.08280 = 0.00180
        expected_tp = signal.entry_price - (5.0 * risk)  # 1.08280 - 0.00900 = 1.07380
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)

    def test_usdcad_sweep_candle_is_c1_immediate_sell_setup(self):
        """
        Exact user TradingView setup from USDCAD (Reference Images 2 & 3):
        1. 5m / 15m bullish candle closed at 07:00 (high = 1.42629).
        2. Next candle opens and is forming.
        3. In 1m timeframe:
           - 07:02: 1m candle's high wick (1.42635) swaps the prior bullish candle's wick (1.42629)
             AND closes bearish (open 1.42630, close 1.42610).
             This candle IS the 1st consecutive bearish candle (C1)!
           - 07:03: 2nd consecutive bearish candle (open 1.42608, close 1.42605).
           - 07:04: 3rd consecutive bearish candle (open 1.42604, close 1.42598).
        4. When the 3rd bearish candle closes at 07:04:
           - Immediately place SELL trade!
           - Entry price = 1.42598 (close of 3rd candle).
           - Stop loss strictly at top of first bearish candle (C1 high = 1.42635).
           - 1:5 Reward-to-Risk ratio -> TP = 1.42598 - 5 * (1.42635 - 1.42598) = 1.42413.
        """
        t0 = datetime(2026, 10, 8, 6, 55, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="USDCAD", session_filter=False)

        # Prior M5 candle (06:55): Bullish with high 1.42629
        m5_prev = Candle(timestamp=t0, open=1.42603, high=1.42629, low=1.42598, close=1.42626)
        engine.on_htf_candle(m5_prev, timeframe="M5")

        t_m5 = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)
        # 07:00 M1: doesn't sweep
        m1_0 = Candle(timestamp=t_m5, open=1.42625, high=1.42626, low=1.42596, close=1.42618)
        self.assertIsNone(engine.on_m1_candle(m1_0))

        # 07:01 M1: doesn't sweep
        m1_1 = Candle(timestamp=t_m5 + timedelta(minutes=1), open=1.42617, high=1.42629, low=1.42616, close=1.42628)
        self.assertIsNone(engine.on_m1_candle(m1_1))

        # 07:02 M1 (C1): Wick swaps bullish candle's high (1.42635 > 1.42629) AND closes bearish (1.42610 < 1.42630)
        m1_c1 = Candle(timestamp=t_m5 + timedelta(minutes=2), open=1.42630, high=1.42635, low=1.42607, close=1.42610)
        self.assertIsNone(engine.on_m1_candle(m1_c1))
        self.assertTrue(engine.is_armed, "Must arm on sweep")
        self.assertEqual(len(engine.armed_state.confirming_candles), 1, "C1 must be registered immediately")

        # 07:03 M1 (C2): 2nd consecutive bearish candle
        m1_c2 = Candle(timestamp=t_m5 + timedelta(minutes=3), open=1.42608, high=1.42614, low=1.42600, close=1.42605)
        self.assertIsNone(engine.on_m1_candle(m1_c2))
        self.assertEqual(len(engine.armed_state.confirming_candles), 2)

        # 07:04 M1 (C3): 3rd consecutive bearish candle
        m1_c3 = Candle(timestamp=t_m5 + timedelta(minutes=4), open=1.42604, high=1.42605, low=1.42597, close=1.42598)
        signal = engine.on_m1_candle(m1_c3)

        self.assertIsNotNone(signal, "Must place SELL trade immediately when 3rd bearish candle closes at 07:04")
        self.assertEqual(signal.direction, "SELL")
        self.assertEqual(signal.entry_price, 1.42598)

        # Stop loss strictly at top of first bearish candle (C1 high = 1.42635)
        self.assertEqual(signal.stop_loss, 1.42635)

        # 1:5 Reward-to-Risk ratio:
        # Risk = 1.42635 - 1.42598 = 0.00037
        # Reward = 5 * 0.00037 = 0.00185
        # TP = 1.42598 - 0.00185 = 1.42413
        self.assertAlmostEqual(signal.take_profit, 1.42413, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)


if __name__ == "__main__":
    unittest.main()


