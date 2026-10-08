"""bridge/watchdog.py
Process supervisor and health watchdog for MT4 bridge operations.

Monitors:
- MT4 DWX bar data file heartbeat / freshness.
- Bridge loop activity and execution health.
- Automatic trip of emergency halt if MT4 communication is lost.
- Telemetry reporting for operator visibility.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from bridge.dwx_client import DWXClient
from risk.guardrails import RiskGuardrails

logger = logging.getLogger("bridge_watchdog")


class HealthState(str, Enum):
    """Operational health states for the trading bridge."""
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE_HEARTBEAT = "STALE_HEARTBEAT"
    HALTED = "HALTED"


@dataclass
class WatchdogStatus:
    """Snapshot of bridge health and telemetry."""
    state: HealthState
    uptime_sec: float
    last_heartbeat_utc: Optional[datetime]
    heartbeat_age_sec: float
    bars_processed: int
    orders_dispatched: int
    emergency_halt_active: bool
    status_message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "uptime_sec": round(self.uptime_sec, 1),
            "last_heartbeat_utc": self.last_heartbeat_utc.isoformat() if self.last_heartbeat_utc else None,
            "heartbeat_age_sec": round(self.heartbeat_age_sec, 1),
            "bars_processed": self.bars_processed,
            "orders_dispatched": self.orders_dispatched,
            "emergency_halt_active": self.emergency_halt_active,
            "status_message": self.status_message,
            "timestamp": self.timestamp.isoformat(),
        }


class BridgeWatchdog:
    """Supervises MT4 file activity and ensures trading halts if connectivity is severed."""

    def __init__(
        self,
        dwx_client: DWXClient,
        risk_guardrails: Optional[RiskGuardrails] = None,
        max_heartbeat_age_sec: float = 600.0,  # 10 minutes (2x M5 bars)
        alert_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.dwx_client = dwx_client
        self.risk_guardrails = risk_guardrails
        self.max_heartbeat_age_sec = max_heartbeat_age_sec
        self.alert_callback = alert_callback

        self._start_time = time.monotonic()
        self._last_heartbeat: Optional[datetime] = None
        self._bars_processed: int = 0
        self._orders_dispatched: int = 0
        self._alerted_stale: bool = False
        self._lock = threading.Lock()

    def record_bar_received(self, dt: Optional[datetime] = None) -> None:
        """Records receipt of a closed bar from MT4."""
        with self._lock:
            self._bars_processed += 1
            self._last_heartbeat = dt or datetime.now(timezone.utc)
            self._alerted_stale = False

    def record_order_dispatched(self) -> None:
        """Records successful dispatch of an order to MT4."""
        with self._lock:
            self._orders_dispatched += 1

    def inspect_file_freshness(self, symbol: str = "USDCAD", timeframe: str = "M5") -> Optional[datetime]:
        """Directly checks the filesystem modification timestamp of the DWX bars file."""
        bars_path = self.dwx_client.get_bars_file(symbol, timeframe)
        if bars_path.exists():
            try:
                mtime = bars_path.stat().st_mtime
                file_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                with self._lock:
                    if self._last_heartbeat is None or file_dt > self._last_heartbeat:
                        self._last_heartbeat = file_dt
                return file_dt
            except OSError as err:
                logger.warning(f"Could not stat bar file {bars_path}: {err}")
        return None

    def check_health(self, current_time: Optional[datetime] = None) -> WatchdogStatus:
        """Evaluates current health state and returns a comprehensive status snapshot."""
        now_utc = current_time or datetime.now(timezone.utc)
        uptime = time.monotonic() - self._start_time

        with self._lock:
            last_hb = self._last_heartbeat
            bars_count = self._bars_processed
            orders_count = self._orders_dispatched

        is_halted = False
        if self.risk_guardrails:
            is_halted = self.risk_guardrails.limits.emergency_halt or self.risk_guardrails.tracker.is_halted

        if last_hb is None:
            # Starting up or awaiting first bar
            state = HealthState.STARTING
            hb_age = 0.0
            msg = f"Awaiting initial MT4 bar feed. Uptime: {uptime:.0f}s."
        else:
            hb_age = max(0.0, (now_utc - last_hb).total_seconds())
            if hb_age > self.max_heartbeat_age_sec:
                state = HealthState.STALE_HEARTBEAT
                msg = f"CRITICAL: MT4 heartbeat stale! No updates for {hb_age:.0f}s (limit: {self.max_heartbeat_age_sec:.0f}s)."
                self._handle_stale_heartbeat(msg)
            elif is_halted:
                state = HealthState.HALTED
                msg = "Circuit breaker or emergency halt active. All execution paused."
            elif hb_age > (self.max_heartbeat_age_sec / 2):
                state = HealthState.DEGRADED
                msg = f"WARNING: Delayed bar feed ({hb_age:.0f}s since last bar)."
            else:
                state = HealthState.HEALTHY
                msg = f"System operational. Last bar {hb_age:.0f}s ago."

        return WatchdogStatus(
            state=state,
            uptime_sec=uptime,
            last_heartbeat_utc=last_hb,
            heartbeat_age_sec=hb_age,
            bars_processed=bars_count,
            orders_dispatched=orders_count,
            emergency_halt_active=is_halted,
            status_message=msg,
            timestamp=now_utc,
        )

    def _handle_stale_heartbeat(self, reason: str) -> None:
        """Internal handler when MT4 heartbeat times out."""
        if not self._alerted_stale:
            self._alerted_stale = True
            logger.error(reason)
            if self.alert_callback:
                self.alert_callback(f"WATCHDOG ALERT: {reason}")
            if self.risk_guardrails:
                self.risk_guardrails.trigger_emergency_halt(f"Watchdog trigger: {reason}")
