"""
Tests for AK Forex Strategy Strict Compliance Specification.

Validates 100% adherence to all sections:
- Section 0: Operating rules (No extra filters, no additions, no omissions, structured rule logging).
- Section 1: Definitions (Strict bullish close > open, bearish close < open, close == open strictly neither; HTF = M5, M15).
- Section 2: SELL rules (S1 - S6 tagged and evaluated).
- Section 3: BUY rules (B1 - B6 tagged and evaluated).
- Section 4: Golden test from user's annotated USDCAD trade on 13 Oct 2026.
- Section 5: Required tests:
  1. Golden SELL test.
  2. BUY mirror test with synthetic candles.
  3. Rejection tests (asserting log names failing rule):
     - No sweep (S1/B1)
     - H not bearish/bullish (S1/B1)
     - Only 2 confirming candles (S3/B3)
     - Run interrupted by wrong-color or doji candle (S3/B3, [A4])
     - c1.close not below L.close (S2) / c1.close not above L.close (B2)
     - Setup evaluated after H has closed (expiry, [A5])
  4. Allowed-variation tests (asserting setup is accepted):
     - c1's wick above L's high (S2)
     - c1's wick below L's low (B2)
     - Doji-like directional candle inside run (shape is irrelevant)
     - M5 qualifies while M15 does not
  5. Numeric tests:
     - TP multiple is exactly 10 (1:10 R:R)
     - Sell SL is above entry
     - Buy SL is below entry
- Section 8 & 9: Named constants and assumptions [A1 - A5].
"""

import math
import unittest
from datetime import datetime, timezone, timedelta

import config
from engine.models import Candle, Direction, TradeSignal
from engine.rule_engine import RuleEngine
from engine.sweep_detector import evaluate_s1_htf_sweep, evaluate_b1_htf_sweep
from engine.confirmation import (
    evaluate_s2_m1_validity,
    evaluate_b2_m1_validity,
    evaluate_s3_m1_confirmation,
    evaluate_b3_m1_confirmation,
    calculate_s4_entry,
    calculate_b4_entry,
    calculate_s5_stop_loss,
    calculate_b5_stop_loss,
    calculate_s6_take_profit,
    calculate_b6_take_profit,
    format_rule_log_record,
)


class TestConfigConstantsAndAssumptions(unittest.TestCase):
    """
    Validates Section 8 config constants and Section 9 assumptions [A1 - A5].
    """

    def test_section_8_config_constants(self):
        self.assertEqual(config.RR_MULTIPLE, 10)
        self.assertEqual(config.CONFIRM_CANDLES, 3)
        self.assertEqual(config.HTF, ["M5", "M15"])
        self.assertEqual(config.ENTRY_ORDER_TYPE, "market")
        self.assertEqual(config.SL_REFERENCE, "c1_extreme")

    def test_section_9_assumptions(self):
        self.assertTrue(config.A1_SWEEP_ON_FORMING_HTF)
        self.assertTrue(config.A2_M1_VALIDITY_STRICT_CLOSE)
        self.assertEqual(config.A3_RISK_REWARD_RATIO, 10.0)
        self.assertTrue(config.A4_RESET_ON_INTERRUPTION)
        self.assertTrue(config.A5_EXPIRE_ON_HTF_CLOSE)


