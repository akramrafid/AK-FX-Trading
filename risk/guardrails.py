"""risk/guardrails.py
Non-bypassable institutional risk guardrails and circuit breaker engine.

Guarantees:
- Every trade order MUST pass validate_trade() before reaching execution bridge.
- Daily Loss Limit: If cumulative realized + unrealized losses exceed 3.0% of starting daily balance,
  trading is halted for the rest of that calendar day.
- Max Open Trades: Rejects new setups if an open trade is currently active (default max 1).
- Max Daily Trades: Ceases trading once daily trade count reaches limit (default max 3).
- Spread Filter: Rejects trades if current broker spread exceeds threshold (default 2.5 pips).
- Session Hours Filter: Restricts trading to London and New York sessions (07:00 - 17:00 UTC).
- Emergency Kill Switch: Global software-level halt capability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, List, Optional

from risk.models import (
    AccountState,
    DailyPnLTracker,
    RiskLimits,
    TradeRejectionReason,
    ValidationResult,
)

logger = logging.getLogger("risk_guardrails")


class RiskGuardrails:
    """Institutional risk management engine enforcing hard, non-bypassable constraints."""

    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        tracker: Optional[DailyPnLTracker] = None,
        alert_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.limits = limits or RiskLimits()
        self.tracker = tracker or DailyPnLTracker(initial_balance=Decimal("10000.00"))
        self.alert_callback = alert_callback
        self.audit_log: List[ValidationResult] = []

    def validate_trade(
        self,
        account_state: AccountState,
        proposed_lots: Decimal = Decimal("0.01"),
        trade_time: Optional[datetime] = None,
    ) -> ValidationResult:
        """Mandatory gating check. Evaluates proposed trade against all active safety bounds.
        
        Returns ValidationResult indicating whether the trade is permitted or rejected.
        """
        now_utc = trade_time or account_state.timestamp or datetime.now(timezone.utc)
        self.tracker.check_and_rollover(now_utc, account_state.current_balance)

        # 0. Global Emergency Kill Switch
        if self.limits.emergency_halt:
            res = ValidationResult(
                is_allowed=False,
                reason=TradeRejectionReason.EMERGENCY_STOP,
                message="Emergency kill-switch is active. All new trades halted.",
                timestamp=now_utc,
            )
            self._record_decision(res)
            return res

        # 1. Active Circuit Breaker Halt for the Day
        if self.tracker.is_halted:
            res = ValidationResult(
                is_allowed=False,
                reason=TradeRejectionReason.CIRCUIT_BREAKER_HALTED,
                message=f"Daily circuit breaker active: {self.tracker.halt_reason}. Trading halted until next UTC session.",
                timestamp=now_utc,
            )
            self._record_decision(res)
            return res

        # 2. Daily Loss Limit Check (Realized + Unrealized)
        if self.limits.max_daily_loss_pct is not None and account_state.is_daily_loss_exceeded(self.limits.max_daily_loss_pct):
            loss_pct_display = (account_state.daily_loss_pct * Decimal("100")).quantize(Decimal("0.1"))
            limit_pct_display = (self.limits.max_daily_loss_pct * Decimal("100")).quantize(Decimal("0.1"))
            msg = (
                f"Daily loss limit breached! Cumulative daily loss is {loss_pct_display}% "
                f"(loss: ${abs(account_state.total_daily_pnl):.2f}), exceeding {limit_pct_display}% limit. "
                f"Trading halted for remainder of day."
            )
            self.tracker.trip_circuit_breaker(msg)
            if self.alert_callback:
                self.alert_callback(f"CIRCUIT BREAKER: {msg}")

            res = ValidationResult(
                is_allowed=False,
                reason=TradeRejectionReason.DAILY_LOSS_LIMIT_EXCEEDED,
                message=msg,
                timestamp=now_utc,
            )
            self._record_decision(res)
            return res

        # 3. Maximum Open Trades Constraint (enforced only when limit > 0; 0 or None = unlimited)
        if self.limits.max_open_trades is not None and self.limits.max_open_trades > 0:
            if account_state.open_trade_count >= self.limits.max_open_trades:
                res = ValidationResult(
                    is_allowed=False,
                    reason=TradeRejectionReason.MAX_OPEN_TRADES_REACHED,
                    message=f"Max open trades reached: currently {account_state.open_trade_count} active (limit: {self.limits.max_open_trades}).",
                    timestamp=now_utc,
                )
                self._record_decision(res)
                return res

        # 4. Maximum Daily Trades Constraint (enforced only when limit is set; None or <= 0 = unlimited)
        if self.limits.max_daily_trades is not None and self.limits.max_daily_trades > 0:
            if account_state.daily_trades_count >= self.limits.max_daily_trades:
                res = ValidationResult(
                    is_allowed=False,
                    reason=TradeRejectionReason.MAX_DAILY_TRADES_REACHED,
                    message=f"Max daily trades limit reached: {account_state.daily_trades_count}/{self.limits.max_daily_trades} trades executed today.",
                    timestamp=now_utc,
                )
                self._record_decision(res)
                return res

        # 5. Broker Spread Filter
        if account_state.current_spread_pips > self.limits.max_spread_pips:
            msg = f"Trade skipped: spread {account_state.current_spread_pips:.1f} pips exceeds limit {self.limits.max_spread_pips:.1f} pips."
            logger.warning(msg)
            res = ValidationResult(
                is_allowed=False,
                reason=TradeRejectionReason.SPREAD_EXCEEDS_MAX,
                message=msg,
                timestamp=now_utc,
            )
            self._record_decision(res)
            return res

        # 6. Session Hours Filter (London, Overlap & NY Sessions: 07:00 - 21:00 UTC)
        if self.limits.session_filter_enabled:
            hour = now_utc.hour
            if hour < self.limits.session_start_hour_utc or hour >= self.limits.session_end_hour_utc:
                res = ValidationResult(
                    is_allowed=False,
                    reason=TradeRejectionReason.OUTSIDE_SESSION_HOURS,
                    message=f"Trade time {now_utc.strftime('%H:%M')} UTC is outside allowed session window ({self.limits.session_start_hour_utc:02d}:00 - {self.limits.session_end_hour_utc:02d}:00 UTC).",
                    timestamp=now_utc,
                )
                self._record_decision(res)
                return res

        # 7. Proposed Lot Size Sanity Check
        if proposed_lots <= Decimal("0.00"):
            res = ValidationResult(
                is_allowed=False,
                reason=TradeRejectionReason.INVALID_LOT_SIZE,
                message=f"Non-positive proposed lot size: {proposed_lots}.",
                timestamp=now_utc,
            )
            self._record_decision(res)
            return res

        # All non-bypassable guardrails passed
        res = ValidationResult(
            is_allowed=True,
            reason=None,
            message="All non-bypassable risk guardrails passed.",
            timestamp=now_utc,
        )
        self._record_decision(res)
        return res

    def _record_decision(self, result: ValidationResult) -> None:
        """Maintains audit history of risk decisions."""
        self.audit_log.append(result)
        if not result.is_allowed:
            logger.warning(f"Risk Guardrail REJECTION: [{result.reason}] {result.message}")
        else:
            logger.info("Risk Guardrails: Trade APPROVED.")

    def trip_emergency_halt(self, reason: str = "Manual emergency stop") -> None:
        """Manually triggers emergency halt."""
        self.limits = RiskLimits(
            max_daily_loss_pct=self.limits.max_daily_loss_pct,
            max_open_trades=self.limits.max_open_trades,
            max_daily_trades=self.limits.max_daily_trades,
            max_spread_pips=self.limits.max_spread_pips,
            close_all_on_daily_limit_breach=self.limits.close_all_on_daily_limit_breach,
            session_start_hour_utc=self.limits.session_start_hour_utc,
            session_end_hour_utc=self.limits.session_end_hour_utc,
            session_filter_enabled=self.limits.session_filter_enabled,
            emergency_halt=True,
        )
        logger.critical(f"EMERGENCY HALT ACTIVATED: {reason}")
        if self.alert_callback:
            self.alert_callback(f"EMERGENCY HALT: {reason}")

    trigger_emergency_halt = trip_emergency_halt

    def reset_emergency_halt(self) -> None:
        """Clears emergency halt status."""
        self.limits = RiskLimits(
            max_daily_loss_pct=self.limits.max_daily_loss_pct,
            max_open_trades=self.limits.max_open_trades,
            max_daily_trades=self.limits.max_daily_trades,
            max_spread_pips=self.limits.max_spread_pips,
            close_all_on_daily_limit_breach=self.limits.close_all_on_daily_limit_breach,
            session_start_hour_utc=self.limits.session_start_hour_utc,
            session_end_hour_utc=self.limits.session_end_hour_utc,
            session_filter_enabled=self.limits.session_filter_enabled,
            emergency_halt=False,
        )
        logger.info("Emergency halt cleared. Normal guardrails resumed.")
