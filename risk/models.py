"""risk/models.py
Risk state, limits, and domain invariant models.

Defines:
- RiskLimits: Configurable hard boundaries for daily loss, open trades, daily trades, spread, and sessions.
- AccountState: Real-time snapshot of account balance, equity, open trades, daily PnL, and broker spread.
- TradeRejectionReason: Enumeration of all non-bypassable guardrail rejection triggers.
- ValidationResult: Immutable decision returned by RiskGuardrails.validate_trade().
- DailyPnLTracker: Session-aware calendar tracker tracking daily loss limits and resetting at 00:00 UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class TradeRejectionReason(str, Enum):
    """Specific rejection reasons when a trade fails non-bypassable risk guardrails."""
    DAILY_LOSS_LIMIT_EXCEEDED = "DAILY_LOSS_LIMIT_EXCEEDED"
    MAX_OPEN_TRADES_REACHED = "MAX_OPEN_TRADES_REACHED"
    MAX_DAILY_TRADES_REACHED = "MAX_DAILY_TRADES_REACHED"
    SPREAD_EXCEEDS_MAX = "SPREAD_EXCEEDS_MAX"
    OUTSIDE_SESSION_HOURS = "OUTSIDE_SESSION_HOURS"
    CIRCUIT_BREAKER_HALTED = "CIRCUIT_BREAKER_HALTED"
    INVALID_LOT_SIZE = "INVALID_LOT_SIZE"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class RiskLimits:
    """Configurable system risk limits and safety bounds."""
    max_daily_loss_pct: Decimal = Decimal("0.03")  # 3.0% maximum daily loss
    max_open_trades: int = 1                       # Maximum concurrent open trades
    max_daily_trades: Optional[int] = None         # None = unlimited daily trades (no trade limits)
    max_spread_pips: Decimal = Decimal("2.5")      # Maximum allowed spread ceiling in pips
    close_all_on_daily_limit_breach: bool = False  # False = let SL protect, True = close immediately
    session_start_hour_utc: int = 7                # 07:00 UTC (London session open)
    session_end_hour_utc: int = 21                 # 21:00 UTC (NY evening close)
    session_filter_enabled: bool = True            # Enforce London, Overlap & NY session window (07:00 - 21:00 UTC)
    emergency_halt: bool = False                   # Global kill switch


@dataclass(frozen=True)
class AccountState:
    """Real-time account state snapshot required for mandatory risk validation."""
    starting_daily_balance: Decimal
    current_balance: Decimal
    current_equity: Decimal
    realized_daily_pnl: Decimal
    unrealized_daily_pnl: Decimal
    open_trade_count: int
    daily_trades_count: int
    current_spread_pips: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_daily_pnl(self) -> Decimal:
        """Cumulative realized + unrealized PnL for the current calendar day."""
        return self.realized_daily_pnl + self.unrealized_daily_pnl

    @property
    def daily_loss_pct(self) -> Decimal:
        """Current daily loss percentage relative to starting balance.
        Returns positive percentage representing loss (e.g. 0.035 for 3.5% loss)."""
        if self.starting_daily_balance <= Decimal("0"):
            return Decimal("0.0")
        if self.total_daily_pnl >= Decimal("0"):
            return Decimal("0.0")
        return abs(self.total_daily_pnl) / self.starting_daily_balance

    def is_daily_loss_exceeded(self, max_daily_loss_pct: Decimal) -> bool:
        """True if total daily losses exceed the allowed percentage threshold."""
        return self.daily_loss_pct >= max_daily_loss_pct


@dataclass(frozen=True)
class ValidationResult:
    """Immutable outcome of trade validation by RiskGuardrails."""
    is_allowed: bool
    reason: Optional[TradeRejectionReason] = None
    message: str = "Trade allowed"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DailyPnLTracker:
    """Session tracker managing daily PnL, trade counts, and UTC calendar day rollovers."""

    def __init__(self, initial_balance: Decimal, reference_date: Optional[date] = None) -> None:
        self.current_date: date = reference_date or datetime.now(timezone.utc).date()
        self.starting_daily_balance: Decimal = initial_balance
        self.realized_daily_pnl: Decimal = Decimal("0.00")
        self.daily_trades_count: int = 0
        self.is_halted: bool = False
        self.halt_reason: Optional[str] = None

    def check_and_rollover(self, current_dt: datetime, current_balance: Decimal) -> None:
        """Checks for new UTC calendar day (00:00 UTC) and resets daily metrics."""
        today = current_dt.date()
        if today > self.current_date:
            self.current_date = today
            self.starting_daily_balance = current_balance
            self.realized_daily_pnl = Decimal("0.00")
            self.daily_trades_count = 0
            self.is_halted = False
            self.halt_reason = None

    def record_trade_opened(self) -> None:
        """Increments daily trade count."""
        self.daily_trades_count += 1

    def record_trade_closed(self, pnl: Decimal) -> None:
        """Updates realized daily PnL upon position close."""
        self.realized_daily_pnl += pnl

    def trip_circuit_breaker(self, reason: str) -> None:
        """Halts trading for the remainder of the calendar day."""
        self.is_halted = True
        self.halt_reason = reason