class TestGoldenSellTrade(unittest.TestCase):
    """
    [Section 4] Golden test taken from user's annotated trade:
    USDCAD, SELL, 13 Oct 2026, chart timezone UTC+6 (14:00 UTC broker time).
    - M15: 19:45 is bullish; 20:00 wick sweeps 19:45 high and 20:00 is bearish.
    - M1: inside 20:00-20:15, bullish push around 20:04 (L), then c1, then 3 consecutive bearish candles (c1, c2, c3).
    - Entry on close of c3 (~20:10): 1.42335.
    - Stop-Loss: 1.42350 (c1.high, wick included).
    - Take-Profit: 1.42185 (risk = 0.00015, reward = 0.00150 = 1:10).
    """

    def test_golden_trade_synthetic_exact(self):
        engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

        # 19:45 UTC+6 (13:45 UTC): Bullish closed M15 candle P
        p_m15 = Candle(
            timestamp=datetime(2026, 10, 13, 13, 45, tzinfo=timezone.utc),
            open=1.42300,
            high=1.42340,
            low=1.42280,
            close=1.42330,  # close > open: bullish
        )

        # 20:00 UTC+6 (14:00 UTC): Forming M15 candle H that swept P's high (1.42360 > 1.42340) and is currently bearish
        h_m15 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc),
            open=1.42345,
            high=1.42360,
            low=1.42250,
            close=1.42320,  # current price < open: bearish
        )

        # M1 candle sequence inside 20:00 - 20:15
        # 20:04: Bullish candle L before c1
        l_candle = Candle(
            timestamp=datetime(2026, 10, 13, 14, 4, tzinfo=timezone.utc),
            open=1.42320,
            high=1.42340,
            low=1.42315,
            close=1.42338,  # bullish
        )
        # 20:08: c1 first bearish candle. High is 1.42350 (the SL), close 1.42336 < L.close (1.42338)
        c1 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 8, tzinfo=timezone.utc),
            open=1.42342,
            high=1.42350,
            low=1.42330,
            close=1.42336,  # bearish: close < open (1.42336 < 1.42342), and close < L.close (1.42338)
        )
        # 20:09: c2 second bearish candle
        c2 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 9, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42338,
            low=1.42332,
            close=1.42335,  # bearish
        )
        # 20:10: c3 third bearish candle. Close is 1.42335 (entry price)
        c3 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 10, tzinfo=timezone.utc),
            open=1.42335,
            high=1.42337,
            low=1.42330,
            close=1.42335 - 0.0000001 if False else 1.4233499,  # bearish: close < open
        )
        # Make sure c3 close is exactly 1.42335 per chart label
        c3 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 10, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42337,
            low=1.42330,
            close=1.42335,
        )

        m1_bars = [l_candle, c1, c2, c3]

        sig, log_rec = engine.evaluate_strict_rules(
            p_htf=p_m15,
            h_htf=h_m15,
            m1_candles=m1_bars,
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
            h_is_closed=False,
        )

        # Assert exactly one SELL signal produced
        self.assertIsNotNone(sig, "Expected a valid SELL TradeSignal from Golden Trade")
        self.assertEqual(sig.direction, "SELL")

        # Assert exact price values and mathematical relationships
        self.assertAlmostEqual(sig.entry_price, 1.42335, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42350, places=5)  # SL = high of c1
        expected_risk = round(1.42350 - 1.42335, 5)  # 0.00015
        self.assertAlmostEqual(sig.risk_distance, expected_risk, places=5)

        expected_tp = round(1.42335 - (10.0 * expected_risk), 5)  # 1.42185
        self.assertAlmostEqual(sig.take_profit, expected_tp, places=5)
        self.assertAlmostEqual(sig.take_profit, 1.42185, places=5)
        self.assertEqual(sig.reward_risk_ratio, 10.0)

        # Verify structured logging record
        self.assertTrue(log_rec["setup_passed"])
        self.assertIsNone(log_rec["failing_rule"])
        rule_ids = [r["rule_id"] for r in log_rec["rules"]]
        self.assertEqual(rule_ids, ["S1", "S2", "S3", "S4", "S5", "S6"])

    def test_golden_trade_feed_replay_through_on_m1(self):
        """
        Replay through live feed ingestion engine.on_htf_candle + engine.on_m1_candle.
        """
        engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

        # Ingest previous closed M15
        p_m15 = Candle(
            timestamp=datetime(2026, 10, 13, 13, 45, tzinfo=timezone.utc),
            open=1.42261,
            high=1.42316,
            low=1.42229,
            close=1.42311,  # bullish
        )
        engine.on_htf_candle(p_m15, "M15")

        # 14:00 sweeps 1.42316 with high 1.42360, opening at 1.42345 (so H is bearish at entry 1.42335)
        m1_00 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc),
            open=1.42345,
            high=1.42360,  # Swept 1.42316
            low=1.42320,
            close=1.42330,
        )
        # 14:04 bullish candle L
        m1_04 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 4, tzinfo=timezone.utc),
            open=1.42320,
            high=1.42340,
            low=1.42315,
            close=1.42338,  # bullish L
        )
        # 14:08 c1 bearish
        c1 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 8, tzinfo=timezone.utc),
            open=1.42342,
            high=1.42350,
            low=1.42330,
            close=1.42336,  # bearish, close < L.close
        )
        # 14:09 c2 bearish
        c2 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 9, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42338,
            low=1.42332,
            close=1.42335,  # bearish
        )
        # 14:10 c3 bearish (entry on close)
        c3 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 10, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42337,
            low=1.42330,
            close=1.42335,  # bearish
        )

        signals = []
        for m in [m1_00, m1_04, c1, c2, c3]:
            sig = engine.on_m1_candle(m)
            if sig:
                signals.append(sig)

        self.assertEqual(len(signals), 1, "Must produce exactly one SELL signal")
        sig = signals[0]
        self.assertEqual(sig.direction, "SELL")
        self.assertAlmostEqual(sig.entry_price, 1.42335, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42350, places=5)
        self.assertAlmostEqual(sig.take_profit, 1.42185, places=5)


