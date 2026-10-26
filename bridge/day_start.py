"""bridge/day_start.py
The daily loss circuit breaker's baseline (plan.md §3.4): the account balance at the first reading of
each UTC day.

It is kept per MT4 account in daily_metrics, one row per day and account, so a restart later in the day
still counts the day's earlier losses and a switch to another account starts that account's day from its
own balance. Deposits and withdrawals cannot be told apart from P&L.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional, Tuple

from database.sqlite_manager import TradingDatabase

logger = logging.getLogger("day_start")

STORED_DAYS_SCANNED = 31


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DayStartBalances:
    """The starting balance of the current UTC day for each MT4 account."""

    def __init__(self, db: Optional[TradingDatabase] = None, clock: Callable[[], datetime] = _utc_now) -> None:
        self.db = db
        self.clock = clock
        self._current: Optional[Tuple[str, Decimal]] = None  # (daily_metrics trade_date key, starting balance)

    def balance_at_start(self, balance: Decimal, account: str = "") -> Decimal:
        """This UTC day's starting balance for the account; the day's first reading sets it."""
        day = self.clock().astimezone(timezone.utc).date().isoformat()
        key = f"{day} {account}" if account else day
        if self._current is not None and self._current[0] == key:
            return self._current[1]
        start = self._stored(key)
        if start is None:
            start = balance
            self._store(key, balance)
        self._current = (key, start)
        return start

    def _stored(self, key: str) -> Optional[Decimal]:
        if self.db is None:
            return None
        try:
            rows = self.db.get_daily_metrics(limit=STORED_DAYS_SCANNED)
        except Exception as e:
            logger.error(f"Failed to read the day's starting balance: {e}")
            return None
        for row in rows:
            if row.get("trade_date") == key and row.get("starting_balance"):
                return Decimal(str(row["starting_balance"]))
        return None

    def _store(self, key: str, balance: Decimal) -> None:
        if self.db is None:
            return
        try:
            self.db.save_daily_metrics(
                trade_date=key,
                starting_balance=float(balance),
                closing_equity=float(balance),
                realized_pnl=0.0,
                trade_count=0,
            )
        except Exception as e:
            logger.error(f"Failed to store the day's starting balance: {e}")
