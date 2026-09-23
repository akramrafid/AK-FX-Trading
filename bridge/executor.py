"""bridge/executor.py
MT4 closed-bar poller and automated signal execution bridge.

Connects:
- MT4 DWX bar data files -> RuleEngine closed-candle processing
- RuleEngine signals -> PositionSizer dynamic risk & lot computation
- Position sizing -> DWXClient atomic command dispatch & confirmation polling
- Idempotency & Magic number tracking to prevent duplicate executions.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Set

from bridge.dwx_client import DWXClient, ExecutionReport, OrderType, TradeCommand
from bridge.sizing import PositionSizer, SizingResult
from engine.models import Candle, Direction, TradeSignal
from engine.rule_engine import RuleEngine

logger = logging.getLogger("executor")


def generate_mt4_magic_number(dt: datetime, sequence: int = 1) -> int:
    """Generates a deterministic 32-bit signed integer magic number for MT4.
    
    MT4 Magic Numbers are 32-bit signed integers (max 2,147,483,647).
    To prevent integer overflow while maintaining uniqueness:
    Formula: (Month*10000000 + Day*100000 + Hour*1000 + Minute*10 + sequence) % 2000000000
    Example: Sept 24, 03:25 -> 09*10000000 + 24*100000 + 03*1000 + 25*10 + 1 = 92,403,251 (< 2.14B).
    """
    base = (dt.month * 10_000_000) + (dt.day * 100_000) + (dt.hour * 1000) + (dt.minute * 10) + (sequence % 10)
    return int(base % 2_000_000_000)


@dataclass
class BridgeOrderRecord:
    """Audit record for bridge order dispatch and confirmation."""
    magic: int
    signal_id: str
    symbol: str
    direction: Direction
    lots: Decimal
    entry_price: Decimal
    sl_price: Decimal
    tp_price: Decimal
    risk_pips: Decimal
    reward_pips: Decimal
    dispatched_at: datetime
    ticket: Optional[int] = None
    status: str = "PENDING"  # PENDING, FILLED, REJECTED, UNCONFIRMED
    fill_price: Optional[Decimal] = None
    confirmed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class BridgeExecutor:
    """Automated trading bridge orchestrating closed-bar ingestion, strategy evaluation,
    dynamic position sizing, and atomic MT4 command execution."""

    def __init__(
        self,
        symbol: str,
        dwx_client: DWXClient,
        rule_engine: Optional[RuleEngine] = None,
        position_sizer: Optional[PositionSizer] = None,
        timeframe: str = "M5",
        initial_balance: Decimal = Decimal("10000.00"),
        risk_pct: Decimal = Decimal("0.015"),
        confirmation_timeout_sec: float = 10.0,
        exchange_rates: Optional[Dict[str, Decimal]] = None,
        on_signal_callback: Optional[Callable[[TradeSignal], None]] = None,
        on_order_callback: Optional[Callable[[BridgeOrderRecord], None]] = None,
    ) -> None:
        self.symbol = symbol.replace("/", "").upper()
        self.dwx_client = dwx_client
        self.timeframe = timeframe.upper()
        self.balance = initial_balance
        self.risk_pct = risk_pct
        self.confirmation_timeout_sec = confirmation_timeout_sec
        self.exchange_rates = exchange_rates or {}

        # Core Rule Engine (strictly shared between backtester & live bridge)
        self.rule_engine = rule_engine or RuleEngine(swing_lookback=20)
        self.position_sizer = position_sizer or PositionSizer(default_risk_pct=risk_pct)

        # Callbacks
        self.on_signal_callback = on_signal_callback
        self.on_order_callback = on_order_callback

        # State tracking
        self.candle_history: List[Candle] = []
        self.last_processed_bar_time: Optional[datetime] = None
        self.processed_signal_keys: Set[str] = set()
        self.order_records: List[BridgeOrderRecord] = []
        self._running = False
        self._magic_seq = 0

    def step(self) -> Optional[BridgeOrderRecord]:
        """Performs a single execution cycle:
        1. Reads closed bars exported by MT4 EA.
        2. Filters for newly closed bars since last cycle.
        3. Evaluates strategy through RuleEngine.
        4. If signal generated, calculates position size.
        5. Dispatches order to MT4 and polls for confirmation.
        
        Returns BridgeOrderRecord if a trade was dispatched, else None.
        """
        closed_bars = self.dwx_client.read_closed_bars(self.symbol, self.timeframe)
        if not closed_bars:
            return None

        dispatched_record: Optional[BridgeOrderRecord] = None

        if self.last_processed_bar_time is None:
            # First initialization: store history and evaluate latest closed bar
            self.candle_history = list(closed_bars)
            self.last_processed_bar_time = closed_bars[-1].timestamp
            if len(self.candle_history) >= 5:
                signal = self.rule_engine.evaluate_completed_candle(self.candle_history)
                if signal is not None:
                    dispatched_record = self._execute_signal(signal)
            return dispatched_record

        # Find new bars that closed after last processed timestamp
        new_bars = [c for c in closed_bars if c.timestamp > self.last_processed_bar_time]
        if not new_bars:
            return None

        for bar in new_bars:
            self.last_processed_bar_time = bar.timestamp
            self.candle_history.append(bar)
            if len(self.candle_history) >= 5:
                signal = self.rule_engine.evaluate_completed_candle(self.candle_history)
                if signal is not None:
                    record = self._execute_signal(signal)
                    if record is not None:
                        dispatched_record = record

        return dispatched_record

    def _execute_signal(self, signal: TradeSignal) -> Optional[BridgeOrderRecord]:
        """Validates signal, computes dynamic position size, and dispatches to MT4."""
        signal_dir = Direction.BUY if str(signal.direction).upper() == "BUY" else Direction.SELL
        signal_time = signal.timestamp or datetime.now(timezone.utc)

        # Signal idempotency key
        signal_key = f"{self.symbol}_{signal_dir.value}_{signal_time.isoformat()}"
        if signal_key in self.processed_signal_keys:
            logger.warning(f"Duplicate signal detected for key {signal_key}; skipping execution.")
            return None
        self.processed_signal_keys.add(signal_key)

        if self.on_signal_callback:
            self.on_signal_callback(signal)

        # Convert price values to Decimal for precision financial tracking
        entry_dec = Decimal(str(round(signal.entry_price, 5)))
        sl_dec = Decimal(str(round(signal.stop_loss, 5)))
        tp_dec = Decimal(str(round(signal.take_profit, 5)))

        # Dynamic lot sizing
        stop_pips = self.position_sizer.price_diff_to_pips(self.symbol, signal.risk_distance)
        sizing: SizingResult = self.position_sizer.calculate_lots(
            account_balance=self.balance,
            stop_pips=stop_pips,
            symbol=self.symbol,
            risk_pct=self.risk_pct,
            rates=self.exchange_rates,
            current_price=entry_dec,
        )

        if not sizing.is_valid:
            logger.warning(f"Order rejected by position sizer: {sizing.rejection_reason}")
            record = BridgeOrderRecord(
                magic=0,
                signal_id=signal_key,
                symbol=self.symbol,
                direction=signal_dir,
                lots=Decimal("0.00"),
                entry_price=entry_dec,
                sl_price=sl_dec,
                tp_price=tp_dec,
                risk_pips=stop_pips,
                reward_pips=self.position_sizer.price_diff_to_pips(self.symbol, signal.reward_distance),
                dispatched_at=datetime.now(timezone.utc),
                status="REJECTED",
                rejection_reason=sizing.rejection_reason,
            )
            self.order_records.append(record)
            if self.on_order_callback:
                self.on_order_callback(record)
            return record

        # Generate MT4 magic number
        self._magic_seq += 1
        magic = generate_mt4_magic_number(signal_time, self._magic_seq)

        order_type = OrderType.BUY if signal_dir == Direction.BUY else OrderType.SELL

        record = BridgeOrderRecord(
            magic=magic,
            signal_id=signal_key,
            symbol=self.symbol,
            direction=signal_dir,
            lots=sizing.lots,
            entry_price=entry_dec,
            sl_price=sl_dec,
            tp_price=tp_dec,
            risk_pips=stop_pips,
            reward_pips=self.position_sizer.price_diff_to_pips(self.symbol, signal.reward_distance),
            dispatched_at=datetime.now(timezone.utc),
            status="PENDING",
        )
        self.order_records.append(record)

        # Dispatch command via DWX Client
        try:
            self.dwx_client.send_order(
                symbol=self.symbol,
                order_type=order_type,
                lots=sizing.lots,
                sl=sl_dec,
                tp=tp_dec,
                magic=magic,
                comment="akstack_10R",
            )
        except Exception as e:
            logger.error(f"Failed to dispatch order to DWX: {e}")
            record.status = "ERROR"
            record.rejection_reason = str(e)
            if self.on_order_callback:
                self.on_order_callback(record)
            return record

        # Poll execution report for confirmation
        report: Optional[ExecutionReport] = self.dwx_client.poll_order_confirmation(
            magic=magic,
            timeout_sec=self.confirmation_timeout_sec,
        )

        if report is not None:
            if report.status in ("FILLED", "OPEN"):
                record.status = "FILLED"
                record.ticket = report.ticket
                record.fill_price = report.open_price
                record.confirmed_at = report.timestamp
                logger.info(f"Order FILLED: Ticket {record.ticket} at {record.fill_price}")
            else:
                record.status = "REJECTED"
                record.rejection_reason = f"{report.message} (error code {report.error_code})"
                logger.warning(f"Order REJECTED by MT4: {record.rejection_reason}")
        else:
            record.status = "UNCONFIRMED"
            record.rejection_reason = f"Timeout ({self.confirmation_timeout_sec}s) waiting for ticket confirmation."
            logger.critical(f"Order UNCONFIRMED for magic {magic}! Check MT4 manually.")

        if self.on_order_callback:
            self.on_order_callback(record)

        return record

    def run(self, poll_interval_sec: float = 1.0, max_cycles: Optional[int] = None) -> None:
        """Runs the continuous bar poller loop until stopped."""
        self._running = True
        logger.info(f"Starting BridgeExecutor for {self.symbol} {self.timeframe}...")
        cycles = 0

        try:
            while self._running:
                self.step()
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                time.sleep(poll_interval_sec)
        except KeyboardInterrupt:
            logger.info("BridgeExecutor stopped by user.")
        finally:
            self._running = False
            logger.info("BridgeExecutor loop terminated.")

    def stop(self) -> None:
        """Signals the bridge loop to stop gracefully."""
        self._running = False
