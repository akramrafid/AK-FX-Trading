"""database/sqlite_manager.py
Zero-dependency SQLite persistence layer for AK Forex Trading system.

Provides production storage for:
1. Closed Candles (OHLCV time-series deduplicated by symbol, timeframe, timestamp)
2. Strategy Trade Signals (sweep levels, 10:1 R:R parameters, execution status)
3. Orders & Execution Telemetry (tickets, magics, fills, slippage)
4. Trade Journal (closed trade telemetry, realized PnL, exit reasons)
5. Daily Performance Metrics (daily balance, equity, drawdowns, circuit breakers)
6. Audit Logs (immutable operational event trail)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Sequence

from engine.models import Candle, Direction, TradeSignal

logger = logging.getLogger("database")


class TradingDatabase:
    """Thread-safe, zero-dependency SQLite database manager."""

    def __init__(self, db_path: str | Path = "data/trading.db") -> None:
        self.db_path_str = str(db_path)
        self.is_memory = self.db_path_str == ":memory:"

        if not self.is_memory:
            self.db_path = Path(db_path).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.db_path = Path(":memory:")
            # For in-memory testing, retain a persistent connection
            self._memory_conn: Optional[sqlite3.Connection] = sqlite3.connect(
                ":memory:", check_same_thread=False
            )
            self._memory_conn.row_factory = sqlite3.Row

        self.init_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides an isolated connection with automatic commit / rollback."""
        if self.is_memory and self._memory_conn is not None:
            conn = self._memory_conn
            yield conn
            conn.commit()
            return

        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Initializes tables, composite unique constraints, and performance indexes."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            if not self.is_memory:
                cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA foreign_keys=ON;")

            # 1. Closed Market Candles
            cur.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL DEFAULT 'M5',
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL DEFAULT 0.0,
                    is_closed INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, timeframe, timestamp)
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_lookup 
                ON candles (symbol, timeframe, timestamp DESC);
            """)

            # 2. Strategy Signals
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL DEFAULT 'M5',
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    risk_distance REAL NOT NULL,
                    reward_distance REAL NOT NULL,
                    rr_ratio REAL NOT NULL DEFAULT 10.0,
                    sweep_level REAL,
                    confirmation_candle INTEGER,
                    executed INTEGER NOT NULL DEFAULT 0,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_lookup 
                ON trade_signals (symbol, timestamp DESC);
            """)

            # 3. Dispatched Orders & Execution Status
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_id TEXT UNIQUE NOT NULL,
                    magic_number INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    lots REAL NOT NULL,
                    target_entry REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'SUBMITTED',
                    risk_rejected_reason TEXT,
                    ticket INTEGER,
                    fill_price REAL,
                    slippage_pips REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_magic 
                ON orders (magic_number);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status 
                ON orders (status, created_at DESC);
            """)

            # 4. Closed Trade Journal
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER UNIQUE NOT NULL,
                    magic_number INTEGER,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    close_time TEXT,
                    open_price REAL NOT NULL,
                    close_price REAL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    lots REAL NOT NULL,
                    realized_pnl REAL,
                    exit_reason TEXT,
                    environment TEXT NOT NULL DEFAULT 'LIVE',
                    created_at TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_journal_time 
                ON trade_journal (open_time DESC);
            """)

            # 5. Daily Performance & Circuit Breaker Metrics
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT UNIQUE NOT NULL,
                    starting_balance REAL NOT NULL,
                    closing_equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0.0,
                    trade_count INTEGER NOT NULL DEFAULT 0,
                    win_count INTEGER NOT NULL DEFAULT 0,
                    loss_count INTEGER NOT NULL DEFAULT 0,
                    max_drawdown_pct REAL NOT NULL DEFAULT 0.0,
                    circuit_breaker_tripped INTEGER NOT NULL DEFAULT 0,
                    environment TEXT NOT NULL DEFAULT 'LIVE',
                    created_at TEXT NOT NULL
                );
            """)

            # 6. Operational Audit Trail
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source_component TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_time 
                ON audit_logs (created_at DESC);
            """)

    # -------------------------------------------------------------------------
    # Candle Operations
    # -------------------------------------------------------------------------

    def save_candle(self, candle: Candle, symbol: str, timeframe: str = "M5") -> None:
        """Persists a single closed candle with deduplication."""
        self.save_candles([candle], symbol=symbol, timeframe=timeframe)

    def save_candles(
        self, candles: Sequence[Candle], symbol: str, timeframe: str = "M5"
    ) -> int:
        """Batch inserts candles using INSERT OR IGNORE for idempotency."""
        if not candles:
            return 0

        now_str = datetime.now(timezone.utc).isoformat()
        records = [
            (
                symbol.replace("/", "").upper(),
                timeframe.upper(),
                c.timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(c.timestamp, datetime) else str(c.timestamp),
                float(c.open),
                float(c.high),
                float(c.low),
                float(c.close),
                float(c.volume),
                1,
                now_str,
            )
            for c in candles
        ]

        query = """
            INSERT OR IGNORE INTO candles (
                symbol, timeframe, timestamp, open, high, low, close, volume, is_closed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(query, records)
            return cur.rowcount

    def get_recent_candles(
        self, symbol: str, timeframe: str = "M5", limit: int = 100
    ) -> List[Candle]:
        """Retrieves recent candles sorted chronologically ascending."""
        clean_symbol = symbol.replace("/", "").upper()
        clean_tf = timeframe.upper()
        query = """
            SELECT timestamp, open, high, low, close, volume 
            FROM candles 
            WHERE symbol = ? AND timeframe = ? 
            ORDER BY timestamp DESC LIMIT ?;
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (clean_symbol, clean_tf, limit))
            rows = cur.fetchall()

        candles: List[Candle] = []
        for r in reversed(rows):
            dt_str = r["timestamp"]
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                dt = datetime.fromisoformat(dt_str)
            candles.append(
                Candle(
                    timestamp=dt,
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]),
                )
            )
        return candles

    # -------------------------------------------------------------------------
    # Signal Operations
    # -------------------------------------------------------------------------

    def save_signal(
        self,
        signal: TradeSignal,
        symbol: str,
        timeframe: str = "M5",
        executed: bool = False,
        rejection_reason: str = "",
    ) -> int:
        """Stores a generated trade signal and its execution state."""
        now_str = datetime.now(timezone.utc).isoformat()
        ts_str = (
            signal.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if signal.timestamp
            else now_str
        )
        dir_str = "BUY" if str(signal.direction).upper() in ("BUY", "DIRECTION.BUY") else "SELL"

        query = """
            INSERT INTO trade_signals (
                timestamp, symbol, timeframe, direction, entry_price, stop_loss, take_profit,
                risk_distance, reward_distance, rr_ratio, sweep_level, confirmation_candle,
                executed, rejection_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        rr = getattr(signal, "reward_risk_ratio", getattr(signal, "rr_ratio", 10.0))
        sweep_lvl = getattr(signal, "sweep_level", None)
        conf_idx = getattr(signal, "confirmation_candle_index", None)
        if conf_idx is None and getattr(signal, "confirmation_indices", None):
            conf_idx = signal.confirmation_indices[-1]

        values = (
            ts_str,
            symbol.replace("/", "").upper(),
            timeframe.upper(),
            dir_str,
            float(signal.entry_price),
            float(signal.stop_loss),
            float(signal.take_profit),
            float(signal.risk_distance),
            float(signal.reward_distance),
            float(rr),
            float(sweep_lvl) if sweep_lvl is not None else None,
            int(conf_idx) if conf_idx is not None else None,
            1 if executed else 0,
            rejection_reason,
            now_str,
        )
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, values)
            return cur.lastrowid or 0

    def get_signals(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves past signals for an instrument."""
        query = """
            SELECT * FROM trade_signals 
            WHERE symbol = ? 
            ORDER BY timestamp DESC LIMIT ?;
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (symbol.replace("/", "").upper(), limit))
            return [dict(r) for r in cur.fetchall()]

    # -------------------------------------------------------------------------
    # Order & Execution Operations
    # -------------------------------------------------------------------------

    def save_order(
        self,
        command_id: str,
        magic_number: int,
        symbol: str,
        direction: str,
        lots: float,
        target_entry: float,
        stop_loss: float,
        take_profit: float,
        status: str = "SUBMITTED",
        risk_rejected_reason: str = "",
        ticket: Optional[int] = None,
        fill_price: Optional[float] = None,
    ) -> int:
        """Stores a newly dispatched or validated order."""
        now_str = datetime.now(timezone.utc).isoformat()
        query = """
            INSERT INTO orders (
                command_id, magic_number, symbol, direction, lots, target_entry,
                stop_loss, take_profit, status, risk_rejected_reason, ticket,
                fill_price, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        values = (
            command_id,
            magic_number,
            symbol.replace("/", "").upper(),
            direction.upper(),
            float(lots),
            float(target_entry),
            float(stop_loss),
            float(take_profit),
            status.upper(),
            risk_rejected_reason,
            ticket,
            fill_price,
            now_str,
        )
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, values)
            return cur.lastrowid or 0

    def update_order_fill(
        self,
        magic_number: int,
        ticket: int,
        fill_price: float,
        slippage_pips: float = 0.0,
        status: str = "FILLED",
    ) -> bool:
        """Updates an order with its confirmed MT4 ticket and execution price."""
        query = """
            UPDATE orders 
            SET ticket = ?, fill_price = ?, slippage_pips = ?, status = ?
            WHERE magic_number = ?;
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (ticket, fill_price, slippage_pips, status, magic_number))
            return cur.rowcount > 0

    def record_closed_trade(
        self,
        ticket: int,
        magic_number: int,
        symbol: str,
        direction: str,
        open_time: str,
        close_time: str,
        open_price: float,
        close_price: float,
        stop_loss: float,
        take_profit: float,
        lots: float,
        realized_pnl: float,
        exit_reason: str = "TP",
        environment: str = "LIVE",
    ) -> int:
        """Records a finalized, closed trade into the journal."""
        now_str = datetime.now(timezone.utc).isoformat()
        query = """
            INSERT INTO trade_journal (
                ticket, magic_number, symbol, direction, open_time, close_time,
                open_price, close_price, stop_loss, take_profit, lots, realized_pnl,
                exit_reason, environment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket) DO UPDATE SET 
                close_time = excluded.close_time,
                close_price = excluded.close_price,
                realized_pnl = excluded.realized_pnl,
                exit_reason = excluded.exit_reason;
        """
        values = (
            ticket,
            magic_number,
            symbol.replace("/", "").upper(),
            direction.upper(),
            open_time,
            close_time,
            open_price,
            close_price,
            stop_loss,
            take_profit,
            lots,
            realized_pnl,
            exit_reason,
            environment.upper(),
            now_str,
        )
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, values)
            # Also update orders table if matching ticket exists
            cur.execute(
                "UPDATE orders SET status = 'CLOSED', closed_at = ? WHERE ticket = ?;",
                (close_time, ticket),
            )
            return cur.lastrowid or 0

    def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent orders."""
        query = "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?;"
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_journal_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent closed trade journal entries."""
        query = "SELECT * FROM trade_journal ORDER BY open_time DESC LIMIT ?;"
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (limit,))
            return [dict(r) for r in cur.fetchall()]

    # -------------------------------------------------------------------------
    # Daily Performance & Circuit Breaker Metrics
    # -------------------------------------------------------------------------

    def save_daily_metrics(
        self,
        trade_date: str,
        starting_balance: float,
        closing_equity: float,
        realized_pnl: float,
        trade_count: int,
        win_count: int = 0,
        loss_count: int = 0,
        max_drawdown_pct: float = 0.0,
        circuit_breaker_tripped: bool = False,
        environment: str = "LIVE",
    ) -> None:
        """Upserts daily risk and performance telemetry."""
        now_str = datetime.now(timezone.utc).isoformat()
        query = """
            INSERT INTO daily_metrics (
                trade_date, starting_balance, closing_equity, realized_pnl,
                trade_count, win_count, loss_count, max_drawdown_pct,
                circuit_breaker_tripped, environment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date) DO UPDATE SET 
                closing_equity = excluded.closing_equity,
                realized_pnl = excluded.realized_pnl,
                trade_count = excluded.trade_count,
                win_count = excluded.win_count,
                loss_count = excluded.loss_count,
                max_drawdown_pct = excluded.max_drawdown_pct,
                circuit_breaker_tripped = excluded.circuit_breaker_tripped;
        """
        values = (
            trade_date,
            starting_balance,
            closing_equity,
            realized_pnl,
            trade_count,
            win_count,
            loss_count,
            max_drawdown_pct,
            1 if circuit_breaker_tripped else 0,
            environment.upper(),
            now_str,
        )
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, values)

    def get_daily_metrics(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieves daily performance history."""
        query = "SELECT * FROM daily_metrics ORDER BY trade_date DESC LIMIT ?;"
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (limit,))
            return [dict(r) for r in cur.fetchall()]

    # -------------------------------------------------------------------------
    # Audit Trail
    # -------------------------------------------------------------------------

    def log_audit_event(
        self, event_type: str, source: str, details: Dict[str, Any] | str
    ) -> int:
        """Appends an immutable audit log record."""
        now_str = datetime.now(timezone.utc).isoformat()
        details_str = json.dumps(details) if isinstance(details, dict) else str(details)
        query = """
            INSERT INTO audit_logs (event_type, source_component, details, created_at)
            VALUES (?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (event_type, source, details_str, now_str))
            return cur.lastrowid or 0

    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent audit logs."""
        query = "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?;"
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (limit,))
            return [dict(r) for r in cur.fetchall()]