class TestBuyMirrorTrade(unittest.TestCase):
    """
    [Section 5] One BUY mirror test with synthetic candles (Rules B1 - B6).
    """

    def test_buy_mirror_trade(self):
        engine = RuleEngine.strict_compliance_preset(symbol="EURUSDm")

        # P: Bearish closed HTF candle
        p_htf = Candle(
            timestamp=datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc),
            open=1.10500,
            high=1.10550,
            low=1.10200,
            close=1.10250,  # bearish
        )

        # H: Forming HTF candle that sweeps P.low (1.10150 < 1.10200) and is currently bullish
        h_htf = Candle(
            timestamp=datetime(2026, 10, 13, 8, 15, tzinfo=timezone.utc),
            open=1.10240,
            high=1.10400,
            low=1.10150,  # swept P.low
            close=1.10300,  # current price > open (bullish)
        )

        # M1 candle sequence inside H's window:
        # L: Bearish candle before c1
        l_candle = Candle(
            timestamp=datetime(2026, 10, 13, 8, 18, tzinfo=timezone.utc),
            open=1.10280,
            high=1.10290,
            low=1.10180,
            close=1.10200,  # bearish L
        )
        # c1: First bullish candle. Low is 1.10150 (the SL). Close is 1.10220 > L.close (1.10200)
        c1 = Candle(
            timestamp=datetime(2026, 10, 13, 8, 20, tzinfo=timezone.utc),
            open=1.10160,
            high=1.10230,
            low=1.10150,  # c1.low = Stop Loss
            close=1.10220,  # bullish: close > open and close > L.close
        )
        # c2: Second bullish candle
        c2 = Candle(
            timestamp=datetime(2026, 10, 13, 8, 21, tzinfo=timezone.utc),
            open=1.10220,
            high=1.10260,
            low=1.10210,
            close=1.10250,  # bullish
        )
        # c3: Third bullish candle. Close is 1.10280 (Entry price)
        c3 = Candle(
            timestamp=datetime(2026, 10, 13, 8, 22, tzinfo=timezone.utc),
            open=1.10250,
            high=1.10290,
            low=1.10240,
            close=1.10280,  # bullish
        )

        sig, log_rec = engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNotNone(sig, "Expected a valid BUY TradeSignal")
        self.assertEqual(sig.direction, "BUY")
        self.assertAlmostEqual(sig.entry_price, 1.10280, places=5)
        # [Rule B5] Stop-loss: the low of L, the bearish candle (wick included), per latest buy example. Not low of c1.
        self.assertAlmostEqual(sig.stop_loss, 1.10180, places=5)  # SL = low of L (1.10180)

        expected_risk = round(1.10280 - 1.10180, 5)  # 0.00100
        self.assertAlmostEqual(sig.risk_distance, expected_risk, places=5)
        expected_tp = round(1.10280 + (10.0 * expected_risk), 5)  # 1.11280
        self.assertAlmostEqual(sig.take_profit, expected_tp, places=5)
        self.assertEqual(sig.reward_risk_ratio, 10.0)

        # Assert B1-B6 tagged in log
        self.assertTrue(log_rec["setup_passed"])
        self.assertIsNone(log_rec["failing_rule"])
        rule_ids = [r["rule_id"] for r in log_rec["rules"]]
        self.assertEqual(rule_ids, ["B1", "B2", "B3", "B4", "B5", "B6"])


