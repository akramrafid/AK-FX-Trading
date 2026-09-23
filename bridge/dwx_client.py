"""bridge/dwx_client.py
DWX Connect file-based client protocol for Python-to-MT4 execution.

Handles:
- Atomic file operations with Windows-compatible exponential backoff.
- Reading bar data files written by MT4 EA on closed bars.
- Writing execution commands (OPEN, MODIFY, CLOSE) to DWX command files.
- Reading trade execution reports and verifying ticket assignment.
- Timeout-based unconfirmed trade alerting and duplicate order prevention.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from engine.models import Candle

logger = logging.getLogger("dwx_client")


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class CommandAction(str, Enum):
    OPEN = "OPEN"
    MODIFY = "MODIFY"
    CLOSE = "CLOSE"
    RESET = "RESET"


@dataclass(frozen=True)
class TradeCommand:
    """Command sent from Python to MT4 EA via DWX_Commands.txt."""
    command_id: str
    action: CommandAction
    symbol: str
    order_type: Optional[OrderType] = None
    lots: Decimal = Decimal("0.01")
    price: Decimal = Decimal("0.0")
    sl: Decimal = Decimal("0.0")
    tp: Decimal = Decimal("0.0")
    magic: int = 0
    comment: str = "akstack_auto"
    ticket: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "command_id": self.command_id,
            "action": self.action.value,
            "symbol": self.symbol,
            "type": self.order_type.value if self.order_type else None,
            "lots": float(self.lots),
            "price": float(self.price),
            "sl": float(self.sl),
            "tp": float(self.tp),
            "magic": self.magic,
            "comment": self.comment,
            "ticket": self.ticket,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> TradeCommand:
        return cls(
            command_id=data["command_id"],
            action=CommandAction(data["action"]),
            symbol=data["symbol"],
            order_type=OrderType(data["type"]) if data.get("type") else None,
            lots=Decimal(str(data.get("lots", "0.01"))),
            price=Decimal(str(data.get("price", "0.0"))),
            sl=Decimal(str(data.get("sl", "0.0"))),
            tp=Decimal(str(data.get("tp", "0.0"))),
            magic=int(data.get("magic", 0)),
            comment=str(data.get("comment", "")),
            ticket=int(data["ticket"]) if data.get("ticket") is not None else None,
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class ExecutionReport:
    """Report written by MT4 EA to DWX_Reports.txt upon order execution."""
    ticket: int
    magic: int
    symbol: str
    order_type: OrderType
    lots: Decimal
    open_price: Decimal
    sl: Decimal
    tp: Decimal
    status: str  # "FILLED", "REJECTED", "ERROR", "CLOSED", "MODIFIED"
    error_code: int = 0
    message: str = "OK"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "ticket": self.ticket,
            "magic": self.magic,
            "symbol": self.symbol,
            "type": self.order_type.value,
            "lots": float(self.lots),
            "open_price": float(self.open_price),
            "sl": float(self.sl),
            "tp": float(self.tp),
            "status": self.status,
            "error_code": self.error_code,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionReport:
        return cls(
            ticket=int(data["ticket"]),
            magic=int(data.get("magic", 0)),
            symbol=str(data["symbol"]),
            order_type=OrderType(data["type"]),
            lots=Decimal(str(data["lots"])),
            open_price=Decimal(str(data["open_price"])),
            sl=Decimal(str(data.get("sl", "0.0"))),
            tp=Decimal(str(data.get("tp", "0.0"))),
            status=str(data["status"]),
            error_code=int(data.get("error_code", 0)),
            message=str(data.get("message", "OK")),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
        )


class DWXClient:
    """DWX Connect file protocol client for communicating with MT4 EA.
    
    Reads/writes files inside the MT4 MQL4/Files directory:
    - Commands: DWX_Commands.txt
    - Reports:  DWX_Reports.txt
    - Bars:     DWX_Bars_<SYMBOL>_<TIMEFRAME>.txt
    """

    def __init__(
        self,
        mt4_files_dir: str | Path,
        max_retries: int = 8,
        initial_backoff_ms: int = 30,
        max_backoff_ms: int = 600,
        alert_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.files_dir = Path(mt4_files_dir).resolve()
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.initial_backoff_ms = initial_backoff_ms
        self.max_backoff_ms = max_backoff_ms
        self.alert_callback = alert_callback

        # Track active magic numbers to prevent duplicate orders
        self._sent_magics: Set[int] = set()
        self._confirmed_tickets: Dict[int, int] = {}  # magic -> ticket

    @property
    def commands_file(self) -> Path:
        return self.files_dir / "DWX_Commands.txt"

    @property
    def reports_file(self) -> Path:
        return self.files_dir / "DWX_Reports.txt"

    def get_bars_file(self, symbol: str, timeframe: str = "M5") -> Path:
        clean_symbol = symbol.replace("/", "").upper()
        return self.files_dir / f"DWX_Bars_{clean_symbol}_{timeframe.upper()}.txt"

    # -------------------------------------------------------------------------
    # Atomic File Operations with Exponential Backoff
    # -------------------------------------------------------------------------

    def atomic_write(self, target_path: Path, content: str) -> None:
        """Atomically writes content by writing to a temporary file then replacing.
        Uses exponential backoff for Windows file-locking retry."""
        temp_path = target_path.parent / f"{target_path.stem}_{uuid.uuid4().hex[:8]}.tmp"
        
        # Write to temp file first
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Atomically replace target
        backoff = self.initial_backoff_ms / 1000.0
        for attempt in range(self.max_retries):
            try:
                os.replace(temp_path, target_path)
                return
            except (PermissionError, OSError) as e:
                if attempt == self.max_retries - 1:
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                    logger.error(f"Failed to atomic replace {target_path} after {self.max_retries} attempts: {e}")
                    raise
                # Jittered backoff
                jitter = random.uniform(0.8, 1.2)
                time.sleep(min(backoff * jitter, self.max_backoff_ms / 1000.0))
                backoff *= 1.8

    def atomic_read(self, target_path: Path) -> str:
        """Reads target file with exponential backoff on file lock / permission collision."""
        if not target_path.exists():
            return ""

        backoff = self.initial_backoff_ms / 1000.0
        for attempt in range(self.max_retries):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    return f.read()
            except (PermissionError, BlockingIOError, OSError) as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed to read {target_path} after {self.max_retries} attempts: {e}")
                    raise
                jitter = random.uniform(0.8, 1.2)
                time.sleep(min(backoff * jitter, self.max_backoff_ms / 1000.0))
                backoff *= 1.8
        return ""

    # -------------------------------------------------------------------------
    # Command Dispatching
    # -------------------------------------------------------------------------

    def send_order(
        self,
        symbol: str,
        order_type: OrderType,
        lots: Decimal,
        sl: Decimal,
        tp: Decimal,
        magic: int,
        comment: str = "akstack_auto",
    ) -> TradeCommand:
        """Sends an OPEN market order command to MT4 EA via DWX_Commands.txt.
        Enforces unique magic number constraint to prevent duplicate orders."""
        if magic in self._sent_magics:
            raise ValueError(f"Magic number {magic} has already been submitted! Duplicate order rejected.")

        command_id = f"cmd_{int(time.time()*1000)}_{magic}"
        cmd = TradeCommand(
            command_id=command_id,
            action=CommandAction.OPEN,
            symbol=symbol.replace("/", "").upper(),
            order_type=order_type,
            lots=lots,
            sl=sl,
            tp=tp,
            magic=magic,
            comment=comment,
        )

        self._append_command(cmd)
        self._sent_magics.add(magic)
        logger.info(f"Dispatched order command: {cmd.command_id} {cmd.order_type} {cmd.lots} {cmd.symbol} magic={cmd.magic}")
        return cmd

    def send_modify(self, ticket: int, sl: Decimal, tp: Decimal, symbol: str = "") -> TradeCommand:
        """Sends a MODIFY command to adjust SL/TP of an existing open position."""
        command_id = f"mod_{int(time.time()*1000)}_{ticket}"
        cmd = TradeCommand(
            command_id=command_id,
            action=CommandAction.MODIFY,
            symbol=symbol,
            ticket=ticket,
            sl=sl,
            tp=tp,
        )
        self._append_command(cmd)
        logger.info(f"Dispatched modify command: {cmd.command_id} ticket={ticket} SL={sl} TP={tp}")
        return cmd

    def send_close(self, ticket: int, lots: Decimal = Decimal("0.0"), symbol: str = "") -> TradeCommand:
        """Sends a CLOSE command to close an existing open position."""
        command_id = f"cls_{int(time.time()*1000)}_{ticket}"
        cmd = TradeCommand(
            command_id=command_id,
            action=CommandAction.CLOSE,
            symbol=symbol,
            ticket=ticket,
            lots=lots,
        )
        self._append_command(cmd)
        logger.info(f"Dispatched close command: {cmd.command_id} ticket={ticket}")
        return cmd

    def _append_command(self, cmd: TradeCommand) -> None:
        """Appends command to DWX_Commands.txt using atomic write."""
        existing = self.atomic_read(self.commands_file)
        lines = [line.strip() for line in existing.splitlines() if line.strip()]
        lines.append(json.dumps(cmd.to_dict()))
        self.atomic_write(self.commands_file, "\n".join(lines) + "\n")

    def clear_commands(self) -> None:
        """Clears all pending commands from DWX_Commands.txt."""
        self.atomic_write(self.commands_file, "")

    # -------------------------------------------------------------------------
    # Execution Report Polling & Verification
    # -------------------------------------------------------------------------

    def read_all_reports(self) -> List[ExecutionReport]:
        """Reads and parses all execution reports from DWX_Reports.txt."""
        content = self.atomic_read(self.reports_file)
        if not content:
            return []

        reports: List[ExecutionReport] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                reports.append(ExecutionReport.from_dict(data))
            except Exception as e:
                logger.warning(f"Failed to parse report line '{line}': {e}")
        return reports

    def poll_order_confirmation(
        self,
        magic: int,
        timeout_sec: float = 10.0,
        poll_interval_sec: float = 0.2,
    ) -> Optional[ExecutionReport]:
        """Polls DWX_Reports.txt until an execution report matching magic number appears.
        
        If timeout is exceeded:
        - Logs an error and triggers the alert callback.
        - Does NOT re-attempt or send duplicates.
        """
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            reports = self.read_all_reports()
            for r in reversed(reports):
                if r.magic == magic:
                    if r.status in ("FILLED", "OPEN"):
                        self._confirmed_tickets[magic] = r.ticket
                        logger.info(f"Trade confirmed! Magic {magic} -> Ticket {r.ticket} @ {r.open_price}")
                        return r
                    elif r.status in ("REJECTED", "ERROR"):
                        logger.warning(f"Trade rejected by EA! Magic {magic}: {r.message} (code={r.error_code})")
                        return r

            time.sleep(poll_interval_sec)

        # Timeout reached without confirmation
        alert_msg = (
            f"ALERT: Order with magic {magic} UNCONFIRMED after {timeout_sec:.1f}s! "
            f"No duplicate sent. Manual MT4 verification required."
        )
        logger.critical(alert_msg)
        if self.alert_callback:
            self.alert_callback(alert_msg)
        return None

    # -------------------------------------------------------------------------
    # Closed Bars Ingestion
    # -------------------------------------------------------------------------

    def read_closed_bars(self, symbol: str, timeframe: str = "M5") -> List[Candle]:
        """Reads historical closed bars exported by MT4 EA.
        
        Expected file format in DWX_Bars_<SYMBOL>_<TIMEFRAME>.txt:
        CSV header: timestamp,open,high,low,close,volume
        Rows: 2026-09-24 03:25:00,1.08500,1.08550,1.08480,1.08520,150
        
        Returns parsed Candle instances sorted ascending by timestamp.
        """
        bars_file = self.get_bars_file(symbol, timeframe)
        content = self.atomic_read(bars_file)
        if not content:
            return []

        candles: List[Candle] = []
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return []

        # Parse CSV lines
        has_header = "timestamp" in lines[0].lower() or "time" in lines[0].lower()
        data_lines = lines[1:] if has_header else lines

        for line in data_lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            try:
                # MT4 standard timestamp format: YYYY.MM.DD HH:MM or YYYY-MM-DD HH:MM:SS
                raw_time = parts[0].replace(".", "-")
                if len(raw_time) == 16:
                    dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

                c = Candle(
                    timestamp=dt,
                    open=float(parts[1]),
                    high=float(parts[2]),
                    low=float(parts[3]),
                    close=float(parts[4]),
                    volume=float(parts[5]) if len(parts) > 5 else 0.0,
                )
                candles.append(c)
            except Exception as e:
                logger.debug(f"Skipping malformed bar line '{line}': {e}")

        candles.sort(key=lambda c: c.timestamp)
        return candles

    def write_mock_bars(self, symbol: str, timeframe: str, candles: List[Candle]) -> None:
        """Utility for test simulation: writes candles to DWX bar file format."""
        bars_file = self.get_bars_file(symbol, timeframe)
        lines = ["timestamp,open,high,low,close,volume"]
        for c in candles:
            time_str = c.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"{time_str},{c.open:.5f},{c.high:.5f},{c.low:.5f},{c.close:.5f},{c.volume}")
        self.atomic_write(bars_file, "\n".join(lines) + "\n")

    def write_mock_report(self, report: ExecutionReport) -> None:
        """Utility for test simulation: writes an execution report to DWX_Reports.txt."""
        existing = self.atomic_read(self.reports_file)
        lines = [line.strip() for line in existing.splitlines() if line.strip()]
        lines.append(json.dumps(report.to_dict()))
        self.atomic_write(self.reports_file, "\n".join(lines) + "\n")
