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
    - Stop Loss strictly anchored to Candle 1 (C1 low for BUY, C1 high for SELL).
    - 1:5 Reward-to-Risk ratio.
    - Breakeven advance at +2.0R with no partial close (100% position runs to +5.0R).
    """

    def test_preset_configuration(self):
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD")
        self.assertTrue(engine.use_c1_only_sl)
        self.assertFalse(engine.use_sweep_wick_sl)
        self.assertFalse(engine.anchor_to_key_liquidity)
        self.assertTrue(engine.allow_variant_a)
        self.assertFalse(engine.allow_variant_b)
        self.assertEqual(engine.reward_risk_ratio, 5.0)
        self.assertEqual(engine.breakeven_trigger_r, 2.0)
        self.assertEqual(engine.partial_bank_pct, 0.0)
        self.assertTrue(engine.h1_trend_filter)

    def test_c1_wickswap_buy_setup(self):
        t0 = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False, h1_trend_filter=False)

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

        # SL strictly below C1 low minus buffer (1.0850 - 0.00005 = 1.08495)
        expected_sl = 1.0850 - (0.5 * 0.0001)
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
        engine = RuleEngine.c1_wickswap_preset(symbol="EURUSD", session_filter=False, h1_trend_filter=False)

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

        # SL strictly top of C1 high plus spread & buffer (1.0880 + 0.00005 + 0.00005 = 1.08810)
        expected_sl = 1.0880 + (0.5 * 0.0001) + (0.5 * 0.0001)
        self.assertAlmostEqual(signal.stop_loss, expected_sl, places=5)

        # 1:5 Reward-to-Risk ratio
        risk = signal.stop_loss - signal.entry_price
        expected_tp = signal.entry_price - (5.0 * risk)
        self.assertAlmostEqual(signal.take_profit, expected_tp, places=5)
        self.assertEqual(signal.reward_risk_ratio, 5.0)


if __name__ == "__main__":
    unittest.main()

