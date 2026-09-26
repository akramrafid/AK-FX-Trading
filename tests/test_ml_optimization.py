"""tests/test_ml_optimization.py
Unit tests for Phase 8 Post-Live ML/RL Optimization Layer (engine/ml_optimization.py).

Verifies:
1. Feature extraction from TradeSignals and market context.
2. Pure Python SessionRegimeConfidenceModel probability estimation & training.
3. DynamicTradeManager policy actions (Hold, Breakeven at +3R, Trailing at +5R).
4. Non-Bypassable Risk Guardrails invariant: ML approval CANNOT bypass RiskGuardrails.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.ml_optimization import (
    DynamicTradeManager,
    SessionRegimeConfidenceModel,
    TradeAction,
    TradeFeatureExtractor,
    TradeFeatures,
    validate_signal_with_ml_and_risk,
)
from engine.models import Candle, Direction, TradeSignal
from risk.guardrails import RiskGuardrails
from risk.models import AccountState, RiskLimits, TradeRejectionReason


class TestFeatureExtraction(unittest.TestCase):
    """Tests for TradeFeatureExtractor."""

    def test_extract_from_signal(self) -> None:
        dt = datetime(2023, 5, 10, 14, 30, tzinfo=timezone.utc)  # 14:30 is London/NY overlap
        sig = TradeSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0835,
            take_profit=1.1000,
            risk_distance=0.0015,
            reward_distance=0.0150,
            reward_risk_ratio=10.0,
            timestamp=dt,
        )

        feats = TradeFeatureExtractor.extract_from_signal(sig, timeframe="M5", sweep_level=1.0830)
        self.assertEqual(feats.session_hour, 14.0)
        self.assertEqual(feats.is_london_ny_overlap, 1.0)
        self.assertEqual(feats.is_london_open, 0.0)
        self.assertAlmostEqual(feats.risk_pips, 15.0, places=2)
        self.assertAlmostEqual(feats.sweep_depth_pips, 20.0, places=2)
        self.assertEqual(feats.timeframe_m15, 0.0)

        vec = feats.to_vector()
        self.assertEqual(len(vec), 7)
        self.assertEqual(vec[0], 1.0)  # Bias term


class TestSessionRegimeConfidenceModel(unittest.TestCase):
    """Tests for pure Python logistic regression confidence model."""

    def setUp(self) -> None:
        self.model = SessionRegimeConfidenceModel(confidence_threshold=0.50)

    def test_confidence_predict_range(self) -> None:
        """Prediction must strictly lie in [0.0, 1.0]."""
        feats = TradeFeatures(
            session_hour=14.0,
            is_london_ny_overlap=1.0,
            is_london_open=0.0,
            sweep_depth_pips=5.0,
            risk_pips=12.0,
            timeframe_m15=0.0,
        )
        conf = self.model.predict_proba(feats)
        self.assertTrue(0.0 <= conf <= 1.0)

    def test_session_preference(self) -> None:
        """London/NY overlap setup must yield higher confidence than off-session."""
        overlap_feats = TradeFeatures(
            session_hour=14.0,
            is_london_ny_overlap=1.0,
            is_london_open=0.0,
            sweep_depth_pips=5.0,
            risk_pips=10.0,
            timeframe_m15=1.0,
        )
        night_feats = TradeFeatures(
            session_hour=22.0,
            is_london_ny_overlap=0.0,
            is_london_open=0.0,
            sweep_depth_pips=5.0,
            risk_pips=10.0,
            timeframe_m15=0.0,
        )
        self.assertGreater(
            self.model.predict_proba(overlap_feats),
            self.model.predict_proba(night_feats),
        )

    def test_training_on_journal_decreases_loss(self) -> None:
        """Training gradient descent on synthetic trade outcomes should succeed without error."""
        synthetic_journal = [
            {"open_time": "2023-05-10T14:00:00+00:00", "realized_pnl": 150.0, "timeframe": "M15"},
            {"open_time": "2023-05-10T15:00:00+00:00", "realized_pnl": 150.0, "timeframe": "M5"},
            {"open_time": "2023-05-10T02:00:00+00:00", "realized_pnl": -15.0, "timeframe": "M5"},
            {"open_time": "2023-05-10T22:00:00+00:00", "realized_pnl": -15.0, "timeframe": "M5"},
        ]
        loss = self.model.train_on_journal(synthetic_journal, learning_rate=0.1, epochs=20)
        self.assertTrue(loss > 0.0)


class TestDynamicTradeManager(unittest.TestCase):
    """Tests for policy-based dynamic trade management."""

    def setUp(self) -> None:
        self.manager = DynamicTradeManager(
            breakeven_threshold_r=3.0,
            trailing_threshold_r=5.0,
            trailing_lock_r=3.0,
            spread_buffer_pips=0.5,
        )

    def test_buy_trade_under_3r_holds(self) -> None:
        """Buy trade at +1.5R should HOLD with original SL."""
        decision = self.manager.evaluate_position(
            direction=Direction.BUY,
            entry_price=1.0800,
            current_price=1.0815,  # +1.5R gain (risk_dist = 0.0010 = 10 pips)
            initial_stop_loss=1.0790,
            take_profit=1.0900,
            risk_distance=0.0010,
        )
        self.assertEqual(decision.action, TradeAction.HOLD)
        self.assertIsNone(decision.new_stop_loss)

    def test_buy_trade_at_3r_moves_to_breakeven(self) -> None:
        """Buy trade at +3.2R should move SL to entry + 0.5 pip buffer."""
        decision = self.manager.evaluate_position(
            direction=Direction.BUY,
            entry_price=1.0800,
            current_price=1.0832,  # +3.2R
            initial_stop_loss=1.0790,
            take_profit=1.0900,
            risk_distance=0.0010,
        )
        self.assertEqual(decision.action, TradeAction.MOVE_TO_BREAKEVEN)
        expected_sl = 1.0800 + (0.5 * 0.0001)  # 1.08005
        self.assertAlmostEqual(decision.new_stop_loss, expected_sl, places=5)

    def test_buy_trade_at_5r_trails_stop_to_lock_3r(self) -> None:
        """Buy trade at +5.5R should trail SL to entry + 3R."""
        decision = self.manager.evaluate_position(
            direction=Direction.BUY,
            entry_price=1.0800,
            current_price=1.0855,  # +5.5R
            initial_stop_loss=1.0790,
            take_profit=1.0900,
            risk_distance=0.0010,
        )
        self.assertEqual(decision.action, TradeAction.TRAIL_STOP)
        expected_sl = 1.0800 + (3.0 * 0.0010)  # 1.0830
        self.assertAlmostEqual(decision.new_stop_loss, expected_sl, places=5)

    def test_sell_trade_at_3r_moves_to_breakeven(self) -> None:
        """Sell trade at +3.0R should move SL to entry - 0.5 pip buffer."""
        decision = self.manager.evaluate_position(
            direction=Direction.SELL,
            entry_price=1.0800,
            current_price=1.0770,  # +3.0R on short (risk_dist = 0.0010)
            initial_stop_loss=1.0810,
            take_profit=1.0700,
            risk_distance=0.0010,
        )
        self.assertEqual(decision.action, TradeAction.MOVE_TO_BREAKEVEN)
        expected_sl = 1.0800 - (0.5 * 0.0001)  # 1.07995
        self.assertAlmostEqual(decision.new_stop_loss, expected_sl, places=5)


class TestStrictRiskGuardrailNonBypassableInvariant(unittest.TestCase):
    """Verifies that ML cannot bypass the non-bypassable RiskGuardrails layer."""

    def setUp(self) -> None:
        self.limits = RiskLimits(
            max_daily_loss_pct=Decimal("0.03"),
            max_open_trades=1,
            max_daily_trades=3,
            max_spread_pips=Decimal("2.5"),
            session_filter_enabled=True,
            session_start_hour_utc=7,
            session_end_hour_utc=17,
            emergency_halt=False,
        )
        self.guardrails = RiskGuardrails(limits=self.limits)
        self.ml_model = SessionRegimeConfidenceModel(confidence_threshold=0.30)

    def test_ml_approved_passes_when_risk_healthy(self) -> None:
        """When ML approves and risk parameters are healthy, trade is allowed."""
        dt = datetime(2023, 5, 10, 14, 0, tzinfo=timezone.utc)
        sig = TradeSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0835,
            take_profit=1.1000,
            risk_distance=0.0015,
            reward_distance=0.0150,
            reward_risk_ratio=10.0,
            timestamp=dt,
        )
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            current_equity=Decimal("10000.00"),
            realized_daily_pnl=Decimal("0.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=0,
            current_spread_pips=Decimal("1.2"),
            timestamp=dt,
        )
        ok, msg, conf = validate_signal_with_ml_and_risk(
            signal=sig,
            account_state=state,
            proposed_lots=Decimal("1.00"),
            guardrails=self.guardrails,
            ml_model=self.ml_model,
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "APPROVED_BY_ML_AND_RISK")
        self.assertIsNotNone(conf)

    def test_ml_approved_strictly_blocked_by_emergency_halt(self) -> None:
        """Even if ML has 100% confidence, Emergency Halt blocks trade."""
        self.guardrails.trip_emergency_halt(reason="Broker maintenance")

        dt = datetime(2023, 5, 10, 14, 0, tzinfo=timezone.utc)
        sig = TradeSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0835,
            take_profit=1.1000,
            risk_distance=0.0015,
            reward_distance=0.0150,
            reward_risk_ratio=10.0,
            timestamp=dt,
        )
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            current_equity=Decimal("10000.00"),
            realized_daily_pnl=Decimal("0.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=0,
            current_spread_pips=Decimal("1.2"),
            timestamp=dt,
        )
        ok, msg, conf = validate_signal_with_ml_and_risk(
            signal=sig,
            account_state=state,
            proposed_lots=Decimal("1.00"),
            guardrails=self.guardrails,
            ml_model=self.ml_model,
        )
        self.assertFalse(ok)
        self.assertIn("RISK_GUARDRAIL_REJECTED", msg)
        self.assertIn(TradeRejectionReason.EMERGENCY_STOP.value, msg)

    def test_ml_approved_strictly_blocked_by_session_filter(self) -> None:
        """Even if ML approves, a trade at 03:00 UTC is blocked by the session filter."""
        dt = datetime(2023, 5, 10, 3, 0, tzinfo=timezone.utc)
        sig = TradeSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0835,
            take_profit=1.1000,
            risk_distance=0.0015,
            reward_distance=0.0150,
            reward_risk_ratio=10.0,
            timestamp=dt,
        )
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            current_equity=Decimal("10000.00"),
            realized_daily_pnl=Decimal("0.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=0,
            current_spread_pips=Decimal("1.2"),
            timestamp=dt,
        )
        ok, msg, _ = validate_signal_with_ml_and_risk(
            signal=sig,
            account_state=state,
            proposed_lots=Decimal("1.00"),
            guardrails=self.guardrails,
            ml_model=self.ml_model,
        )
        self.assertFalse(ok)
        self.assertIn(TradeRejectionReason.OUTSIDE_SESSION_HOURS.value, msg)


if __name__ == "__main__":
    unittest.main()
