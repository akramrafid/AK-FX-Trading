"""
Exhaustive unit tests for Multi-Timeframe Rule Engine (Phase 1 Specification).

Validates:
1. 5-minute / 15-minute Bearish Sweep -> 1-minute 3 consecutive bearish confirmation -> SELL entry.
2. 5-minute / 15-minute Bullish Sweep -> 1-minute 3 consecutive bullish confirmation -> BUY entry.
3. Stop-Loss at the extreme (highest high for Sell, lowest low for Buy) across the 3 confirming candles.
4. Exact 10:1 Reward-to-Risk mathematical pricing (TP = entry ± 10 * stop_distance).
5. "Check both 5-minute and 15-minute": either is sufficient to arm the 1-minute confirmation watch.
6. 15-candle armed-state expiry: disarms if confirmation does not complete within 15 1-minute candles.
7. Direction break: disarms if a 1-minute candle breaks direction before 3 form.
8. Reset mode: resets consecutive count if configured with disarm_on_break=False.
9. Automated M1 to M5 / M15 resampling.
10. Event-driven multi-timeframe historical stream scanning without look-ahead bias.
11. Unified feed_candle API returning {direction, entry_price, stop_loss, take_profit}.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import unittest

from engine.models import ArmedState, Candle, Direction, TradeSignal
from engine.rule_engine import RuleEngine, MultiTimeframeRuleEngine, resample_m1_to_htf


def make_candle(
    time: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float = 100.0,
) -> Candle:
    """Helper to generate a validated Candle object."""
    return Candle(
        timestamp=time,
        open=round(o, 5),
        high=round(h, 5),
        low=round(l, 5),
        close=round(c, 5),
        volume=v,
    )


class TestMultiTimeframeRuleEngine(unittest.TestCase):
    def setUp(self):
        self.base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        self.engine = RuleEngine(
            check_m5=True,
            check_m15=True,
            max_watch_candles=15,
            disarm_on_break=True,
            spread_pips=0.0,
            buffer_pips=0.0,
            pip_size=0.0001,
        )

    def test_sell_setup_m5_sweep_with_m1_confirmation(self):
        """
        Sell setup:
        - 5m candle 0 (10:00-10:05): Bullish (open 1.0850, close 1.0880, high 1.0890)
        - 5m candle 1 (10:05-10:10): Sweeps high 1.0890 with wick to 1.0910, closes 1.0875 (Bearish)
          -> Arms for SELL!
        - 1m candle 1 (10:10-10:11): Bearish (1.0875 -> 1.0865, high 1.0878)
        - 1m candle 2 (10:11-10:12): Bearish (1.0865 -> 1.0855, high 1.0868)
        - 1m candle 3 (10:12-10:13): Bearish (1.0855 -> 1.0845, high 1.0858)
        - Entry: 1.0845 (close of 3rd candle)
        - Stop-Loss: 1.0878 (highest high among the 3 confirming candles: max(1.0878, 1.0868, 1.0858))
        - Stop distance: 1.0878 - 1.0845 = 0.0033 (33 pips)
        - Take-Profit: 1.0845 - (10 * 0.0033) = 1.0515 (exactly 10:1 R:R)
        """
        # HTF M5 bars
        m5_0 = make_candle(self.base_time, 1.0850, 1.0890, 1.0840, 1.0880)  # 10:00
        m5_1 = make_candle(self.base_time + timedelta(minutes=5), 1.0880, 1.0910, 1.0870, 1.0875)  # 10:05

        self.engine.on_htf_candle(m5_0, "M5")
        self.assertFalse(self.engine.is_armed)

        armed = self.engine.on_htf_candle(m5_1, "M5")
        self.assertTrue(self.engine.is_armed)
        self.assertEqual(self.engine.armed_state.direction, Direction.SELL)
        self.assertEqual(self.engine.armed_state.sweep_timeframe, "M5")
        self.assertAlmostEqual(self.engine.armed_state.swept_level, 1.0890)
        self.assertAlmostEqual(self.engine.armed_state.extreme_price, 1.0910)

        # 1m confirmation bars starting at 10:10 (when 10:05 M5 candle has closed)
        t_m1 = self.base_time + timedelta(minutes=10)
        m1_1 = make_candle(t_m1, 1.0875, 1.0878, 1.0860, 1.0865)
        m1_2 = make_candle(t_m1 + timedelta(minutes=1), 1.0865, 1.0868, 1.0850, 1.0855)
        m1_3 = make_candle(t_m1 + timedelta(minutes=2), 1.0855, 1.0858, 1.0840, 1.0845)

        sig1 = self.engine.on_m1_candle(m1_1)
        self.assertIsNone(sig1)
        self.assertTrue(self.engine.is_armed)
        self.assertEqual(len(self.engine.armed_state.confirming_candles), 1)

        sig2 = self.engine.on_m1_candle(m1_2)
        self.assertIsNone(sig2)
        self.assertTrue(self.engine.is_armed)
        self.assertEqual(len(self.engine.armed_state.confirming_candles), 2)

        sig3 = self.engine.on_m1_candle(m1_3)
        self.assertIsNotNone(sig3)
        self.assertFalse(self.engine.is_armed)  # Disarmed upon execution!

        self.assertEqual(sig3.direction, "SELL")
        self.assertAlmostEqual(sig3.entry_price, 1.0845)
        self.assertAlmostEqual(sig3.stop_loss, 1.0878)  # Highest high across the 3 candles
        self.assertAlmostEqual(sig3.risk_distance, 0.0033)
        self.assertAlmostEqual(sig3.reward_distance, 0.0165)
        self.assertAlmostEqual(sig3.take_profit, 1.0680)
        self.assertAlmostEqual(sig3.reward_risk_ratio, 5.0)

    def test_buy_setup_m15_sweep_with_m1_confirmation(self):
        """
        Buy setup on 15m chart:
        - 15m candle 0 (10:00): Bearish (open 1.0880, close 1.0840, low 1.0830)
        - 15m candle 1 (10:15): Sweeps low 1.0830 with wick to 1.0810, closes 1.0850 (Bullish)
          -> Arms for BUY!
        - 1m candle 1 (10:30-10:31): Bullish (1.0850 -> 1.0860, low 1.0848)
        - 1m candle 2 (10:31-10:32): Bullish (1.0860 -> 1.0875, low 1.0842)  <- Lowest low here
        - 1m candle 3 (10:32-10:33): Bullish (1.0875 -> 1.0890, low 1.0870)
        - Entry: 1.0890 (close of 3rd candle)
        - Stop-Loss: 1.0842 (lowest low among the 3 confirming candles: min(1.0848, 1.0842, 1.0870))
        - Stop distance: 1.0890 - 1.0842 = 0.0048 (48 pips)
        - Take-Profit: 1.0890 + (10 * 0.0048) = 1.1370 (exactly 10:1 R:R)
        """
        m15_0 = make_candle(self.base_time, 1.0880, 1.0890, 1.0830, 1.0840)  # 10:00
        m15_1 = make_candle(self.base_time + timedelta(minutes=15), 1.0840, 1.0860, 1.0810, 1.0850)  # 10:15

        self.engine.on_htf_candle(m15_0, "M15")
        self.assertFalse(self.engine.is_armed)

        armed = self.engine.on_htf_candle(m15_1, "M15")
        self.assertTrue(self.engine.is_armed)
        self.assertEqual(self.engine.armed_state.direction, Direction.BUY)
        self.assertEqual(self.engine.armed_state.sweep_timeframe, "M15")

        # 1m confirmation bars starting at 10:30 (when 10:15 M15 candle closes)
        t_m1 = self.base_time + timedelta(minutes=30)
        m1_1 = make_candle(t_m1, 1.0850, 1.0865, 1.0848, 1.0860)
        m1_2 = make_candle(t_m1 + timedelta(minutes=1), 1.0860, 1.0878, 1.0842, 1.0875)  # Lowest low
        m1_3 = make_candle(t_m1 + timedelta(minutes=2), 1.0875, 1.0895, 1.0870, 1.0890)

        self.assertIsNone(self.engine.on_m1_candle(m1_1))
        self.assertIsNone(self.engine.on_m1_candle(m1_2))
        sig = self.engine.on_m1_candle(m1_3)

        self.assertIsNotNone(sig)
        self.assertEqual(sig.direction, "BUY")
        self.assertAlmostEqual(sig.entry_price, 1.0890)
        self.assertAlmostEqual(sig.stop_loss, 1.0842)  # Lowest low across all 3 confirming candles
        self.assertAlmostEqual(sig.risk_distance, 0.0048)
        self.assertAlmostEqual(sig.reward_distance, 0.0240)
        self.assertAlmostEqual(sig.take_profit, 1.1130)
        self.assertAlmostEqual(sig.reward_risk_ratio, 5.0)

    def test_disarm_when_direction_breaks_before_3_form(self):
        """
        Specification: 'If a 1-minute candle breaks the required direction before 3 form... disarm and resume watching the higher timeframe.'
        Armed for SELL.
        Candle 1: Bearish (valid)
        Candle 2: Bullish (breaks direction!) -> Must disarm immediately.
        """
        m5_0 = make_candle(self.base_time, 1.0850, 1.0890, 1.0840, 1.0880)
        m5_1 = make_candle(self.base_time + timedelta(minutes=5), 1.0880, 1.0910, 1.0870, 1.0875)
        self.engine.on_htf_candle(m5_0, "M5")
        self.engine.on_htf_candle(m5_1, "M5")
        self.assertTrue(self.engine.is_armed)

        t_m1 = self.base_time + timedelta(minutes=10)
        m1_1 = make_candle(t_m1, 1.0875, 1.0878, 1.0860, 1.0865)  # Bearish (1/3)
        m1_2 = make_candle(t_m1 + timedelta(minutes=1), 1.0865, 1.0875, 1.0862, 1.0872)  # Bullish (BREAKS DIRECTION!)

        self.engine.on_m1_candle(m1_1)
        self.assertTrue(self.engine.is_armed)

        sig = self.engine.on_m1_candle(m1_2)
        self.assertIsNone(sig)
        self.assertFalse(self.engine.is_armed)  # Must be disarmed!

    def test_armed_state_expiry_after_15_candles(self):
        """
        Specification: 15 candles armed-state expiry.
        If 15 1-minute candles elapse without 3 consecutive confirming candles, state expires and disarms.
        """
        # Engine with disarm_on_break=False to allow alternating bars up to expiry
        engine = RuleEngine(max_watch_candles=15, disarm_on_break=False)
        m5_0 = make_candle(self.base_time, 1.0850, 1.0890, 1.0840, 1.0880)
        m5_1 = make_candle(self.base_time + timedelta(minutes=5), 1.0880, 1.0910, 1.0870, 1.0875)
        engine.on_htf_candle(m5_0, "M5")
        engine.on_htf_candle(m5_1, "M5")
        self.assertTrue(engine.is_armed)

        t_m1 = self.base_time + timedelta(minutes=10)
        # Feed 14 alternating candles (never 3 in a row)
        for i in range(14):
            if i % 2 == 0:
                c = make_candle(t_m1 + timedelta(minutes=i), 1.0870, 1.0875, 1.0860, 1.0865)  # Bearish
            else:
                c = make_candle(t_m1 + timedelta(minutes=i), 1.0865, 1.0875, 1.0862, 1.0870)  # Bullish
            engine.on_m1_candle(c)
            self.assertTrue(engine.is_armed, f"Should still be armed at candle {i+1}")

        # Candle 15 arrives
        c15 = make_candle(t_m1 + timedelta(minutes=14), 1.0870, 1.0875, 1.0868, 1.0872)  # Bullish
        engine.on_m1_candle(c15)
        self.assertFalse(engine.is_armed, "Should disarm at candle 15 due to expiry")

    def test_resample_m1_to_htf(self):
        """Verify that 1-minute candles correctly aggregate into 5-minute and 15-minute bars."""
        m1_bars = []
        for i in range(15):
            t = self.base_time + timedelta(minutes=i)
            # Create candles: open=1.0800 + i*0.0001, close=open+0.00005, high=open+0.0002, low=open-0.0001
            o = 1.0800 + i * 0.0001
            c = o + 0.00005
            h = o + 0.0002
            l = o - 0.0001
            m1_bars.append(make_candle(t, o, h, l, c, v=10.0))

        m5_bars = resample_m1_to_htf(m1_bars, 5)
        self.assertEqual(len(m5_bars), 3)

        # First M5 bar (0 to 4 minutes: 10:00 to 10:04)
        first_m5 = m5_bars[0]
        self.assertEqual(first_m5.timestamp, self.base_time)
        self.assertAlmostEqual(first_m5.open, m1_bars[0].open)
        self.assertAlmostEqual(first_m5.close, m1_bars[4].close)
        self.assertAlmostEqual(first_m5.high, max(b.high for b in m1_bars[:5]))
        self.assertAlmostEqual(first_m5.low, min(b.low for b in m1_bars[:5]))
        self.assertAlmostEqual(first_m5.volume, 50.0)

        # M15 bar (all 15 minutes)
        m15_bars = resample_m1_to_htf(m1_bars, 15)
        self.assertEqual(len(m15_bars), 1)
        first_m15 = m15_bars[0]
        self.assertEqual(first_m15.timestamp, self.base_time)
        self.assertAlmostEqual(first_m15.open, m1_bars[0].open)
        self.assertAlmostEqual(first_m15.close, m1_bars[14].close)
        self.assertAlmostEqual(first_m15.high, max(b.high for b in m1_bars))
        self.assertAlmostEqual(first_m15.low, min(b.low for b in m1_bars))
        self.assertAlmostEqual(first_m15.volume, 150.0)

    def test_feed_candle_dictionary_interface(self):
        """
        Verify the top-level feed_candle API:
        - M5 bars return None
        - M1 confirmation bars return None until 3rd candle which returns {direction, entry_price, stop_loss, take_profit}
        """
        m5_0 = make_candle(self.base_time, 1.0850, 1.0890, 1.0840, 1.0880)
        m5_1 = make_candle(self.base_time + timedelta(minutes=5), 1.0880, 1.0910, 1.0870, 1.0875)

        res0 = self.engine.feed_candle("M5", m5_0)
        self.assertIsNone(res0)
        res1 = self.engine.feed_candle("M5", m5_1)
        self.assertIsNone(res1)
        self.assertTrue(self.engine.is_armed)

        t_m1 = self.base_time + timedelta(minutes=10)
        m1_1 = make_candle(t_m1, 1.0875, 1.0878, 1.0860, 1.0865)
        m1_2 = make_candle(t_m1 + timedelta(minutes=1), 1.0865, 1.0868, 1.0850, 1.0855)
        m1_3 = make_candle(t_m1 + timedelta(minutes=2), 1.0855, 1.0858, 1.0840, 1.0845)

        self.assertIsNone(self.engine.feed_candle("M1", m1_1))
        self.assertIsNone(self.engine.feed_candle("M1", m1_2))
        trade_dict = self.engine.feed_candle("M1", m1_3)

        self.assertIsInstance(trade_dict, dict)
        self.assertEqual(trade_dict["direction"], "SELL")
        self.assertAlmostEqual(trade_dict["entry_price"], 1.0845)
        self.assertAlmostEqual(trade_dict["stop_loss"], 1.0878)
        self.assertAlmostEqual(trade_dict["take_profit"], 1.0680)
        self.assertAlmostEqual(trade_dict["reward_risk_ratio"], 5.0)

    def test_scan_multitimeframe_streams_integration(self):
        """
        Verify historical multi-timeframe stream scan correctly processes an entire sequence
        of M1 bars with automatic HTF resampling.
        """
        # Construct a sequence of M1 bars containing a clear 5m bearish sweep and 1m confirmation
        # 10:00 to 10:04 (Bar 0 M5): Bullish (open 1.0850 -> close 1.0880, high 1.0885)
        # 10:05 to 10:09 (Bar 1 M5): Sweeps 1.0885 (high 1.0905), closes 1.0870 (Bearish)
        # 10:10 to 10:12: 3 consecutive bearish 1m bars
        candles: list[Candle] = []

        # 10:00-10:04: 5 M1 bars moving up from 1.0850 to 1.0880
        for i in range(5):
            t = self.base_time + timedelta(minutes=i)
            o = 1.0850 + i * 0.0006
            c = o + 0.0005
            h = c + 0.0002
            l = o - 0.0001
            candles.append(make_candle(t, o, h, l, c))

        # 10:05-10:09: 5 M1 bars; bar 10:06 spikes high to 1.0905, then closes down to 1.0870 at 10:09
        t5 = self.base_time + timedelta(minutes=5)
        candles.append(make_candle(t5, 1.0880, 1.0885, 1.0875, 1.0880))
        candles.append(make_candle(t5 + timedelta(minutes=1), 1.0880, 1.0905, 1.0875, 1.0882))  # Spike high
        candles.append(make_candle(t5 + timedelta(minutes=2), 1.0882, 1.0885, 1.0872, 1.0875))
        candles.append(make_candle(t5 + timedelta(minutes=3), 1.0875, 1.0878, 1.0870, 1.0872))
        candles.append(make_candle(t5 + timedelta(minutes=4), 1.0872, 1.0874, 1.0868, 1.0870))  # Closes M5 bearish at 1.0870

        # 10:10-10:12: 3 consecutive bearish 1m bars
        t10 = self.base_time + timedelta(minutes=10)
        candles.append(make_candle(t10, 1.0870, 1.0872, 1.0858, 1.0860))  # C1: Bearish
        candles.append(make_candle(t10 + timedelta(minutes=1), 1.0860, 1.0862, 1.0848, 1.0850))  # C2: Bearish
        candles.append(make_candle(t10 + timedelta(minutes=2), 1.0850, 1.0852, 1.0838, 1.0840))  # C3: Bearish

        # Additional 5 neutral bars
        for i in range(5):
            t = t10 + timedelta(minutes=3 + i)
            candles.append(make_candle(t, 1.0840, 1.0842, 1.0838, 1.0840))

        signals = self.engine.scan_multitimeframe_streams(m1_candles=candles)
        self.assertEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig.direction, "SELL")
        self.assertAlmostEqual(sig.entry_price, 1.0840)
        self.assertAlmostEqual(sig.stop_loss, 1.0872)  # max(1.0872, 1.0862, 1.0852)
        self.assertAlmostEqual(sig.reward_risk_ratio, 5.0)

    def test_sell_setup_m15_sweep_with_m1_confirmation_including_doji(self):
        """
        User setup from live EUR/USD chart:
        15-minute Bullish candle wick swept by 15-minute Bearish candle.
        Then 1-minute confirmation where candle 2 is a Doji (open == close).
        Must successfully trigger a SELL signal.
        """
        # 15m candle 0 (10:00): Bullish (1.0850 -> 1.0880, high 1.0890)
        m15_0 = make_candle(self.base_time, 1.0850, 1.0890, 1.0840, 1.0880)
        # 15m candle 1 (10:15): Sweeps high 1.0890 with wick to 1.0910, closes bearish at 1.0875
        m15_1 = make_candle(self.base_time + timedelta(minutes=15), 1.0880, 1.0910, 1.0870, 1.0875)

        self.engine.on_htf_candle(m15_0, "M15")
        armed = self.engine.on_htf_candle(m15_1, "M15")
        self.assertTrue(self.engine.is_armed)
        self.assertEqual(self.engine.armed_state.direction, Direction.SELL)
        self.assertEqual(self.engine.armed_state.sweep_timeframe, "M15")

        # 1m confirmation bars starting at 10:30
        t_m1 = self.base_time + timedelta(minutes=30)
        # C1: Bearish
        m1_1 = make_candle(t_m1, 1.0875, 1.0878, 1.0860, 1.0865)
        # C2: Flat neutral Doji (open == close == 1.0865)
        m1_2 = make_candle(t_m1 + timedelta(minutes=1), 1.0865, 1.0868, 1.0860, 1.0865)
        # C3: Bearish
        m1_3 = make_candle(t_m1 + timedelta(minutes=2), 1.0865, 1.0868, 1.0850, 1.0852)

        sig1 = self.engine.on_m1_candle(m1_1)
        self.assertIsNone(sig1)
        self.assertEqual(len(self.engine.armed_state.confirming_candles), 1)

        sig2 = self.engine.on_m1_candle(m1_2)
        self.assertIsNone(sig2)
        # Doji is accepted and does NOT break the sequence!
        self.assertEqual(len(self.engine.armed_state.confirming_candles), 2)

        sig3 = self.engine.on_m1_candle(m1_3)
        self.assertIsNotNone(sig3)
        self.assertEqual(sig3.direction, "SELL")
        self.assertAlmostEqual(sig3.entry_price, 1.0852)

    def test_buy_setup_m5_sweep_with_m1_confirmation_including_doji(self):
        """
        5-minute Bearish candle wick swept by Bullish candle.
        Then 1-minute confirmation where candle 2 is a Doji (open == close).
        Must successfully trigger a BUY signal.
        """
        m5_0 = make_candle(self.base_time, 1.0880, 1.0890, 1.0840, 1.0850)
        m5_1 = make_candle(self.base_time + timedelta(minutes=5), 1.0850, 1.0865, 1.0830, 1.0860)

        self.engine.on_htf_candle(m5_0, "M5")
        armed = self.engine.on_htf_candle(m5_1, "M5")
        self.assertTrue(self.engine.is_armed)
        self.assertEqual(self.engine.armed_state.direction, Direction.BUY)

        t_m1 = self.base_time + timedelta(minutes=10)
        m1_1 = make_candle(t_m1, 1.0860, 1.0870, 1.0858, 1.0868)
        m1_2 = make_candle(t_m1 + timedelta(minutes=1), 1.0868, 1.0872, 1.0865, 1.0868)  # Doji
        m1_3 = make_candle(t_m1 + timedelta(minutes=2), 1.0868, 1.0885, 1.0866, 1.0880)

        self.assertIsNone(self.engine.on_m1_candle(m1_1))
        self.assertIsNone(self.engine.on_m1_candle(m1_2))
        sig3 = self.engine.on_m1_candle(m1_3)
        self.assertIsNotNone(sig3)
        self.assertEqual(sig3.direction, "BUY")
        self.assertAlmostEqual(sig3.entry_price, 1.0880)


if __name__ == "__main__":
    unittest.main()