class TestRejectionRules(unittest.TestCase):
    """
    [Section 5] Rejection tests, each asserting the log names the failing rule:
    - no sweep (S1/B1)
    - H not bearish/bullish (S1/B1)
    - only 2 confirming candles (S3/B3)
    - run interrupted by a wrong-color candle ([A4])
    - c1.close not below L.close (S2) / c1.close not above L.close (B2)
    - sweep present only after H has closed (expiry, [A5])
    """

    def setUp(self):
        self.engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

    def test_rejection_s1_no_sweep(self):
        # P is bullish, H.high <= P.high
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4210, 1.4220)  # high not > 1.4250
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.SELL, current_price=1.4220
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S1")

    def test_rejection_b1_no_sweep(self):
        # P is bearish, H.low >= P.low
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4205, 1.4230)  # low not < 1.4200
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.BUY, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B1")

    def test_rejection_s1_h_not_bearish(self):
        # P is bullish, H swept high, but current price > H.open (H is bullish)
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4230, 1.4250)
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.SELL, current_price=1.4255  # > h.open 1.4240
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S1")

    def test_rejection_b1_h_not_bullish(self):
        # P is bearish, H swept low, but current price < H.open (H is bearish)
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4200)
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.BUY, current_price=1.4205  # < h.open 1.4210
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B1")

    def test_rejection_s2_c1_close_not_below_l_close(self):
        # S2: c1.close must be < L.close. Here c1.close >= L.close
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4235, 1.4228, 1.4234)
        # c1 is bearish (1.4245 -> 1.4235), but close (1.4235) is > L.close (1.4234)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4245, 1.4250, 1.4234, 1.4235)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1], timeframe="M15", direction=Direction.SELL, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S2")

    def test_rejection_b2_c1_low_not_le_l_low(self):
        # B2: Require c1.low <= L.low (wick check). Here c1.low > L.low
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        # L is bearish with low 1.4210
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4210, 1.4215)
        # c1 is bullish, but low (1.4215) is > L.low (1.4210), so c1.low <= L.low FAILS
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4216, 1.4225, 1.4215, 1.4222)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1], timeframe="M15", direction=Direction.BUY, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B2")

    def test_rejection_s3_only_two_confirming_candles(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4230, 1.4233)  # bearish, < L.close
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)  # bearish

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1, c2], timeframe="M15", direction=Direction.SELL, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S3")

    def test_rejection_interrupted_run(self):
        """
        [A4] Non-qualifying candle interrupts run before c3 closes.
        c1 bearish, c2 bearish, then bullish candle, then only 1 bearish candle -> discarded.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4230, 1.4233)  # bearish
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)  # bearish
        interruption = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4230, 1.4236, 1.4229, 1.4235)  # BULLISH!
        new_c1 = Candle(datetime(2026, 10, 13, 10, 20, tzinfo=timezone.utc), 1.4235, 1.4237, 1.4227, 1.4229)  # bearish

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, interruption, new_c1],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=1.4229,
        )
        self.assertIsNone(sig, "Interrupted run must be discarded and fail S3 confirmation")
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S3")

    def test_rejection_doji_interruption(self):
        """
        Candle with close == open is strictly neither bullish nor bearish, and interrupts run [A4].
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4230, 1.4233)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)
        doji = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4230, 1.4235, 1.4225, 1.4230)  # close == open
        c3 = Candle(datetime(2026, 10, 13, 10, 20, tzinfo=timezone.utc), 1.4230, 1.4232, 1.4222, 1.4226)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, doji, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=1.4226,
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S3")

    def test_rejection_sweep_after_h_closed_expiry(self):
        """
        [A5] A setup expires when H closes. If evaluated after H has closed, reject.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4230, 1.4233)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4230, 1.4232, 1.4224, 1.4227)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=1.4227,
            h_is_closed=True,  # H has closed -> EXPIRED!
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S1")


class TestAllowedVariations(unittest.TestCase):
    """
    [Section 5] Allowed-variation tests, each asserting the setup is accepted:
    - c1's wick above L's high (S2)
    - c1's wick below L's low (B2)
    - doji-like directional candle inside the run
    - M5 qualifies while M15 does not
    """

    def setUp(self):
        self.engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

    def test_c1_wick_above_l_high_accepted(self):
        """
        S2: "c1's high may exceed L's high; never reject for that."
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4270, 1.4210, 1.4230)
        # L has high 1.4238, close 1.4236
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        # c1 has high 1.4265 (WAY higher than L's high 1.4238!), but close 1.4233 < L.close
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4240, 1.4265, 1.4230, 1.4233)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4230, 1.4232, 1.4224, 1.4227)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
        )
        self.assertIsNotNone(sig, "c1's wick exceeding L's high must be ACCEPTED")
        self.assertTrue(log_rec["setup_passed"])
        self.assertAlmostEqual(sig.stop_loss, 1.4265, places=5)  # SL is c1.high

    def test_c1_wick_below_l_low_accepted(self):
        """
        B2: "Require c1.low <= L.low (the bearish candle's wick is smaller than or equal to the bullish candle's wick)."
        B5: "Stop-loss: the low of L, the bearish candle (wick included), per my latest buy example. Not the low of c1."
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        # L has low 1.4215, close 1.4218
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4215, 1.4218)
        # c1 has low 1.4200 (< L.low 1.4215)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4205, 1.4225, 1.4200, 1.4222)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4222, 1.4227, 1.4220, 1.4225)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4225, 1.4230, 1.4223, 1.4228)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
        )
        self.assertIsNotNone(sig, "c1's wick going below L's low must be ACCEPTED")
        self.assertTrue(log_rec["setup_passed"])
        self.assertAlmostEqual(sig.stop_loss, 1.4215, places=5)  # [Rule B5] SL is L.low (1.4215), NOT c1.low

    def test_c1_wick_equal_l_low_accepted(self):
        """
        B2: "Equal passes." Test c1.low == L.low.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        # L has low 1.4215, close 1.4218
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4215, 1.4218)
        # c1 has low 1.4215 (== L.low 1.4215)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4216, 1.4225, 1.4215, 1.4222)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4222, 1.4227, 1.4220, 1.4225)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4225, 1.4230, 1.4223, 1.4228)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
        )
        self.assertIsNotNone(sig, "c1's wick equal to L's low must be ACCEPTED per B2 ('Equal passes')")
        self.assertTrue(log_rec["setup_passed"])
        self.assertAlmostEqual(sig.stop_loss, 1.4215, places=5)  # [Rule B5] SL is L.low

    def test_doji_like_directional_candle_accepted(self):
        """
        Section 1: "Shape is irrelevant (engulfing, doji-like, anything counts); only the direction of the close vs open counts."
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4230, 1.4233)
        # c2 has huge wicks (0.0010) but tiny body where close is just 0.00001 below open: doji-like but strictly bearish!
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.42330, 1.42400, 1.42200, 1.42329)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.42329, 1.42335, 1.42240, 1.42270)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
        )
        self.assertIsNotNone(sig, "Doji-like candle with close < open must be ACCEPTED")
        self.assertTrue(log_rec["setup_passed"])

    def test_m5_qualifies_while_m15_does_not(self):
        """
        Section 1: "HTF = M15 and M5, each evaluated independently. Either can qualify a setup."
        """
        engine = RuleEngine.strict_compliance_preset(symbol="USDCADm", check_m5=True, check_m15=True)

        # M15 has no sweep
        p_m15 = Candle(datetime(2026, 10, 13, 9, 45, tzinfo=timezone.utc), 1.4200, 1.4280, 1.4190, 1.4270)
        engine.on_htf_candle(p_m15, "M15")

        # M5 has a valid S1 sweep!
        p_m5 = Candle(datetime(2026, 10, 13, 9, 55, tzinfo=timezone.utc), 1.4220, 1.4230, 1.4215, 1.4228)
        engine.on_htf_candle(p_m5, "M5")

        # M1 forming inside 10:00 - 10:05 M5 window:
        m1_00 = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4228, 1.4235, 1.4224, 1.4226)  # sweeps 1.4230
        l_candle = Candle(datetime(2026, 10, 13, 10, 1, tzinfo=timezone.utc), 1.4225, 1.4232, 1.4223, 1.4230)
        c1 = Candle(datetime(2026, 10, 13, 10, 2, tzinfo=timezone.utc), 1.4232, 1.4234, 1.4227, 1.4228)  # bearish < L.close
        c2 = Candle(datetime(2026, 10, 13, 10, 3, tzinfo=timezone.utc), 1.4228, 1.4230, 1.4224, 1.4226)  # bearish
        c3 = Candle(datetime(2026, 10, 13, 10, 4, tzinfo=timezone.utc), 1.4226, 1.4227, 1.4220, 1.4222)  # bearish

        signals = []
        for m in [m1_00, l_candle, c1, c2, c3]:
            sig = engine.on_m1_candle(m)
            if sig:
                signals.append(sig)

        self.assertEqual(len(signals), 1, "M5 must qualify independently even when M15 does not")
        self.assertEqual(signals[0].sweep_timeframe, "M5")


class TestNumericRules(unittest.TestCase):
    """
    [Section 5] Numeric tests:
    - TP multiple is exactly 10
    - sell SL is above entry
    - buy SL is below entry
    """

    def test_sell_numeric_relationships(self):
        c1 = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4240, 1.4250, 1.4230, 1.4235)
        c3 = Candle(datetime(2026, 10, 13, 10, 2, tzinfo=timezone.utc), 1.4235, 1.4236, 1.4230, 1.4233)

        entry, _ = calculate_s4_entry(c3)
        sl, _ = calculate_s5_stop_loss(c1)
        tp, _ = calculate_s6_take_profit(entry, sl, rr_multiple=10.0)

        # SL must be strictly above entry for a SELL
        self.assertGreater(sl, entry)
        risk = sl - entry
        self.assertGreater(risk, 0.0)

        # TP = entry - 10 * (SL - entry)
        reward = entry - tp
        self.assertAlmostEqual(reward / risk, 10.0, places=5)
        self.assertAlmostEqual(tp, entry - 10.0 * risk, places=5)

    def test_buy_numeric_relationships(self):
        # [Rule B5] Stop-loss: the low of L, the bearish candle (wick included). Not the low of c1.
        l_candle = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4220, 1.4225, 1.4200, 1.4210)
        c3 = Candle(datetime(2026, 10, 13, 10, 2, tzinfo=timezone.utc), 1.4220, 1.4230, 1.4219, 1.4228)

        entry, _ = calculate_b4_entry(c3)
        sl, _ = calculate_b5_stop_loss(l_candle, entry=entry)
        tp, _ = calculate_b6_take_profit(entry, sl, rr_multiple=10.0)

        # SL must be strictly below entry for a BUY
        self.assertLess(sl, entry)
        risk = entry - sl
        self.assertGreater(risk, 0.0)

        # TP = entry + 10 * (entry - SL)
        reward = tp - entry
        self.assertAlmostEqual(reward / risk, 10.0, places=5)
        self.assertAlmostEqual(tp, entry + 10.0 * risk, places=5)


if __name__ == "__main__":
    unittest.main()
