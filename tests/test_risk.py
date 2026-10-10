"""tests/test_risk.py
Comprehensive test suite for Phase 4 — Non-Bypassable Risk Guardrails & Circuit Breakers.

Tests:
- AccountState invariant models (daily_loss_pct, total_daily_pnl)
- DailyPnLTracker session rollover at 00:00 UTC
- RiskGuardrails.validate_trade() for every rejection reason
- Emergency halt activation and reset
- BridgeExecutor integration: risk rejection prevents DWX dispatch
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from risk.models import (
    AccountState,
    DailyPnLTracker,
    RiskLimits,
    TradeRejectionReason,
    ValidationResult,
)
from risk.guardrails import RiskGuardrails


# ═══════════════════════════════════════════════════════════════════
# AccountState Model Tests
# ═══════════════════════════════════════════════════════════════════


class TestAccountState(unittest.TestCase):
    """Validate AccountState computed properties and daily loss math."""

    def test_total_daily_pnl_sums_realized_and_unrealized(self):
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("9800.00"),
            current_equity=Decimal("9750.00"),
            realized_daily_pnl=Decimal("-150.00"),
            unrealized_daily_pnl=Decimal("-50.00"),
            open_trade_count=1,
            daily_trades_count=2,
            current_spread_pips=Decimal("1.2"),
        )
        self.assertEqual(state.total_daily_pnl, Decimal("-200.00"))

    def test_daily_loss_pct_positive_pnl_returns_zero(self):
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("10200.00"),
            current_equity=Decimal("10200.00"),
            realized_daily_pnl=Decimal("200.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=1,
            current_spread_pips=Decimal("1.0"),
        )
        self.assertEqual(state.daily_loss_pct, Decimal("0.0"))

    def test_daily_loss_pct_calculation(self):
        """3.5% loss = $350 on $10,000 starting balance."""
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("9650.00"),
            current_equity=Decimal("9650.00"),
            realized_daily_pnl=Decimal("-250.00"),
            unrealized_daily_pnl=Decimal("-100.00"),
            open_trade_count=1,
            daily_trades_count=2,
            current_spread_pips=Decimal("1.0"),
        )
        self.assertEqual(state.daily_loss_pct, Decimal("0.035"))

    def test_is_daily_loss_exceeded(self):
        state = AccountState(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("9650.00"),
            current_equity=Decimal("9650.00"),
            realized_daily_pnl=Decimal("-350.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=2,
            current_spread_pips=Decimal("1.0"),
        )
        # 3.5% loss exceeds 3.0% limit
        self.assertTrue(state.is_daily_loss_exceeded(Decimal("0.03")))
        # But not 4.0% limit
        self.assertFalse(state.is_daily_loss_exceeded(Decimal("0.04")))

    def test_zero_starting_balance_returns_zero_pct(self):
        state = AccountState(
            starting_daily_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
            current_equity=Decimal("0.00"),
            realized_daily_pnl=Decimal("-100.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=0,
            current_spread_pips=Decimal("1.0"),
        )
        self.assertEqual(state.daily_loss_pct, Decimal("0.0"))


# ═══════════════════════════════════════════════════════════════════
# DailyPnLTracker Tests
# ═══════════════════════════════════════════════════════════════════


class TestDailyPnLTracker(unittest.TestCase):
    """Validate session rollover logic at 00:00 UTC."""

    def test_same_day_no_rollover(self):
        tracker = DailyPnLTracker(
            initial_balance=Decimal("10000.00"),
            reference_date=date(2024, 9, 24),
        )
        tracker.realized_daily_pnl = Decimal("-200.00")
        tracker.daily_trades_count = 2

        # Same day -> no reset
        same_day = datetime(2024, 9, 24, 15, 30, tzinfo=timezone.utc)
        tracker.check_and_rollover(same_day, Decimal("9800.00"))

        self.assertEqual(tracker.realized_daily_pnl, Decimal("-200.00"))
        self.assertEqual(tracker.daily_trades_count, 2)

    def test_new_day_triggers_rollover(self):
        tracker = DailyPnLTracker(
            initial_balance=Decimal("10000.00"),
            reference_date=date(2024, 9, 24),
        )
        tracker.realized_daily_pnl = Decimal("-200.00")
        tracker.daily_trades_count = 2
        tracker.is_halted = True
        tracker.halt_reason = "Test halt"

        # Next day -> full reset
        next_day = datetime(2024, 9, 25, 0, 1, tzinfo=timezone.utc)
        tracker.check_and_rollover(next_day, Decimal("9800.00"))

        self.assertEqual(tracker.realized_daily_pnl, Decimal("0.00"))
        self.assertEqual(tracker.daily_trades_count, 0)
        self.assertFalse(tracker.is_halted)
        self.assertIsNone(tracker.halt_reason)
        self.assertEqual(tracker.starting_daily_balance, Decimal("9800.00"))
        self.assertEqual(tracker.current_date, date(2024, 9, 25))

    def test_record_trade_opened(self):
        tracker = DailyPnLTracker(initial_balance=Decimal("10000.00"))
        self.assertEqual(tracker.daily_trades_count, 0)
        tracker.record_trade_opened()
        self.assertEqual(tracker.daily_trades_count, 1)

    def test_record_trade_closed(self):
        tracker = DailyPnLTracker(initial_balance=Decimal("10000.00"))
        tracker.record_trade_closed(Decimal("-75.50"))
        tracker.record_trade_closed(Decimal("120.00"))
        self.assertEqual(tracker.realized_daily_pnl, Decimal("44.50"))

    def test_trip_circuit_breaker(self):
        tracker = DailyPnLTracker(initial_balance=Decimal("10000.00"))
        tracker.trip_circuit_breaker("Daily loss exceeded 3%")
        self.assertTrue(tracker.is_halted)
        self.assertEqual(tracker.halt_reason, "Daily loss exceeded 3%")


# ═══════════════════════════════════════════════════════════════════
# RiskGuardrails — Core Validation Tests
# ═══════════════════════════════════════════════════════════════════


class TestRiskGuardrails(unittest.TestCase):
    """Every guardrail rejection reason must be verified independently."""

    def _make_default_state(self, **overrides) -> AccountState:
        """Helper: constructs a healthy AccountState with overridable fields."""
        defaults = dict(
            starting_daily_balance=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            current_equity=Decimal("10000.00"),
            realized_daily_pnl=Decimal("0.00"),
            unrealized_daily_pnl=Decimal("0.00"),
            open_trade_count=0,
            daily_trades_count=0,
            current_spread_pips=Decimal("1.0"),
            timestamp=datetime(2024, 9, 24, 10, 30, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return AccountState(**defaults)

    def setUp(self):
        self.guardrails = RiskGuardrails(
            limits=RiskLimits(),
            tracker=DailyPnLTracker(
                initial_balance=Decimal("10000.00"),
                reference_date=date(2024, 9, 24),
            ),
        )
        self.trade_time = datetime(2024, 9, 24, 10, 30, tzinfo=timezone.utc)

    def test_all_guardrails_pass(self):
        state = self._make_default_state()
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertTrue(result.is_allowed)
        self.assertIsNone(result.reason)

    def test_emergency_halt_blocks_all_trades(self):
        self.guardrails.trip_emergency_halt("Manual stop")
        state = self._make_default_state()
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.EMERGENCY_STOP)

    def test_emergency_halt_reset_allows_trades(self):
        self.guardrails.trip_emergency_halt("Test halt")
        self.guardrails.reset_emergency_halt()
        state = self._make_default_state()
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertTrue(result.is_allowed)

    def test_circuit_breaker_halted_blocks_trades(self):
        self.guardrails.tracker.trip_circuit_breaker("Halted by prior loss")
        state = self._make_default_state()
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.CIRCUIT_BREAKER_HALTED)

    def test_daily_loss_limit_exceeded(self):
        """3.5% loss exceeds 3.0% default -> rejection + circuit breaker trips."""
        state = self._make_default_state(
            realized_daily_pnl=Decimal("-350.00"),
            current_balance=Decimal("9650.00"),
        )
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.DAILY_LOSS_LIMIT_EXCEEDED)
        # Circuit breaker should now be tripped
        self.assertTrue(self.guardrails.tracker.is_halted)

    def test_max_open_trades_reached(self):
        state = self._make_default_state(open_trade_count=1)  # default max is 1
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.MAX_OPEN_TRADES_REACHED)

    def test_max_daily_trades_reached(self):
        # When explicit limit is set (e.g. 3), guardrail blocks trade once reached
        guardrails_with_limit = RiskGuardrails(limits=RiskLimits(max_daily_trades=3))
        state = self._make_default_state(daily_trades_count=3)
        result = guardrails_with_limit.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.MAX_DAILY_TRADES_REACHED)

    def test_daily_no_trade_limits_allows_unlimited_trades(self):
        # Default system has no daily trade limit (max_daily_trades=None)
        state = self._make_default_state(daily_trades_count=10)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertTrue(result.is_allowed)

    def test_spread_exceeds_max(self):
        state = self._make_default_state(current_spread_pips=Decimal("3.0"))  # limit is 2.5
        result = self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.SPREAD_EXCEEDS_MAX)

    def test_outside_session_hours_early(self):
        """04:00 UTC is before London open (07:00)."""
        early = datetime(2024, 9, 24, 4, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=early)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), early)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.OUTSIDE_SESSION_HOURS)

    def test_outside_session_hours_late(self):
        """22:00 UTC is after session cutoff."""
        late = datetime(2024, 9, 24, 22, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=late)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), late)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.OUTSIDE_SESSION_HOURS)

    def test_outside_session_hours_at_12_am_local_cutoff(self):
        """18:00 UTC corresponds to 12:00 AM midnight local time (UTC+6) and must be blocked."""
        midnight_local = datetime(2024, 9, 24, 18, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=midnight_local)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), midnight_local)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.OUTSIDE_SESSION_HOURS)

    def test_session_allowed_up_to_12_am_local_close(self):
        """17:00 UTC (11:00 PM local time) is within session (before 18:00 UTC / 12:00 AM cutoff)."""
        active_time = datetime(2024, 9, 24, 17, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=active_time)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), active_time)
        self.assertTrue(result.is_allowed)

    def test_within_session_hours(self):
        """12:00 UTC is within London/NY overlap."""
        midday = datetime(2024, 9, 24, 12, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=midday)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), midday)
        self.assertTrue(result.is_allowed)

    def test_session_filter_disabled_allows_any_hour(self):
        """When session filter is off, 03:00 UTC should pass."""
        guardrails = RiskGuardrails(
            limits=RiskLimits(session_filter_enabled=False),
            tracker=DailyPnLTracker(
                initial_balance=Decimal("10000.00"),
                reference_date=date(2024, 9, 24),
            ),
        )
        early = datetime(2024, 9, 24, 3, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=early)
        result = guardrails.validate_trade(state, Decimal("0.05"), early)
        self.assertTrue(result.is_allowed)

    def test_invalid_lot_size_zero(self):
        state = self._make_default_state()
        result = self.guardrails.validate_trade(state, Decimal("0.00"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.INVALID_LOT_SIZE)

    def test_invalid_lot_size_negative(self):
        state = self._make_default_state()
        result = self.guardrails.validate_trade(state, Decimal("-0.01"), self.trade_time)
        self.assertFalse(result.is_allowed)
        self.assertEqual(result.reason, TradeRejectionReason.INVALID_LOT_SIZE)

    def test_audit_log_records_all_decisions(self):
        state = self._make_default_state()
        self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertEqual(len(self.guardrails.audit_log), 2)

    def test_alert_callback_fires_on_circuit_breaker(self):
        alerts = []
        guardrails = RiskGuardrails(
            limits=RiskLimits(),
            tracker=DailyPnLTracker(
                initial_balance=Decimal("10000.00"),
                reference_date=date(2024, 9, 24),
            ),
            alert_callback=alerts.append,
        )
        state = self._make_default_state(
            realized_daily_pnl=Decimal("-400.00"),
            current_balance=Decimal("9600.00"),
        )
        guardrails.validate_trade(state, Decimal("0.05"), self.trade_time)
        self.assertEqual(len(alerts), 1)
        self.assertIn("CIRCUIT BREAKER", alerts[0])

    def test_new_day_clears_circuit_breaker(self):
        """After midnight UTC, daily metrics reset and trading resumes."""
        self.guardrails.tracker.trip_circuit_breaker("Loss exceeded")

        # Advance to next day
        next_day = datetime(2024, 9, 25, 10, 0, tzinfo=timezone.utc)
        state = self._make_default_state(timestamp=next_day)
        result = self.guardrails.validate_trade(state, Decimal("0.05"), next_day)
        self.assertTrue(result.is_allowed)
        self.assertFalse(self.guardrails.tracker.is_halted)


# ═══════════════════════════════════════════════════════════════════
# BridgeExecutor + RiskGuardrails Integration
# ═══════════════════════════════════════════════════════════════════


class TestBridgeRiskIntegration(unittest.TestCase):
    """Verify BridgeExecutor rejects orders when RiskGuardrails block them."""

    def test_bridge_rejects_on_emergency_halt(self):
        """When emergency halt is active, _execute_signal must return REJECTED."""
        from unittest.mock import MagicMock
        from bridge.executor import BridgeExecutor
        from bridge.dwx_client import DWXClient
        from engine.models import Direction, TradeSignal

        mock_dwx = MagicMock(spec=DWXClient)

        guardrails = RiskGuardrails(
            limits=RiskLimits(session_filter_enabled=False),
            tracker=DailyPnLTracker(
                initial_balance=Decimal("10000.00"),
                reference_date=date(2024, 9, 24),
            ),
        )
        guardrails.trip_emergency_halt("Test halt")

        bridge = BridgeExecutor(
            symbol="EURUSD",
            dwx_client=mock_dwx,
            risk_guardrails=guardrails,
        )

        signal = TradeSignal(
            direction=Direction.BUY,
            entry_price=1.08500,
            stop_loss=1.08300,
            take_profit=1.10500,
            risk_distance=0.00200,
            reward_distance=0.02000,
            timestamp=datetime(2024, 9, 24, 10, 30, tzinfo=timezone.utc),
        )

        record = bridge._execute_signal(signal)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "REJECTED")
        self.assertIn("RISK:", record.rejection_reason)
        self.assertIn("EMERGENCY_STOP", record.rejection_reason)
        # DWX should never have been called
        mock_dwx.send_order.assert_not_called()

    def test_bridge_allows_when_guardrails_pass(self):
        """When all risk checks pass, the order should reach DWX dispatch."""
        from unittest.mock import MagicMock, patch
        from bridge.executor import BridgeExecutor
        from bridge.dwx_client import DWXClient, ExecutionReport, OrderType
        from engine.models import Direction, TradeSignal

        mock_dwx = MagicMock(spec=DWXClient)
        mock_dwx.poll_order_confirmation.return_value = ExecutionReport(
            ticket=12345,
            magic=100001,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            lots=Decimal("0.05"),
            open_price=Decimal("1.08500"),
            sl=Decimal("1.08300"),
            tp=Decimal("1.10500"),
            status="FILLED",
            timestamp=datetime(2024, 9, 24, 10, 31, tzinfo=timezone.utc),
        )

        guardrails = RiskGuardrails(
            limits=RiskLimits(session_filter_enabled=False),
            tracker=DailyPnLTracker(
                initial_balance=Decimal("10000.00"),
                reference_date=date(2024, 9, 24),
            ),
        )

        bridge = BridgeExecutor(
            symbol="EURUSD",
            dwx_client=mock_dwx,
            risk_guardrails=guardrails,
        )

        signal = TradeSignal(
            direction=Direction.BUY,
            entry_price=1.08500,
            stop_loss=1.08300,
            take_profit=1.10500,
            risk_distance=0.00200,
            reward_distance=0.02000,
            timestamp=datetime(2024, 9, 24, 10, 30, tzinfo=timezone.utc),
        )

        record = bridge._execute_signal(signal)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "FILLED")
        mock_dwx.send_order.assert_called_once()


if __name__ == "__main__":
    unittest.main()
