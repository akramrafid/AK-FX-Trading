"""
Tests for AK Forex Strategy Strict Compliance Specification.

Validates 100% adherence to all sections:
- Section 0: Operating rules (No extra filters, no additions, no omissions, structured rule logging).
- Section 1: Definitions (Strict bullish close > open, bearish close < open, close == open strictly neither; HTF = M5, M15).
- Section 2: SELL rules (S1 - S6 tagged and evaluated).
- Section 3: BUY rules (B1 - B6 tagged and evaluated).
- Section 5: Golden tests (synthetic 4 cases: SELL base equal, SELL variant wick_swap, BUY base equal, BUY variant wick_swap).
- Section 6: Required tests:
  1. The four golden cases from Section 5.
  2. Gate rejections (c1.high = 1.42319 for SELL, c1.low = 1.42481 for BUY; log names S2/B2).
  3. Other rejections naming failing rule (no sweep, H wrong colour, 2 candles, interrupted run, L same colour or doji, sweep after H closed).
  4. Allowed variations accepted (doji-like directional candle inside run, M5 qualifies while M15 does not).
  5. Numeric tests (TP multiple exactly 10, sell SL above entry, buy SL below entry, SL always equals c1's wick extreme).
- Section 9: Named constants.
- Section 10: Assumptions [A1 - A6].
"""

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
    Validates Section 9 config constants and Section 10 assumptions [A1 - A6].
    """

    def test_section_9_config_constants(self):
        self.assertEqual(config.RR_MULTIPLE, 10)
        self.assertEqual(config.CONFIRM_CANDLES, 3)
        self.assertEqual(config.HTF, ["M5", "M15"])
        self.assertEqual(config.ENTRY_ORDER_TYPE, "market")
        self.assertEqual(config.EQUAL_TOLERANCE_POINTS, 0.0)
        self.assertEqual(config.SL_REFERENCE, "c1_wick_extreme")
        self.assertEqual(config.M1_METHODS, ["equal", "wick_swap"])

    def test_section_10_assumptions(self):
        self.assertTrue(config.A1_SWEEP_ON_FORMING_HTF)
        self.assertEqual(config.A2_EQUAL_TOLERANCE_POINTS, 0.0)
        self.assertTrue(config.A3_SL_IS_C1_WICK_EXTREME)
        self.assertTrue(config.A4_RESET_ON_INTERRUPTION)
        self.assertTrue(config.A5_EXPIRE_ON_HTF_CLOSE)
        self.assertTrue(config.A6_L_MUST_BE_IMMEDIATE_PREVIOUS_OPPOSITE)


class TestGoldenCases(unittest.TestCase):
    """
    [Section 5 & Section 6.1] Four synthetic golden cases inside a valid S1/B1 setup:
    1. SELL base case (method S2-A, equal top)
    2. SELL variant (method S2-B, wick swap)
    3. BUY base case (method B2-A, equal low)
    4. BUY variant (method B2-B, wick swap)
    """

    def setUp(self):
        self.engine = RuleEngine.strict_compliance_preset(symbol="EURUSDm")

    def test_golden_sell_base_case_equal_top(self):
        """
        SELL base case (method S2-A, equal top)
        L (bullish)  1.42300  1.42320  1.42295  1.42316
        c1 (bearish) 1.42316  1.42320  1.42300  1.42304
        c2 (bearish) 1.42304  1.42308  1.42290  1.42294
        c3 (bearish) 1.42294  1.42298  1.42280  1.42284
        Expected: one SELL at 1.42284, SL 1.42320, TP 1.41924, method "equal".
        """
        p_htf = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.42250, 1.42310, 1.42200, 1.42300)
        h_htf = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.42330, 1.42350, 1.42250, 1.42284)

        l_cand = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.42300, 1.42320, 1.42295, 1.42316)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.42316, 1.42320, 1.42300, 1.42304)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.42304, 1.42308, 1.42290, 1.42294)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.42294, 1.42298, 1.42280, 1.42284)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_cand, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNotNone(sig, "Must produce a valid SELL TradeSignal")
        self.assertEqual(sig.direction, "SELL")
        self.assertAlmostEqual(sig.entry_price, 1.42284, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42320, places=5)
        self.assertAlmostEqual(sig.take_profit, 1.41924, places=5)
        self.assertEqual(log_rec["method"], "equal")
        self.assertTrue(log_rec["setup_passed"])
        self.assertIsNone(log_rec["failing_rule"])
        rule_ids = [r["rule_id"] for r in log_rec["rules"]]
        self.assertEqual(rule_ids, ["S1", "S2", "S3", "S4", "S5", "S6"])

    def test_golden_sell_variant_wick_swap(self):
        """
        SELL variant (method S2-B, wick swap)
        c1.high = 1.42326 (all other values same as base case).
        Expected: one SELL at 1.42284, SL 1.42326, TP 1.41864, method "wick_swap".
        """
        p_htf = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.42250, 1.42310, 1.42200, 1.42300)
        h_htf = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.42330, 1.42350, 1.42250, 1.42284)

        l_cand = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.42300, 1.42320, 1.42295, 1.42316)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.42316, 1.42326, 1.42300, 1.42304)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.42304, 1.42308, 1.42290, 1.42294)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.42294, 1.42298, 1.42280, 1.42284)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_cand, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNotNone(sig, "Must produce a valid SELL TradeSignal")
        self.assertEqual(sig.direction, "SELL")
        self.assertAlmostEqual(sig.entry_price, 1.42284, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42326, places=5)
        self.assertAlmostEqual(sig.take_profit, 1.41864, places=5)
        self.assertEqual(log_rec["method"], "wick_swap")
        self.assertTrue(log_rec["setup_passed"])

    def test_golden_buy_base_case_equal_low(self):
        """
        BUY base case (method B2-A, equal low)
        L (bearish)  1.42500  1.42505  1.42480  1.42484
        c1 (bullish) 1.42484  1.42500  1.42480  1.42496
        c2 (bullish) 1.42496  1.42512  1.42492  1.42508
        c3 (bullish) 1.42508  1.42524  1.42504  1.42520
        Expected: one BUY at 1.42520, SL 1.42480, TP 1.42920, method "equal".
        """
        p_htf = Candle(datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc), 1.42600, 1.42650, 1.42500, 1.42510)
        h_htf = Candle(datetime(2026, 10, 13, 8, 15, tzinfo=timezone.utc), 1.42470, 1.42550, 1.42460, 1.42520)

        l_cand = Candle(datetime(2026, 10, 13, 8, 16, tzinfo=timezone.utc), 1.42500, 1.42505, 1.42480, 1.42484)
        c1 = Candle(datetime(2026, 10, 13, 8, 17, tzinfo=timezone.utc), 1.42484, 1.42500, 1.42480, 1.42496)
        c2 = Candle(datetime(2026, 10, 13, 8, 18, tzinfo=timezone.utc), 1.42496, 1.42512, 1.42492, 1.42508)
        c3 = Candle(datetime(2026, 10, 13, 8, 19, tzinfo=timezone.utc), 1.42508, 1.42524, 1.42504, 1.42520)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_cand, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNotNone(sig, "Must produce a valid BUY TradeSignal")
        self.assertEqual(sig.direction, "BUY")
        self.assertAlmostEqual(sig.entry_price, 1.42520, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42480, places=5)
        self.assertAlmostEqual(sig.take_profit, 1.42920, places=5)
        self.assertEqual(log_rec["method"], "equal")
        self.assertTrue(log_rec["setup_passed"])
        self.assertIsNone(log_rec["failing_rule"])
        rule_ids = [r["rule_id"] for r in log_rec["rules"]]
        self.assertEqual(rule_ids, ["B1", "B2", "B3", "B4", "B5", "B6"])

    def test_golden_buy_variant_wick_swap(self):
        """
        BUY variant (method B2-B, wick swap)
        c1.low = 1.42474 (all other values same as base case).
        Expected: one BUY at 1.42520, SL 1.42474 (not L.low!), TP 1.42980, method "wick_swap".
        """
        p_htf = Candle(datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc), 1.42600, 1.42650, 1.42500, 1.42510)
        h_htf = Candle(datetime(2026, 10, 13, 8, 15, tzinfo=timezone.utc), 1.42470, 1.42550, 1.42460, 1.42520)

        l_cand = Candle(datetime(2026, 10, 13, 8, 16, tzinfo=timezone.utc), 1.42500, 1.42505, 1.42480, 1.42484)
        c1 = Candle(datetime(2026, 10, 13, 8, 17, tzinfo=timezone.utc), 1.42484, 1.42500, 1.42474, 1.42496)
        c2 = Candle(datetime(2026, 10, 13, 8, 18, tzinfo=timezone.utc), 1.42496, 1.42512, 1.42492, 1.42508)
        c3 = Candle(datetime(2026, 10, 13, 8, 19, tzinfo=timezone.utc), 1.42508, 1.42524, 1.42504, 1.42520)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_cand, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNotNone(sig, "Must produce a valid BUY TradeSignal")
        self.assertEqual(sig.direction, "BUY")
        self.assertAlmostEqual(sig.entry_price, 1.42520, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42474, places=5)
        self.assertAlmostEqual(sig.take_profit, 1.42980, places=5)
        self.assertEqual(log_rec["method"], "wick_swap")
        self.assertTrue(log_rec["setup_passed"])


class TestGateRejections(unittest.TestCase):
    """
    [Section 6.2] Gate rejections:
    Valid HTF, valid 3 confirming candles, must NOT trade, log must name S2/B2:
    - SELL with c1.high = 1.42319 (one point below L.high) -> fails S2
    - BUY with c1.low = 1.42481 (one point above L.low) -> fails B2
    """

    def setUp(self):
        self.engine = RuleEngine.strict_compliance_preset(symbol="EURUSDm")

    def test_sell_gate_rejection_c1_high_below_l_high(self):
        """
        SELL setup where c1.high = 1.42319 is strictly below L.high = 1.42320.
        All 3 candles are bearish. Valid HTF.
        Must NOT trade. Log must name S2.
        """
        p_htf = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.42250, 1.42310, 1.42200, 1.42300)
        h_htf = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.42330, 1.42350, 1.42250, 1.42284)

        l_cand = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.42300, 1.42320, 1.42295, 1.42316)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.42316, 1.42319, 1.42300, 1.42304)  # 1 pt below L.high
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.42304, 1.42308, 1.42290, 1.42294)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.42294, 1.42298, 1.42280, 1.42284)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_cand, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNone(sig, "Must NOT trade when S2 method gate fails")
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S2")

    def test_buy_gate_rejection_c1_low_above_l_low(self):
        """
        BUY setup where c1.low = 1.42481 is strictly above L.low = 1.42480.
        All 3 candles are bullish. Valid HTF.
        Must NOT trade. Log must name B2.
        """
        p_htf = Candle(datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc), 1.42600, 1.42650, 1.42500, 1.42510)
        h_htf = Candle(datetime(2026, 10, 13, 8, 15, tzinfo=timezone.utc), 1.42470, 1.42550, 1.42460, 1.42520)

        l_cand = Candle(datetime(2026, 10, 13, 8, 16, tzinfo=timezone.utc), 1.42500, 1.42505, 1.42480, 1.42484)
        c1 = Candle(datetime(2026, 10, 13, 8, 17, tzinfo=timezone.utc), 1.42484, 1.42500, 1.42481, 1.42496)  # 1 pt above L.low
        c2 = Candle(datetime(2026, 10, 13, 8, 18, tzinfo=timezone.utc), 1.42496, 1.42512, 1.42492, 1.42508)
        c3 = Candle(datetime(2026, 10, 13, 8, 19, tzinfo=timezone.utc), 1.42508, 1.42524, 1.42504, 1.42520)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p_htf,
            h_htf=h_htf,
            m1_candles=[l_cand, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNone(sig, "Must NOT trade when B2 method gate fails")
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B2")


class TestOtherRejections(unittest.TestCase):
    """
    [Section 6.3] Other rejections, each naming the failing rule:
    - no HTF sweep (S1 / B1)
    - H wrong colour (S1 / B1)
    - only 2 confirming candles (S3 / B3)
    - run interrupted by a wrong-colour candle (S3 / B3)
    - L same colour as c1 or a doji (S2 / B2)
    - sweep appearing only after H closed (S1 / B1)
    """

    def setUp(self):
        self.engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

    def test_rejection_sell_no_htf_sweep(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4245, 1.4210, 1.4220)  # high <= P.high
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.SELL, current_price=1.4220
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S1")

    def test_rejection_buy_no_htf_sweep(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4205, 1.4230)  # low >= P.low
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.BUY, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B1")

    def test_rejection_sell_h_wrong_colour(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4230, 1.4250)
        # current price > H.open (1.4255 > 1.4240): H is bullish, not bearish
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.SELL, current_price=1.4255
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S1")

    def test_rejection_buy_h_wrong_colour(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4200)
        # current price < H.open (1.4205 < 1.4210): H is bearish, not bullish
        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[], timeframe="M15", direction=Direction.BUY, current_price=1.4205
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B1")

    def test_rejection_sell_only_two_confirming_candles(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4238, 1.4240, 1.4230, 1.4233)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1, c2], timeframe="M15", direction=Direction.SELL, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S3")

    def test_rejection_buy_only_two_confirming_candles(self):
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4215, 1.4218)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4216, 1.4225, 1.4214, 1.4222)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4222, 1.4227, 1.4220, 1.4225)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1, c2], timeframe="M15", direction=Direction.BUY, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B3")

    def test_rejection_sell_run_interrupted_by_wrong_colour_candle(self):
        """
        [A4] A wrong-colour candle interrupts run before c3 closes -> discard run.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4238, 1.4240, 1.4230, 1.4233)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4233, 1.4235, 1.4228, 1.4230)
        interruption = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4230, 1.4236, 1.4229, 1.4235)  # BULLISH!

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, interruption],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=1.4235,
        )
        self.assertIsNone(sig, "Interrupted run must be discarded and fail S3 confirmation")
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S3")

    def test_rejection_buy_run_interrupted_by_wrong_colour_candle(self):
        """
        [A4] A wrong-colour candle interrupts run before c3 closes -> discard run.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4215, 1.4218)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4216, 1.4225, 1.4214, 1.4222)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4222, 1.4227, 1.4220, 1.4225)
        interruption = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4225, 1.4227, 1.4219, 1.4220)  # BEARISH!

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, interruption],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=1.4220,
        )
        self.assertIsNone(sig, "Interrupted run must be discarded and fail B3 confirmation")
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B3")

    def test_rejection_sell_l_same_colour_as_c1(self):
        """
        L must be opposite colour of c1 (bullish for a sell). If L is bearish, reject at S2.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        # L is bearish (close < open: 1.4234 < 1.4236)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4236, 1.4238, 1.4228, 1.4234)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4234, 1.4238, 1.4225, 1.4230)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1], timeframe="M15", direction=Direction.SELL, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S2")

    def test_rejection_sell_l_is_doji(self):
        """
        L is a doji (close == open); strictly neither bullish nor bearish. Must fail S2.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        # L is doji
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4235, 1.4238, 1.4228, 1.4235)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4235, 1.4238, 1.4225, 1.4230)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1], timeframe="M15", direction=Direction.SELL, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "S2")

    def test_rejection_buy_l_same_colour_as_c1(self):
        """
        L must be opposite colour of c1 (bearish for a buy). If L is bullish, reject at B2.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        # L is bullish (close > open: 1.4222 > 1.4218)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4218, 1.4225, 1.4215, 1.4222)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4222, 1.4228, 1.4215, 1.4226)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1], timeframe="M15", direction=Direction.BUY, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B2")

    def test_rejection_buy_l_is_doji(self):
        """
        L is a doji (close == open); strictly neither bullish nor bearish. Must fail B2.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        # L is doji
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4220, 1.4225, 1.4215, 1.4220)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4220, 1.4228, 1.4215, 1.4226)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p, h_htf=h, m1_candles=[l_candle, c1], timeframe="M15", direction=Direction.BUY, current_price=1.4230
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B2")

    def test_rejection_sell_sweep_after_h_closed(self):
        """
        [A5] A setup expires when H closes. If evaluated after H has closed, reject at S1.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4238, 1.4240, 1.4230, 1.4233)
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

    def test_rejection_buy_sweep_after_h_closed(self):
        """
        [A5] A setup expires when H closes. If evaluated after H has closed, reject at B1.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4215, 1.4218)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4216, 1.4225, 1.4215, 1.4222)
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.4222, 1.4227, 1.4220, 1.4225)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.4225, 1.4230, 1.4223, 1.4228)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=1.4228,
            h_is_closed=True,  # H has closed -> EXPIRED!
        )
        self.assertIsNone(sig)
        self.assertFalse(log_rec["setup_passed"])
        self.assertEqual(log_rec["failing_rule"], "B1")


class TestAllowedVariations(unittest.TestCase):
    """
    [Section 6.4] Allowed-variation tests, each asserting the setup is accepted:
    - doji-like directional candle inside the run
    - M5 qualifies while M15 does not (and vice-versa)
    """

    def setUp(self):
        self.engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

    def test_sell_doji_like_directional_candle_accepted(self):
        """
        Section 1: "Shape is irrelevant (engulfing, doji-like, anything counts); only the direction of the close vs open counts."
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4200, 1.4250, 1.4190, 1.4240)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4240, 1.4260, 1.4210, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4230, 1.4238, 1.4228, 1.4236)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4238, 1.4240, 1.4230, 1.4233)
        # c2 has huge wicks but tiny body where close is just 0.00001 below open: doji-like but strictly bearish!
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

    def test_buy_doji_like_directional_candle_accepted(self):
        """
        Section 1: Buy with doji-like candle where close is strictly > open.
        """
        p = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4250, 1.4260, 1.4200, 1.4210)
        h = Candle(datetime(2026, 10, 13, 10, 15, tzinfo=timezone.utc), 1.4210, 1.4240, 1.4190, 1.4230)
        l_candle = Candle(datetime(2026, 10, 13, 10, 16, tzinfo=timezone.utc), 1.4225, 1.4228, 1.4215, 1.4218)
        c1 = Candle(datetime(2026, 10, 13, 10, 17, tzinfo=timezone.utc), 1.4216, 1.4225, 1.4214, 1.4222)
        # c2 has huge wicks but tiny body where close is just 0.00001 above open: doji-like but strictly bullish!
        c2 = Candle(datetime(2026, 10, 13, 10, 18, tzinfo=timezone.utc), 1.42220, 1.42300, 1.42100, 1.42221)
        c3 = Candle(datetime(2026, 10, 13, 10, 19, tzinfo=timezone.utc), 1.42221, 1.42280, 1.42200, 1.42260)

        sig, log_rec = self.engine.evaluate_strict_rules(
            p_htf=p,
            h_htf=h,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.BUY,
            current_price=c3.close,
        )
        self.assertIsNotNone(sig, "Doji-like candle with close > open must be ACCEPTED")
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
        c1 = Candle(datetime(2026, 10, 13, 10, 2, tzinfo=timezone.utc), 1.4230, 1.4234, 1.4227, 1.4228)  # c1.high > L.high
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
    [Section 6.5] Numeric tests:
    - TP multiple is exactly 10 (1:10 R:R)
    - Sell SL is above entry
    - Buy SL is below entry
    - SL always equals c1's wick extreme
    """

    def test_sell_numeric_relationships(self):
        c1 = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4240, 1.4250, 1.4230, 1.4235)
        c3 = Candle(datetime(2026, 10, 13, 10, 2, tzinfo=timezone.utc), 1.4235, 1.4236, 1.4230, 1.4233)

        entry, s4_data = calculate_s4_entry(c3)
        sl, s5_data = calculate_s5_stop_loss(c1, entry=entry)
        tp, s6_data = calculate_s6_take_profit(entry, sl, rr_multiple=10.0)

        # SL must be strictly above entry for a SELL
        self.assertGreater(sl, entry)
        # SL always equals c1's wick extreme (c1.high)
        self.assertEqual(sl, c1.high)
        risk = sl - entry
        self.assertGreater(risk, 0.0)

        # TP = entry - 10 * (SL - entry)
        reward = entry - tp
        self.assertAlmostEqual(reward / risk, 10.0, places=5)
        self.assertAlmostEqual(tp, entry - 10.0 * risk, places=5)

    def test_buy_numeric_relationships(self):
        c1 = Candle(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), 1.4220, 1.4225, 1.4210, 1.4223)
        c3 = Candle(datetime(2026, 10, 13, 10, 2, tzinfo=timezone.utc), 1.4220, 1.4230, 1.4219, 1.4228)

        entry, b4_data = calculate_b4_entry(c3)
        sl, b5_data = calculate_b5_stop_loss(c1, entry=entry)
        tp, b6_data = calculate_b6_take_profit(entry, sl, rr_multiple=10.0)

        # SL must be strictly below entry for a BUY
        self.assertLess(sl, entry)
        # SL always equals c1's wick extreme (c1.low)
        self.assertEqual(sl, c1.low)
        risk = entry - sl
        self.assertGreater(risk, 0.0)

        # TP = entry + 10 * (entry - SL)
        reward = tp - entry
        self.assertAlmostEqual(reward / risk, 10.0, places=5)
        self.assertAlmostEqual(tp, entry + 10.0 * risk, places=5)


class TestHistoricalAnnotatedTrade(unittest.TestCase):
    """
    USDCAD SELL annotated trade on 13 Oct 2026 (chart timezone UTC+6, 14:00 UTC broker time).
    Verifies that real historical setup passes S1-S6 with method "wick_swap".
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
        l_candle = Candle(
            timestamp=datetime(2026, 10, 13, 14, 4, tzinfo=timezone.utc),
            open=1.42320,
            high=1.42340,
            low=1.42315,
            close=1.42338,  # bullish
        )
        c1 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 8, tzinfo=timezone.utc),
            open=1.42342,
            high=1.42350,  # wick swaps L.high (1.42350 > 1.42340) -> S2-B
            low=1.42330,
            close=1.42336,  # bearish
        )
        c2 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 9, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42338,
            low=1.42332,
            close=1.42335,  # bearish
        )
        c3 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 10, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42337,
            low=1.42330,
            close=1.42335,  # bearish
        )

        sig, log_rec = engine.evaluate_strict_rules(
            p_htf=p_m15,
            h_htf=h_m15,
            m1_candles=[l_candle, c1, c2, c3],
            timeframe="M15",
            direction=Direction.SELL,
            current_price=c3.close,
            h_is_closed=False,
        )

        self.assertIsNotNone(sig, "Expected a valid SELL TradeSignal from Golden Trade")
        self.assertEqual(sig.direction, "SELL")
        self.assertAlmostEqual(sig.entry_price, 1.42335, places=5)
        self.assertAlmostEqual(sig.stop_loss, 1.42350, places=5)  # SL = high of c1
        expected_risk = round(1.42350 - 1.42335, 5)  # 0.00015
        self.assertAlmostEqual(sig.risk_distance, expected_risk, places=5)
        expected_tp = round(1.42335 - (10.0 * expected_risk), 5)  # 1.42185
        self.assertAlmostEqual(sig.take_profit, expected_tp, places=5)
        self.assertEqual(sig.reward_risk_ratio, 10.0)
        self.assertEqual(log_rec["method"], "wick_swap")
        self.assertTrue(log_rec["setup_passed"])
        self.assertIsNone(log_rec["failing_rule"])
        rule_ids = [r["rule_id"] for r in log_rec["rules"]]
        self.assertEqual(rule_ids, ["S1", "S2", "S3", "S4", "S5", "S6"])

    def test_golden_trade_feed_replay_through_on_m1(self):
        engine = RuleEngine.strict_compliance_preset(symbol="USDCADm")

        p_m15 = Candle(
            timestamp=datetime(2026, 10, 13, 13, 45, tzinfo=timezone.utc),
            open=1.42261,
            high=1.42316,
            low=1.42229,
            close=1.42311,  # bullish
        )
        engine.on_htf_candle(p_m15, "M15")

        m1_00 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc),
            open=1.42345,
            high=1.42360,
            low=1.42320,
            close=1.42330,
        )
        m1_04 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 4, tzinfo=timezone.utc),
            open=1.42320,
            high=1.42340,
            low=1.42315,
            close=1.42338,  # bullish L
        )
        c1 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 8, tzinfo=timezone.utc),
            open=1.42342,
            high=1.42350,
            low=1.42330,
            close=1.42336,  # bearish
        )
        c2 = Candle(
            timestamp=datetime(2026, 10, 13, 14, 9, tzinfo=timezone.utc),
            open=1.42336,
            high=1.42338,
            low=1.42332,
            close=1.42335,  # bearish
        )
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


if __name__ == "__main__":
    unittest.main()
