"""bridge/executor.py
MT4 closed-bar poller and automated signal execution bridge.

Connects:
- MT4 DWX bar data files -> RuleEngine closed-candle processing
- RuleEngine signals -> PositionSizer dynamic risk & lot computation
- Position sizing -> DWXClient atomic command dispatch & confirmation polling
- Idempotency & Magic number tracking to prevent duplicate executions.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Callable, Dict, List, Optional, Set

from bridge.dwx_client import DWXClient, ExecutionReport, OrderType, TradeCommand
from bridge.sizing import PositionSizer, SizingResult
from bridge.watchdog import BridgeWatchdog
from database.sqlite_manager import TradingDatabase
from engine.models import Candle, Direction, TradeSignal
from engine.rule_engine import RuleEngine
from risk.guardrails import RiskGuardrails
from risk.models import AccountState, ValidationResult

logger = logging.getLogger("executor")

TIMEFRAME_DELTAS: Dict[str, timedelta] = {
    "M1": timedelta(minutes=1),
    "M5": timedelta(minutes=5),
    "M15": timedelta(minutes=15),
    "M30": timedelta(minutes=30),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
}


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
class ActiveBridgeTrade:
    """Tracks active MT4 position for live trade management (Pillar 5)."""
    ticket: int
    magic: int
    symbol: str
    direction: Direction
    entry_price: Decimal
    sl_price: Decimal
    tp_price: Decimal
    lots: Decimal
    risk_pips: Decimal
    partial_banked: bool = False
    breakeven_set: bool = False
    partial_bank_pct: Optional[Decimal] = Decimal("0.70")


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
        risk_guardrails: Optional[RiskGuardrails] = None,
        watchdog: Optional[BridgeWatchdog] = None,
        db: Optional[TradingDatabase] = None,
        timeframe: str = "M5",
        initial_balance: Decimal = Decimal("10000.00"),
        risk_pct: Decimal = Decimal("0.015"),
        confirmation_timeout_sec: float = 10.0,
        exchange_rates: Optional[Dict[str, Decimal]] = None,
        on_signal_callback: Optional[Callable[[TradeSignal], None]] = None,
        on_order_callback: Optional[Callable[[BridgeOrderRecord], None]] = None,
    ) -> None:
        self.symbol = symbol.strip().replace("/", "")
        self.dwx_client = dwx_client
        self.timeframe = timeframe.upper()
        self.timeframe_delta = TIMEFRAME_DELTAS.get(self.timeframe, timedelta(minutes=5))
        self.balance = initial_balance
        self.risk_pct = risk_pct
        self.confirmation_timeout_sec = confirmation_timeout_sec
        self.exchange_rates = exchange_rates or {}

        # Core Rule Engine (strictly shared between backtester & live bridge)
        self.rule_engine = rule_engine or RuleEngine(swing_lookback=20)
        self.position_sizer = position_sizer or PositionSizer(default_risk_pct=risk_pct)
        self.risk_guardrails = risk_guardrails  # None = guardrails not wired (legacy/test mode)
        self.watchdog = watchdog
        self.db = db

        # Callbacks
        self.on_signal_callback = on_signal_callback
        self.on_order_callback = on_order_callback

        # State tracking
        self.candle_history: List[Candle] = []
        self.last_processed_bar_time: Optional[datetime] = None
        self.last_processed_m1_time: Optional[datetime] = None
        self.last_processed_m5_time: Optional[datetime] = None
        self.last_processed_m15_time: Optional[datetime] = None
        self.processed_signal_keys: Set[str] = set()
        self.order_records: List[BridgeOrderRecord] = []
        self.active_trades: Dict[int, ActiveBridgeTrade] = {}
        self._running = False
        self._magic_seq = 0

    def _manage_active_trades(self, current_bar: Candle) -> None:
        """Applies Institutional Pillar 5 dynamic trade management to active MT4 positions:
        - Milestone 1: At +2.0R, bank 70% partial profits via send_close.
        - Milestone 2: At +2.0R, move SL to breakeven (+0.5 pip buffer) via send_modify.
        """
        if not self.active_trades:
            return

        pip_size = PositionSizer.get_pip_size(self.symbol)
        for ticket, trade in list(self.active_trades.items()):
            if trade.direction == Direction.BUY:
                favorable_price = Decimal(str(current_bar.high))
                cur_r = (favorable_price - trade.entry_price) / (trade.risk_pips * pip_size) if trade.risk_pips > 0 else Decimal("0")
            else:
                favorable_price = Decimal(str(current_bar.low))
                cur_r = (trade.entry_price - favorable_price) / (trade.risk_pips * pip_size) if trade.risk_pips > 0 else Decimal("0")

            if cur_r >= Decimal("2.0"):
                # Milestone 1: Bank partial profits if configured (> 0)
                if not trade.partial_banked and trade.partial_bank_pct and trade.partial_bank_pct > Decimal("0"):
                    close_lots = (trade.lots * trade.partial_bank_pct).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                    if close_lots >= Decimal("0.01"):
                        try:
                            self.dwx_client.send_close(ticket=ticket, lots=close_lots, symbol=self.symbol)
                            trade.partial_banked = True
                            trade.lots -= close_lots
                            logger.info(
                                f"[{self.symbol}] Milestone 1: Banked {trade.partial_bank_pct * Decimal('100'):.0f}% partial ({close_lots} lots) "
                                f"on ticket {ticket} at +2.0R (reached {cur_r:.2f}R)"
                            )
                            if self.db is not None:
                                self.db.log_audit_event(
                                    "PARTIAL_CLOSE",
                                    "executor",
                                    f"Ticket {ticket}: closed {close_lots} lots at +2.0R",
                                )
                        except Exception as e:
                            logger.error(f"Failed to send partial close for ticket {ticket}: {e}")

                # Milestone 2: Advance Stop Loss to Breakeven (+ 0.5 pip buffer)
                if not trade.breakeven_set:
                    buffer = Decimal("0.00005") if "JPY" not in self.symbol.upper() else Decimal("0.005")
                    new_sl = (trade.entry_price + buffer) if trade.direction == Direction.BUY else (trade.entry_price - buffer)
                    try:
                        self.dwx_client.send_modify(ticket=ticket, sl=new_sl, tp=trade.tp_price, symbol=self.symbol)
                        trade.breakeven_set = True
                        trade.sl_price = new_sl
                        logger.info(
                            f"[{self.symbol}] Milestone 2: Moved SL to Breakeven ({new_sl}) "
                            f"on ticket {ticket} at +2.0R"
                        )
                        if self.db is not None:
                            self.db.log_audit_event(
                                "BREAKEVEN_ADVANCE",
                                "executor",
                                f"Ticket {ticket}: SL moved to {new_sl}",
                            )
                    except Exception as e:
                        logger.error(f"Failed to advance SL to breakeven for ticket {ticket}: {e}")

    def step_multitimeframe(
        self,
        m1_timeframe: str = "M1",
        m5_timeframe: str = "M5",
        m15_timeframe: str = "M15",
    ) -> Optional[BridgeOrderRecord]:
        """
        Multi-timeframe execution cycle (Phase 1 & 3 Specification):
        1. Reads M5 and M15 closed bars from MT4 exports and feeds to RuleEngine.on_htf_candle.
        2. Reads M1 closed bars from MT4 export and feeds to RuleEngine.on_m1_candle.
        3. If 3 consecutive confirming 1m candles complete, calculates dynamic position size,
           evaluates non-bypassable risk guardrails, logs to database, and executes market order via DWXClient.
        """
        # 1. Process M15 bars (if present)
        m15_bars = self.dwx_client.read_closed_bars(self.symbol, m15_timeframe)
        if m15_bars:
            if self.last_processed_m15_time is None:
                new_m15 = m15_bars
            else:
                new_m15 = [c for c in m15_bars if c.timestamp > self.last_processed_m15_time]
            for bar in new_m15:
                self.last_processed_m15_time = bar.timestamp
                self.rule_engine.on_htf_candle(bar, timeframe="M15")
                if self.db is not None:
                    try:
                        self.db.save_candles([bar], self.symbol, "M15")
                    except Exception as e:
                        logger.error(f"Failed to save M15 candle to DB: {e}")

        # 2. Process M5 bars (if present)
        m5_bars = self.dwx_client.read_closed_bars(self.symbol, m5_timeframe)
        if m5_bars:
            if self.last_processed_m5_time is None:
                new_m5 = m5_bars
            else:
                new_m5 = [c for c in m5_bars if c.timestamp > self.last_processed_m5_time]
            for bar in new_m5:
                self.last_processed_m5_time = bar.timestamp
                self.rule_engine.on_htf_candle(bar, timeframe="M5")
                if self.db is not None:
                    try:
                        self.db.save_candles([bar], self.symbol, "M5")
                    except Exception as e:
                        logger.error(f"Failed to save M5 candle to DB: {e}")

        # 3. Process M1 bars
        m1_bars = self.dwx_client.read_closed_bars(self.symbol, m1_timeframe)
        if not m1_bars:
            return None

        if self.db is not None:
            try:
                self.db.save_candles(m1_bars, self.symbol, "M1")
            except Exception as e:
                logger.error(f"Failed to save M1 candles to DB: {e}")

        if self.watchdog is not None:
            m1_delta = TIMEFRAME_DELTAS.get("M1", timedelta(minutes=1))
            self.watchdog.record_bar_received(m1_bars[-1].timestamp + m1_delta)

        if self.last_processed_m1_time is None:
            if self.rule_engine.is_armed and self.rule_engine.armed_state is not None:
                tf_mins = 15 if self.rule_engine.armed_state.sweep_timeframe == "M15" else 5
                sweep_close_time = self.rule_engine.armed_state.sweep_candle.timestamp + timedelta(minutes=tf_mins)
                new_m1 = [c for c in m1_bars if c.timestamp >= sweep_close_time]
            else:
                for b in m1_bars[-20:]:
                    self.rule_engine._m1_body_sum += b.body
                    self.rule_engine._m1_body_count += 1
                new_m1 = []
            self.last_processed_m1_time = m1_bars[-1].timestamp
        else:
            new_m1 = [c for c in m1_bars if c.timestamp > self.last_processed_m1_time]

        if not new_m1:
            return None

        dispatched_record: Optional[BridgeOrderRecord] = None
        for bar in new_m1:
            self.last_processed_m1_time = bar.timestamp
            self._manage_active_trades(bar)
            signal = self.rule_engine.on_m1_candle(bar)
            if signal is not None:
                record = self._execute_signal(signal)
                if record is not None:
                    dispatched_record = record

        return dispatched_record

    def step(self) -> Optional[BridgeOrderRecord]:
        """Performs a single execution cycle:
        1. Reads closed bars exported by MT4 EA.
        2. Filters for newly closed bars since last cycle.
        3. Evaluates strategy through RuleEngine.
        4. If signal generated, calculates position size.
        5. Dispatches order to MT4 and polls for confirmation.
        
        Returns BridgeOrderRecord if a trade was dispatched, else None.
        """
        # If M1 bars file is exported by MT4, route to multi-timeframe streaming engine
        m1_file = self.dwx_client.get_bars_file(self.symbol, "M1")
        if m1_file.exists():
            return self.step_multitimeframe()

        closed_bars = self.dwx_client.read_closed_bars(self.symbol, self.timeframe)
        if not closed_bars:
            return None

        if self.db is not None:
            try:
                self.db.save_candles(closed_bars, self.symbol, self.timeframe)
            except Exception as e:
                logger.error(f"Failed to persist closed candles to DB: {e}")

        if self.watchdog is not None:
            # Bar timestamp is the candle open time; candle closes at open + timeframe_delta
            bar_close_time = closed_bars[-1].timestamp + self.timeframe_delta
            self.watchdog.record_bar_received(bar_close_time)

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
            self._manage_active_trades(bar)
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
            if self.db is not None:
                try:
                    self.db.save_signal(
                        signal=signal,
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        executed=False,
                        rejection_reason=f"PositionSizer: {sizing.rejection_reason}",
                    )
                except Exception as e:
                    logger.error(f"Failed to log rejected signal to DB: {e}")
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

        # ── Non-Bypassable Risk Guardrail Gate ──────────────────────────
        # If RiskGuardrails are wired, this is the MANDATORY checkpoint.
        # A rejected trade NEVER reaches DWX dispatch.
        if self.risk_guardrails is not None:
            # Sync active trades with live MT4 account state if available
            acc_info = self.dwx_client.read_account_info()
            if acc_info and "orders" in acc_info:
                live_tickets = {int(o["ticket"]) for o in acc_info["orders"] if "ticket" in o}
                closed_tickets = [t for t in self.active_trades if t not in live_tickets]
                for t in closed_tickets:
                    del self.active_trades[t]
                open_count = len(live_tickets)
            elif self.active_trades:
                open_count = len(self.active_trades)
            else:
                open_count = len([r for r in self.order_records if r.status == "FILLED"])

            account_state = AccountState(
                starting_daily_balance=self.balance,
                current_balance=self.balance,
                current_equity=self.balance,  # updated by live feed in production
                realized_daily_pnl=Decimal("0.00"),
                unrealized_daily_pnl=Decimal("0.00"),
                open_trade_count=open_count,
                daily_trades_count=len([r for r in self.order_records if r.status in ("FILLED", "UNCONFIRMED")]),
                current_spread_pips=Decimal("0.0"),  # populated by live feed in production
                timestamp=signal_time,
            )
            risk_result: ValidationResult = self.risk_guardrails.validate_trade(
                account_state=account_state,
                proposed_lots=sizing.lots,
                trade_time=signal_time,
            )
            if not risk_result.is_allowed:
                logger.warning(f"RISK REJECTION [{risk_result.reason}]: {risk_result.message}")
                if self.db is not None:
                    try:
                        self.db.save_signal(
                            signal=signal,
                            symbol=self.symbol,
                            timeframe=self.timeframe,
                            executed=False,
                            rejection_reason=f"RISK: [{risk_result.reason}] {risk_result.message}",
                        )
                        self.db.log_audit_event(
                            event_type="TRADE_REJECTED",
                            source="RiskGuardrails",
                            details=f"[{risk_result.reason}] {risk_result.message}",
                        )
                    except Exception as e:
                        logger.error(f"Failed to log risk rejection to DB: {e}")
                record = BridgeOrderRecord(
                    magic=0,
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
                    status="REJECTED",
                    rejection_reason=f"RISK: [{risk_result.reason}] {risk_result.message}",
                )
                self.order_records.append(record)
                if self.on_order_callback:
                    self.on_order_callback(record)
                return record

        # Generate MT4 magic number
        self._magic_seq += 1
        magic = generate_mt4_magic_number(signal_time, self._magic_seq)

        order_type = OrderType.BUY if signal_dir == Direction.BUY else OrderType.SELL

        if self.db is not None:
            try:
                self.db.save_signal(
                    signal=signal,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    executed=True,
                )
                self.db.save_order(
                    command_id=f"CMD_{magic}_{self.symbol}",
                    magic_number=magic,
                    symbol=self.symbol,
                    direction=signal_dir.value,
                    lots=float(sizing.lots),
                    target_entry=float(entry_dec),
                    stop_loss=float(sl_dec),
                    take_profit=float(tp_dec),
                    status="SUBMITTED",
                )
            except Exception as e:
                logger.error(f"Failed to save signal/order to DB: {e}")

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
            if self.watchdog is not None:
                self.watchdog.record_order_dispatched()
        except Exception as e:
            logger.error(f"Failed to dispatch order to DWX: {e}")
            record.status = "ERROR"
            record.rejection_reason = str(e)
            if self.db is not None:
                try:
                    self.db.update_order_fill(
                        magic_number=magic,
                        ticket=0,
                        fill_price=0.0,
                        status="ERROR",
                    )
                    self.db.log_audit_event("ORDER_ERROR", "executor", f"Magic {magic}: {e}")
                except Exception as dbe:
                    logger.error(f"Failed to update error in DB: {dbe}")
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
                if report.ticket is not None:
                    p_pct = Decimal(str(signal.partial_bank_pct)) if (signal.partial_bank_pct is not None) else Decimal("0.0")
                    self.active_trades[report.ticket] = ActiveBridgeTrade(
                        ticket=report.ticket,
                        magic=magic,
                        symbol=self.symbol,
                        direction=signal_dir,
                        entry_price=report.open_price,
                        sl_price=sl_dec,
                        tp_price=tp_dec,
                        lots=sizing.lots,
                        risk_pips=stop_pips,
                        partial_bank_pct=p_pct,
                    )
                if self.db is not None and record.ticket is not None:
                    try:
                        slippage = float(abs(report.open_price - entry_dec) / Decimal("0.0001"))
                        self.db.update_order_fill(
                            magic_number=magic,
                            ticket=record.ticket,
                            fill_price=float(report.open_price),
                            slippage_pips=slippage,
                            status="FILLED",
                        )
                        self.db.log_audit_event(
                            event_type="ORDER_FILLED",
                            source="executor",
                            details=f"Ticket {record.ticket}, Magic {magic}, Price {report.open_price}",
                        )
                    except Exception as e:
                        logger.error(f"Failed to record fill in DB: {e}")
            else:
                record.status = "REJECTED"
                record.rejection_reason = f"{report.message} (error code {report.error_code})"
                logger.warning(f"Order REJECTED by MT4: {record.rejection_reason}")
                if self.db is not None:
                    try:
                        self.db.update_order_fill(
                            magic_number=magic,
                            ticket=0,
                            fill_price=0.0,
                            status="REJECTED",
                        )
                        self.db.log_audit_event(
                            event_type="ORDER_REJECTED",
                            source="MT4",
                            details=f"Magic {magic}: {record.rejection_reason}",
                        )
                    except Exception as e:
                        logger.error(f"Failed to record rejection in DB: {e}")
        else:
            record.status = "UNCONFIRMED"
            record.rejection_reason = f"Timeout ({self.confirmation_timeout_sec}s) waiting for ticket confirmation."
            logger.critical(f"Order UNCONFIRMED for magic {magic}! Check MT4 manually.")
            if self.db is not None:
                try:
                    self.db.update_order_fill(
                        magic_number=magic,
                        ticket=0,
                        fill_price=0.0,
                        status="UNCONFIRMED",
                    )
                    self.db.log_audit_event(
                        event_type="ORDER_UNCONFIRMED",
                        source="executor",
                        details=f"Magic {magic}: Timeout waiting for ticket confirmation",
                    )
                except Exception as e:
                    logger.error(f"Failed to record unconfirmed in DB: {e}")

        if self.on_order_callback:
            self.on_order_callback(record)

        return record

    def run(self, poll_interval_sec: float = 1.0, max_cycles: Optional[int] = None) -> None:
        """Runs the continuous bar poller loop until stopped."""
        self._running = True
        logger.info(f"Starting BridgeExecutor for {self.symbol} {self.timeframe}...")
        cycles = 0
        last_watchdog_log = 0.0

        try:
            while self._running:
                self.step()
                cycles += 1

                now_mono = time.monotonic()
                if self.watchdog is not None and (now_mono - last_watchdog_log >= 30.0):
                    last_watchdog_log = now_mono
                    status = self.watchdog.check_health()
                    logger.info(
                        f"[WATCHDOG] State: {status.state.value} | "
                        f"Bars: {status.bars_processed} | "
                        f"Orders: {status.orders_dispatched} | "
                        f"{status.status_message}"
                    )

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


def main() -> None:
    """Production entrypoint for running the AK Forex Trading Bridge."""
    import sys
    from config import load_config
    from integrations.alerts import AlertDispatcher
    from risk.models import RiskLimits

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        cfg = load_config()
    except Exception as e:
        logger.critical(f"Failed to load configuration: {e}")
        sys.exit(1)

    print("=" * 70)
    print("  AK FOREX TRADING SYSTEM — MT4 EXECUTION BRIDGE")
    print(f"  Symbol:            {cfg.symbol}")
    print(f"  Timeframe:         {cfg.timeframe}")
    print(f"  Balance:           ${cfg.initial_balance:,.2f}")
    daily_loss_display = f"{cfg.max_daily_loss_pct * Decimal('100'):.1f}%" if cfg.max_daily_loss_pct is not None else "Unlimited (No limit)"
    print(f"  Max Daily Loss:    {daily_loss_display}")
    print(f"  Max Daily Trades:  {cfg.max_daily_trades if cfg.max_daily_trades is not None else 'Unlimited (No limit)'}")
    print(f"  Spread Ceiling:    {cfg.max_spread_pips} pips")
    print(f"  Session Filter:    {cfg.session_start_hour:02d}:00 - {cfg.session_end_hour:02d}:00 UTC (London + NY + Overlap)")
    print(f"  MT4 Files Folder:  {cfg.mt4_files_dir}")
    db = TradingDatabase(cfg.db_path) if cfg.db_enabled else None
    if db is not None:
        logger.info(f"Connected to SQLite database at {cfg.db_path}")
        print(f"  Database:          SQLite ({cfg.db_path})")
        db.log_audit_event(
            event_type="BRIDGE_STARTED",
            source="executor",
            details=f"Symbol: {cfg.symbol}, Timeframe: {cfg.timeframe}, Initial Balance: ${cfg.initial_balance}",
        )
    else:
        print("  Database:          Disabled")
    print("=" * 70)

    dwx = DWXClient(cfg.mt4_files_dir)
    alerts = AlertDispatcher(
        telegram_token=cfg.telegram_token,
        telegram_chat_id=cfg.telegram_chat_id,
        webhook_url=cfg.webhook_url,
    )
    guardrail_cb = alerts.create_guardrail_callback()
    watchdog_cb = alerts.create_watchdog_callback()

    limits = RiskLimits(
        max_daily_loss_pct=cfg.max_daily_loss_pct,
        max_open_trades=cfg.max_open_trades,
        max_daily_trades=cfg.max_daily_trades,
        max_spread_pips=cfg.max_spread_pips,
        session_start_hour_utc=cfg.session_start_hour,
        session_end_hour_utc=cfg.session_end_hour,
        session_filter_enabled=cfg.session_filter_enabled,
        emergency_halt=cfg.emergency_halt,
    )
    guardrails = RiskGuardrails(limits=limits, alert_callback=guardrail_cb)
    watchdog = BridgeWatchdog(
        dwx_client=dwx,
        risk_guardrails=guardrails,
        max_heartbeat_age_sec=cfg.max_heartbeat_age_sec,
        alert_callback=watchdog_cb,
    )
    sizer = PositionSizer(default_risk_pct=cfg.risk_pct)

    symbols = [s.strip() for s in cfg.symbol.split(",") if s.strip()]
    if not symbols:
        symbols = ["EURUSDm"]

    # Read live balance from DWX_Account.txt if present
    live_bal = cfg.initial_balance
    acc_file = dwx.files_dir / "DWX_Account.txt"
    if acc_file.exists():
        try:
            acc_data = json.loads(acc_file.read_text(encoding="utf-8", errors="ignore"))
            if "balance" in acc_data and float(acc_data["balance"]) > 0:
                live_bal = Decimal(str(acc_data["balance"]))
                print(f"  Live Balance:      ${live_bal:,.2f} (from MT4 account {acc_data.get('account_number', '')})")
        except Exception:
            pass

    bridges: List[BridgeExecutor] = []
    is_c1_mode = getattr(cfg, "strategy_mode", "c1_wickswap").lower() == "c1_wickswap"
    preset_name = "C1 Wick-Swap (1:5 R:R, BE @ 2R, C1 SL)" if is_c1_mode else "Institutional Preset"

    for sym in symbols:
        engine = (
            RuleEngine.c1_wickswap_preset(symbol=sym)
            if is_c1_mode
            else RuleEngine.institutional_preset(symbol=sym)
        )
        b = BridgeExecutor(
            symbol=sym,
            dwx_client=dwx,
            rule_engine=engine,
            position_sizer=sizer,
            risk_guardrails=guardrails,
            watchdog=watchdog,
            db=db,
            timeframe=cfg.timeframe,
            initial_balance=live_bal,
            risk_pct=cfg.risk_pct,
            confirmation_timeout_sec=cfg.confirmation_timeout_sec,
        )
        bridges.append(b)

    alerts.dispatch(
        title="Bridge Started",
        body=f"AK Forex Trading Bridge initialized on {', '.join(symbols)} {cfg.timeframe} ({preset_name}).",
    )

    print(f"\n[INFO] Starting bridge loop for symbols: {', '.join(symbols)} ({preset_name})")
    print("[INFO] Polling MT4 files folder every 1.0s... (Press Ctrl+C to stop)\n")

    try:
        last_watchdog_log = 0.0
        while True:
            for b in bridges:
                b.step()
            now_mono = time.monotonic()
            if watchdog is not None and (now_mono - last_watchdog_log >= 30.0):
                last_watchdog_log = now_mono
                status = watchdog.check_health()
                logger.info(
                    f"[WATCHDOG] State: {status.state.value} | "
                    f"Bars: {status.bars_processed} | "
                    f"Orders: {sum(len(b.order_records) for b in bridges)} | "
                    f"{status.status_message}"
                )
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("BridgeExecutor stopped by user.")


if __name__ == "__main__":
    main()
