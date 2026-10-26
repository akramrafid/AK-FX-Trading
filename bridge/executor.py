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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from bridge.day_start import DayStartBalances
from bridge.dwx_client import (
    DWXClient,
    ExecutionReport,
    OrderType,
    TradeCommand,
    account_spread_pips,
    open_positions_by_side,
)
from bridge.sizing import (
    PositionSizer,
    SizingResult,
    calculate_r2_risk_amount,
    calculate_r3_quote_distance,
    calculate_r4_per_lot_loss,
    calculate_r5_lot_size,
    calculate_r8_realized_risk,
    format_r8_order_record,
    get_r4_tick_value,
    prepare_r6_order_prices,
    read_r1_account_balance,
    verify_r7_no_post_entry_modifications,
)
from bridge.watchdog import BridgeWatchdog
from config import (
    A1_ACCOUNT_CURRENCY,
    A2_COMMISSION_PER_LOT_ROUND_TURN,
    A3_RISK_BASIS_IS_BALANCE,
    A4_NO_POST_ENTRY_MODIFICATIONS,
    BALANCE_MAX_AGE_SECONDS,
    COMMISSION_PER_LOT_ROUND_TURN,
    LOT_ROUNDING,
    MIN_LOT_POLICY,
    RISK_BASIS,
    RISK_DEVIATION_TOLERANCE_PCT,
    RISK_PERCENT,
)
from database.sqlite_manager import TradingDatabase
from engine.models import Candle, Direction, TradeSignal
from engine.ak_scenarios import AkScenariosEngine, no_hedging_params
from engine.buy_scenarios import BuyScenarioEngine, BuyScenarioParams
from engine.rule_engine import RuleEngine
from engine.sell_scenarios import SellScenarioEngine, SellScenarioParams
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

# Strategy modes that exit at SL or TP only: no break-even, trailing or partial close.
SCENARIO_MODES = ("sell_scenarios", "buy_scenarios", "ak_scenarios")
# The EA rewrites DWX_Account.txt every second, so a read can catch it half-written: read it again shortly.
SNAPSHOT_READ_ATTEMPTS = 3
SNAPSHOT_RETRY_SECONDS = 0.05
# An order this bridge sent counts as open on its side until the EA's order list shows it.
RECENT_ORDER_SECONDS = 60.0


def _account_value(acc_info: Any, key: str) -> Optional[Decimal]:
    """A positive balance or equity figure from the account snapshot the EA writes, or None."""
    if not isinstance(acc_info, dict):
        return None
    try:
        value = Decimal(str(acc_info[key]))
    except (KeyError, ArithmeticError, ValueError, TypeError):
        return None
    return value if value.is_finite() and value > 0 else None


def _account_id(acc_info: Any) -> str:
    """The MT4 account number in the EA's account snapshot, or "" when it is missing."""
    return str(acc_info.get("account_number", "")).strip() if isinstance(acc_info, dict) else ""


def generate_mt4_magic_number(dt: datetime, sequence: int = 1) -> int:
    """Generates a deterministic 32-bit signed integer magic number for MT4.
    
    MT4 Magic Numbers are 32-bit signed integers (max 2,147,483,647).
    To prevent integer overflow while maintaining uniqueness:
    Formula: (Month*10000000 + Day*100000 + Hour*1000 + Minute*10 + sequence) % 2000000000
    Example: Sept 24, 03:25 -> 09*10000000 + 24*100000 + 03*1000 + 25*10 + 1 = 92,403,251 (< 2.14B).
    """
    base = (dt.month * 10_000_000) + (dt.day * 100_000) + (dt.hour * 1000) + (dt.minute * 10) + (sequence % 10)
    return int(base % 2_000_000_000)


def _journal_sink(
    db: Optional[TradingDatabase], symbol: str, source: str, prefix: str
) -> Optional[Callable[[Dict[str, Any]], None]]:
    """audit_logs writer for a scenario engine: <prefix>_SIGNAL, <prefix>_SKIPPED, or the record's own event."""
    if db is None:
        return None

    def sink(record: Dict[str, Any]) -> None:
        event = {"SIGNAL": f"{prefix}_SIGNAL", "SKIPPED": f"{prefix}_SKIPPED"}.get(record["event"], record["event"])
        db.log_audit_event(event, source, {"symbol": symbol, **record})

    return sink


def build_sell_scenario_engine(cfg: Any, symbol: str, db: Optional[TradingDatabase] = None) -> SellScenarioEngine:
    """Sell Scenarios engine for the live bridge (STRATEGY_MODE=sell_scenarios).

    The session and open-position limit come from the same AppConfig as the risk guardrails.
    Every signal and skipped signal is journaled to audit_logs (plan.md §3.9).
    """
    return SellScenarioEngine(
        params=SellScenarioParams.from_app_config(cfg, symbol),
        symbol=symbol,
        event_sink=_journal_sink(db, symbol, "sell_scenarios", "SELL_SCENARIO"),
    )


def build_buy_scenario_engine(cfg: Any, symbol: str, db: Optional[TradingDatabase] = None) -> BuyScenarioEngine:
    """Buy Scenarios engine for the live bridge (STRATEGY_MODE=buy_scenarios).

    The session and open-position limit come from the same AppConfig as the risk guardrails.
    Every signal and skipped signal is journaled to audit_logs (plan.md §3.9).
    """
    return BuyScenarioEngine(
        params=BuyScenarioParams.from_app_config(cfg, symbol),
        symbol=symbol,
        event_sink=_journal_sink(db, symbol, "buy_scenarios", "BUY_SCENARIO"),
    )


def build_ak_scenarios_engine(cfg: Any, symbol: str, db: Optional[TradingDatabase] = None) -> AkScenariosEngine:
    """Sell and buy scenarios together for the live bridge (STRATEGY_MODE=ak_scenarios).

    Never a buy and a sell open at once: the BridgeExecutor that runs the engine counts the open
    positions by side (open_positions_by_side), and while they are unknown neither side trades.
    A sell and a buy on the same bar are journaled as SAME_BAR_CONFLICT and neither is sent.
    """
    sell = SellScenarioEngine(
        params=no_hedging_params(SellScenarioParams.from_app_config(cfg, symbol)),
        symbol=symbol,
        event_sink=_journal_sink(db, symbol, "sell_scenarios", "SELL_SCENARIO"),
    )
    buy = BuyScenarioEngine(
        params=no_hedging_params(BuyScenarioParams.from_app_config(cfg, symbol)),
        symbol=symbol,
        event_sink=_journal_sink(db, symbol, "buy_scenarios", "BUY_SCENARIO"),
    )
    return AkScenariosEngine(sell=sell, buy=buy, event_sink=_journal_sink(db, symbol, "ak_scenarios", "AK_SCENARIOS"))


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
    breakeven_trigger_r: Optional[Decimal] = Decimal("2.0")


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
    r8_record: Optional[Dict[str, Any]] = None


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
        risk_pct: Decimal = Decimal("0.01"),
        confirmation_timeout_sec: float = 10.0,
        exchange_rates: Optional[Dict[str, Decimal]] = None,
        on_signal_callback: Optional[Callable[[TradeSignal], None]] = None,
        on_order_callback: Optional[Callable[[BridgeOrderRecord], None]] = None,
        risk_percent: Decimal = Decimal(str(RISK_PERCENT)),
        commission_per_lot_round_turn: Decimal = Decimal(str(COMMISSION_PER_LOT_ROUND_TURN)),
        balance_max_age_seconds: float = BALANCE_MAX_AGE_SECONDS,
        risk_deviation_tolerance_pct: float = RISK_DEVIATION_TOLERANCE_PCT,
        allow_post_entry_modifications: bool = False,
        exact_risk_sizing: Optional[bool] = None,
    ) -> None:
        self.symbol = symbol.strip().replace("/", "")
        self.dwx_client = dwx_client
        self.timeframe = timeframe.upper()
        self.timeframe_delta = TIMEFRAME_DELTAS.get(self.timeframe, timedelta(minutes=5))
        self.balance = initial_balance
        self.risk_pct = risk_pct
        self.confirmation_timeout_sec = confirmation_timeout_sec
        self.exchange_rates = exchange_rates or {}

        # Exact 1% Risk Sizing Config
        self.risk_percent = risk_percent
        self.commission_per_lot_round_turn = commission_per_lot_round_turn
        self.balance_max_age_seconds = balance_max_age_seconds
        self.risk_deviation_tolerance_pct = risk_deviation_tolerance_pct
        self.allow_post_entry_modifications = allow_post_entry_modifications
        self.exact_risk_sizing = (
            exact_risk_sizing
            if exact_risk_sizing is not None
            else self.symbol.upper().startswith("USDCAD")
        )

        # Core Rule Engine (strictly shared between backtester & live bridge)
        self.rule_engine = rule_engine or RuleEngine(swing_lookback=20)
        # ak_scenarios' no-hedging rule counts open positions through this bridge (MT4's list + its own orders).
        if getattr(self.rule_engine, "position_counter", False) is None:
            self.rule_engine.position_counter = self.open_positions_by_side
        self.position_sizer = position_sizer or PositionSizer(default_risk_pct=risk_pct)
        self.min_lot = getattr(self.position_sizer, "min_lot", Decimal("0.01"))
        self.max_lot = getattr(self.position_sizer, "max_lot", Decimal("50.00"))
        self.lot_step = getattr(self.position_sizer, "lot_step", Decimal("0.01"))
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
        self._day_starts = DayStartBalances(db)  # the daily loss limit's baseline
        self._running = False
        self._magic_seq = 0


    def _manage_active_trades(self, current_bar: Candle) -> None:
        """[R7] No changes after entry.
        The strategy has no break-even, trailing, partial close or early close.
        A position ends only by its SL or TP. [A4]
        If allow_post_entry_modifications is False (default under R7 & A4), this is a no-op.
        """
        if not self.allow_post_entry_modifications:
            return

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

            be_target_r = trade.breakeven_trigger_r if trade.breakeven_trigger_r is not None else Decimal("2.0")
            if cur_r >= be_target_r:
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
                                f"on ticket {ticket} at 1:2 RR (reached {cur_r:.2f}R)"
                            )
                            if self.db is not None:
                                self.db.log_audit_event(
                                    "PARTIAL_CLOSE",
                                    "executor",
                                    f"Ticket {ticket}: closed {close_lots} lots at 1:2 RR",
                                )
                        except Exception as e:
                            logger.error(f"Failed to send partial close for ticket {ticket}: {e}")

                # Milestone 2: Advance Stop Loss strictly to Entry (Breakeven)
                if not trade.breakeven_set:
                    new_sl = trade.entry_price
                    try:
                        self.dwx_client.send_modify(ticket=ticket, sl=new_sl, tp=trade.tp_price, symbol=self.symbol)
                        trade.breakeven_set = True
                        trade.sl_price = new_sl
                        logger.info(
                            f"[{self.symbol}] Milestone 2: Moved SL strictly to Entry ({new_sl}) "
                            f"on ticket {ticket} at 1:2 RR (reached {cur_r:.2f}R)"
                        )
                        if self.db is not None:
                            self.db.log_audit_event(
                                "BREAKEVEN_ADVANCE",
                                "executor",
                                f"Ticket {ticket}: SL moved to entry {new_sl}",
                            )
                    except Exception as e:
                        logger.error(f"Failed to advance SL to entry for ticket {ticket}: {e}")

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
        # 0. Sync live spread from DWX account info if available
        acc_info = self.dwx_client.read_account_info()
        self._note_day_start(acc_info)
        if isinstance(acc_info, dict):
            live_spread = None
            if "pairs" in acc_info and isinstance(acc_info["pairs"], dict) and self.symbol in acc_info["pairs"]:
                pair_data = acc_info["pairs"][self.symbol]
                if isinstance(pair_data, dict) and "spread_pips" in pair_data:
                    try:
                        live_spread = float(pair_data["spread_pips"])
                    except (ValueError, TypeError):
                        pass
            elif "spread_pips" in acc_info:
                try:
                    live_spread = float(acc_info["spread_pips"])
                except (ValueError, TypeError):
                    pass
            if live_spread is not None and live_spread > 0:
                self.rule_engine.spread_pips = live_spread

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
            for b in m1_bars[-20:]:
                self.rule_engine._m1_body_sum += b.body
                self.rule_engine._m1_body_count += 1
            self.last_processed_m1_time = m1_bars[-1].timestamp
            return None

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

        self._note_day_start(self.dwx_client.read_account_info())
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

    def _note_day_start(self, acc_info: Any) -> None:
        """Record the day's starting balance at the first account reading of each UTC day."""
        balance = _account_value(acc_info, "balance")
        if balance is not None:
            self._day_starts.balance_at_start(balance, _account_id(acc_info))

    def _account_snapshot(self, fresh: bool = False) -> Any:
        """The EA's account snapshot, read again when caught half-written; with fresh=True, None when stale."""
        if fresh:
            try:
                if time.time() - self.dwx_client.account_file.stat().st_mtime > self.balance_max_age_seconds:
                    return None
            except (OSError, TypeError, ValueError):
                return None
        acc_info = self.dwx_client.read_account_info()
        for _ in range(SNAPSHOT_READ_ATTEMPTS - 1):
            if isinstance(acc_info, dict):
                break
            time.sleep(SNAPSHOT_RETRY_SECONDS)
            acc_info = self.dwx_client.read_account_info()
        return acc_info

    def open_positions_by_side(self) -> Optional[Tuple[int, int]]:
        """(buys, sells) open on this symbol for ak_scenarios' no-hedging rule; None when unknown.

        A fresh DWX_Account.txt order list, plus the orders this bridge sent in the last
        RECENT_ORDER_SECONDS that the list does not show yet (the EA rewrites it about once a second).
        """
        acc_info = self._account_snapshot(fresh=True)
        counts = open_positions_by_side(acc_info, self.symbol)
        if counts is None:
            return None
        listed = {o["ticket"] for o in acc_info["orders"] if isinstance(o, dict) and "ticket" in o}
        since = datetime.now(timezone.utc) - timedelta(seconds=RECENT_ORDER_SECONDS)
        unlisted = [
            r.direction
            for r in self.order_records
            if r.status in ("PENDING", "FILLED", "UNCONFIRMED") and r.dispatched_at >= since and r.ticket not in listed
        ]
        return counts[0] + unlisted.count(Direction.BUY), counts[1] + unlisted.count(Direction.SELL)

    def _reject_signal(
        self,
        signal: TradeSignal,
        signal_key: str,
        signal_dir: Direction,
        entry: Decimal,
        sl: Decimal,
        tp: Decimal,
        reason: str,
    ) -> BridgeOrderRecord:
        """Records a signal that sends no order: journal row, REJECTED order record and callback."""
        if self.db is not None:
            try:
                self.db.save_signal(
                    signal=signal,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    executed=False,
                    rejection_reason=reason,
                )
            except Exception as e:
                logger.error(f"Failed to log rejected signal to DB: {e}")
        record = BridgeOrderRecord(
            magic=0,
            signal_id=signal_key,
            symbol=self.symbol,
            direction=signal_dir,
            lots=Decimal("0.00"),
            entry_price=entry,
            sl_price=sl,
            tp_price=tp,
            risk_pips=Decimal("0.0"),
            reward_pips=Decimal("0.0"),
            dispatched_at=datetime.now(timezone.utc),
            status="REJECTED",
            rejection_reason=reason,
        )
        self.order_records.append(record)
        if self.on_order_callback:
            self.on_order_callback(record)
        return record

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
        if not self.exact_risk_sizing:
            # Legacy sizing path for non-USDCAD symbols / backward compatibility
            acc_info = self.dwx_client.read_account_info()
            if isinstance(acc_info, dict) and "balance" in acc_info:
                try:
                    live_bal = Decimal(str(acc_info["balance"]))
                    if live_bal > Decimal("0"):
                        self.balance = live_bal
                except Exception as e:
                    logger.debug(f"Could not parse live balance from acc_info: {e}")

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

            lots_sent = sizing.lots
            final_sl = sl_dec
            final_tp = tp_dec
            distance = signal.risk_distance
            live_quote = entry_dec
            lots_raw = lots_sent
            achieved_risk_pct = self.risk_pct * Decimal("100")
            balance_read = self.balance
            balance_ts = datetime.now(timezone.utc)
            tick_size = Decimal("0.00001") if "JPY" not in self.symbol.upper() else Decimal("0.001")
            tick_value = Decimal("1.00")
            per_lot_loss = Decimal("0.00")
            risk_amount = self.balance * self.risk_pct
        else:
            # [R1] Read current account balance from MT4 now (not equity, not free margin, not cached).
            # If it cannot be read, is <= 0, or is older than 5 seconds, send no order.
            balance_read, balance_ts, bal_err = read_r1_account_balance(
                self.dwx_client.account_file,
                max_age_seconds=self.balance_max_age_seconds,
            )
            if bal_err is not None:
                logger.error(f"[R1] Cannot read fresh balance from MT4: {bal_err}. Sending no order.")
                record = BridgeOrderRecord(
                    magic=0,
                    signal_id=signal_key,
                    symbol=self.symbol,
                    direction=signal_dir,
                    lots=Decimal("0.00"),
                    entry_price=entry_dec,
                    sl_price=sl_dec,
                    tp_price=tp_dec,
                    risk_pips=Decimal("0.0"),
                    reward_pips=Decimal("0.0"),
                    dispatched_at=datetime.now(timezone.utc),
                    status="REJECTED",
                    rejection_reason=f"R1_BALANCE_REJECTED: {bal_err}",
                )
                self.order_records.append(record)
                if self.on_order_callback:
                    self.on_order_callback(record)
                return record

            self.balance = balance_read

            # [R2] Risk amount = balance * 1.0 / 100
            risk_amount = calculate_r2_risk_amount(balance_read, self.risk_percent)

            # [R3] Price used for sizing: live quote at moment of sending (Ask for BUY, Bid for SELL).
            # distance = |quote - SL|. Spread is inherent in live quote.
            live_quote: Optional[Decimal] = None
            quotes = self.dwx_client.read_market_quote(self.symbol)
            # Sell and buy scenarios price the TP from the fill, so they need the live quote the EA writes
            # to DWX_Account.txt; without a fresh one nothing is sent.
            tp_from_quote = bool(getattr(self.rule_engine, "tp_from_fill", False))
            if tp_from_quote:
                quotes = self.dwx_client.read_account_quote(self.symbol, self.balance_max_age_seconds) or quotes
                if quotes is None:
                    logger.warning(f"[{self.symbol}] No fresh live quote from MT4. Sending no order.")
                    return self._reject_signal(signal, signal_key, signal_dir, entry_dec, sl_dec, tp_dec, "NO_LIVE_QUOTE")
            if quotes is not None:
                bid, ask = quotes
                live_quote = ask if signal_dir == Direction.BUY else bid
            if live_quote is None:
                live_quote = entry_dec

            _quote_dec, distance = calculate_r3_quote_distance(live_quote, sl_dec)

            # MT4 rejects a sell whose SL is not above the ask and a buy whose SL is not below the bid,
            # so such a signal sends nothing.
            if tp_from_quote and signal_dir == Direction.SELL and quotes[1] >= sl_dec:
                logger.warning(f"[{self.symbol}] Ask {quotes[1]} is at or above SL {sl_dec}. Sending no order.")
                return self._reject_signal(signal, signal_key, signal_dir, entry_dec, sl_dec, tp_dec, "SL_NOT_ABOVE_ASK")
            if tp_from_quote and signal_dir == Direction.BUY and quotes[0] <= sl_dec:
                logger.warning(f"[{self.symbol}] Bid {quotes[0]} is at or below SL {sl_dec}. Sending no order.")
                return self._reject_signal(signal, signal_key, signal_dir, entry_dec, sl_dec, tp_dec, "SL_NOT_BELOW_BID")

            # [R4] Tick size, tick value, and per-lot loss at the stop
            # per_lot_loss = (distance / tick_size) * tick_value + COMMISSION_PER_LOT_ROUND_TURN ($7.00/lot)
            tick_size = Decimal("0.00001") if "JPY" not in self.symbol.upper() else Decimal("0.001")
            tick_value = get_r4_tick_value(
                symbol=self.symbol,
                current_price=live_quote,
                contract_size=Decimal("100000"),
                tick_size=tick_size,
            )
            per_lot_loss = calculate_r4_per_lot_loss(
                distance=distance,
                tick_size=tick_size,
                tick_value=tick_value,
                commission_per_lot=self.commission_per_lot_round_turn,
            )

            # [R5] lots_raw = risk_amount / per_lot_loss. Round down to lot_step, never round() or ceil.
            # If below min_lot, skip trade and log MIN_LOT_EXCEEDS_RISK.
            lots_sent, lots_raw, achieved_risk_pct, r5_status = calculate_r5_lot_size(
                risk_amount=risk_amount,
                per_lot_loss=per_lot_loss,
                lot_step=self.lot_step,
                min_lot=self.min_lot,
                max_lot=self.max_lot,
                balance=balance_read,
            )

            if r5_status == "MIN_LOT_EXCEEDS_RISK":
                logger.warning(
                    f"[R5] MIN_LOT_EXCEEDS_RISK: lots_raw {lots_raw} is below min_lot {self.min_lot}. "
                    f"Skipping trade without raising lot size."
                )
                record = BridgeOrderRecord(
                    magic=0,
                    signal_id=signal_key,
                    symbol=self.symbol,
                    direction=signal_dir,
                    lots=Decimal("0.00"),
                    entry_price=entry_dec,
                    sl_price=sl_dec,
                    tp_price=tp_dec,
                    risk_pips=self.position_sizer.price_diff_to_pips(self.symbol, distance),
                    reward_pips=self.position_sizer.price_diff_to_pips(self.symbol, signal.reward_distance),
                    dispatched_at=datetime.now(timezone.utc),
                    status="REJECTED",
                    rejection_reason="MIN_LOT_EXCEEDS_RISK",
                )
                self.order_records.append(record)
                if self.on_order_callback:
                    self.on_order_callback(record)
                return record
            elif r5_status == "MAX_LOT_CAPPED":
                logger.info(f"[R5] Lots capped at max_lot {self.max_lot} (raw: {lots_raw})")

            # [R6] Send once, complete. Market order with SL and TP attached in the same request.
            # Prices rounded to symbol digits. TP follows strategy (or 10x SL distance).
            _q_final, final_sl, final_tp = prepare_r6_order_prices(
                quote=live_quote,
                sl=sl_dec,
                direction=signal_dir,
                rr_multiple=getattr(self.rule_engine, "reward_risk_ratio", 10),
                digits=5 if "JPY" not in self.symbol.upper() else 3,
                strategy_tp=None if tp_from_quote else tp_dec,
            )

        # ── Non-Bypassable Risk Guardrail Gate ──────────────────────────
        if self.risk_guardrails is not None:
            acc_info = self._account_snapshot()
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

            # Daily loss = closed P&L since the day's first balance reading + the open trades' floating P&L.
            balance_now = _account_value(acc_info, "balance")
            equity_now = _account_value(acc_info, "equity")
            live_spread = account_spread_pips(acc_info, self.symbol)
            if balance_now is None or equity_now is None or live_spread is None:
                if self.exact_risk_sizing:
                    logger.error(f"[{self.symbol}] No complete account snapshot for the guardrails. Sending no order.")
                    return self._reject_signal(
                        signal, signal_key, signal_dir, entry_dec, sl_dec, tp_dec, "ACCOUNT_SNAPSHOT_UNREADABLE"
                    )
                # Legacy sizing path: what the snapshot gives, otherwise the cached balance and no spread.
                balance_now = balance_now or self.balance
                equity_now = equity_now or balance_now
                live_spread = live_spread if live_spread is not None else Decimal("0.0")
            day_start = self._day_starts.balance_at_start(balance_now, _account_id(acc_info))
            account_state = AccountState(
                starting_daily_balance=day_start,
                current_balance=balance_now,
                current_equity=equity_now,
                realized_daily_pnl=balance_now - day_start,
                unrealized_daily_pnl=equity_now - balance_now,
                open_trade_count=open_count,
                daily_trades_count=len([r for r in self.order_records if r.status in ("FILLED", "UNCONFIRMED")]),
                current_spread_pips=live_spread,
                timestamp=signal_time,
            )
            risk_result: ValidationResult = self.risk_guardrails.validate_trade(
                account_state=account_state,
                proposed_lots=lots_sent,
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
                    lots=lots_sent,
                    entry_price=entry_dec,
                    sl_price=sl_dec,
                    tp_price=tp_dec,
                    risk_pips=self.position_sizer.price_diff_to_pips(self.symbol, distance),
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
                    lots=float(lots_sent),
                    target_entry=float(entry_dec),
                    stop_loss=float(final_sl),
                    take_profit=float(final_tp),
                    status="SUBMITTED",
                )
            except Exception as e:
                logger.error(f"Failed to save signal/order to DB: {e}")

        stop_pips = self.position_sizer.price_diff_to_pips(self.symbol, distance)
        reward_pips = self.position_sizer.price_diff_to_pips(self.symbol, abs(final_tp - live_quote))

        record = BridgeOrderRecord(
            magic=magic,
            signal_id=signal_key,
            symbol=self.symbol,
            direction=signal_dir,
            lots=lots_sent,
            entry_price=entry_dec,
            sl_price=final_sl,
            tp_price=final_tp,
            risk_pips=stop_pips,
            reward_pips=reward_pips,
            dispatched_at=datetime.now(timezone.utc),
            status="PENDING",
        )
        self.order_records.append(record)

        # Dispatch command via DWX Client
        try:
            self.dwx_client.send_order(
                symbol=self.symbol,
                order_type=order_type,
                lots=lots_sent,
                sl=final_sl,
                tp=final_tp,
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

        actual_fill_price: Optional[Decimal] = None
        ticket_val: Optional[int] = None

        if report is not None:
            if report.status in ("FILLED", "OPEN"):
                record.status = "FILLED"
                record.ticket = report.ticket
                record.fill_price = report.open_price
                record.confirmed_at = report.timestamp
                actual_fill_price = report.open_price
                ticket_val = report.ticket
                logger.info(f"Order FILLED: Ticket {record.ticket} at {record.fill_price}")

                if report.ticket is not None:
                    # [R7] Record active trade, but modifications are forbidden by default
                    self.active_trades[report.ticket] = ActiveBridgeTrade(
                        ticket=report.ticket,
                        magic=magic,
                        symbol=self.symbol,
                        direction=signal_dir,
                        entry_price=report.open_price,
                        sl_price=final_sl,
                        tp_price=final_tp,
                        lots=lots_sent,
                        risk_pips=stop_pips,
                        partial_bank_pct=Decimal("0.0"),
                        breakeven_trigger_r=Decimal("0.0"),
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

        # [R8] Comprehensive Order & Risk Audit Logging
        if self.exact_risk_sizing:
            expected_loss_sl = (per_lot_loss * lots_sent).quantize(Decimal("0.01"))
            reward_dist = abs(final_tp - live_quote)
            profit_per_lot_tp = (reward_dist / tick_size) * tick_value - self.commission_per_lot_round_turn
            expected_profit_tp = (profit_per_lot_tp * lots_sent).quantize(Decimal("0.01"))
            price_rr = (reward_dist / distance).quantize(Decimal("0.01")) if distance > Decimal("0") else Decimal("0.00")
            net_dollar_rr = (expected_profit_tp / expected_loss_sl).quantize(Decimal("0.01")) if expected_loss_sl > Decimal("0") else Decimal("0.00")

            realized_risk_pct = None
            dev_pct = None
            dev_flag = False
            dev_cause = None

            if actual_fill_price is not None:
                realized_risk_pct, dev_pct, dev_flag, dev_cause = calculate_r8_realized_risk(
                    balance=balance_read,
                    fill_price=actual_fill_price,
                    sl=final_sl,
                    direction=signal.direction,
                    lots_sent=lots_sent,
                    tick_size=tick_size,
                    tick_value=tick_value,
                    commission_rate=self.commission_per_lot_round_turn,
                    planned_risk_pct=achieved_risk_pct if achieved_risk_pct > Decimal("0") else self.risk_percent,
                    tolerance_pct=self.risk_deviation_tolerance_pct,
                    quote=live_quote,
                )
                if dev_flag:
                    logger.warning(
                        f"[R8 RISK_DEVIATION] Realized risk {realized_risk_pct}% deviated by {dev_pct}% "
                        f"from planned {self.risk_percent}% (> {self.risk_deviation_tolerance_pct}%). Cause: {dev_cause}"
                    )

            r8_record = format_r8_order_record(
                balance=balance_read,
                balance_timestamp=balance_ts,
                risk_amount=risk_amount,
                quote=live_quote,
                sl=final_sl,
                tp=final_tp,
                distance=distance,
                tick_size=tick_size,
                tick_value=tick_value,
                commission_rate=self.commission_per_lot_round_turn,
                lots_raw=lots_raw,
                lots_sent=lots_sent,
                expected_loss_sl=expected_loss_sl,
                expected_profit_tp=expected_profit_tp,
                price_rr=price_rr,
                net_dollar_rr=net_dollar_rr,
                ticket=ticket_val,
                actual_fill_price=actual_fill_price,
                realized_risk_pct=realized_risk_pct,
                risk_deviation=dev_cause,
            )
            record.r8_record = r8_record

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
        symbols = ["USDCADm"]

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
    mode_str = getattr(cfg, "strategy_mode", "strict_compliance").lower()
    if mode_str == "strict_compliance":
        preset_name = "Strict Compliance (1:10 R:R, 100% AK Rules [S1-S6/B1-B6])"
    elif mode_str == "c1_wickswap":
        preset_name = "C1 Wick-Swap (1:5 R:R, BE @ 2R, C1 SL)"
    elif mode_str == "sell_scenarios":
        preset_name = "Sell Scenarios 1-4 (1m entry on M5/M15 setup, 1:10 R:R, SL/TP only)"
    elif mode_str == "buy_scenarios":
        preset_name = "Buy Scenarios 1-2 (1m 3-run on M5/M15 setup, 1:10 R:R, SL/TP only)"
    elif mode_str == "ak_scenarios":
        preset_name = "AK Scenarios: Sell 1-4 + Buy 1-2, no hedging (1:10 R:R, SL/TP only)"
    else:
        preset_name = "Institutional Preset"

    for sym in symbols:
        if mode_str == "strict_compliance":
            engine = RuleEngine.strict_compliance_preset(
                symbol=sym,
                check_m5=True,
                check_m15=True,
            )
        elif mode_str == "c1_wickswap":
            engine = RuleEngine.c1_wickswap_preset(
                symbol=sym,
                check_m5=True,
                check_m15=True,
                session_filter=cfg.session_filter_enabled,
                session_start_hour=cfg.session_start_hour,
                session_end_hour=cfg.session_end_hour,
                spread_pips=float(getattr(cfg, "max_spread_pips", 1.8)),
                enable_intrabar_sweep=getattr(cfg, "enable_intrabar_sweep", True),
            )
        elif mode_str == "sell_scenarios":
            engine = build_sell_scenario_engine(cfg, sym, db)
        elif mode_str == "buy_scenarios":
            engine = build_buy_scenario_engine(cfg, sym, db)
        elif mode_str == "ak_scenarios":
            engine = build_ak_scenarios_engine(cfg, sym, db)
        else:
            engine = RuleEngine.institutional_preset(
                symbol=sym,
                check_m5=True,
                check_m15=True,
                session_filter=cfg.session_filter_enabled,
                session_start_hour=cfg.session_start_hour,
                session_end_hour=cfg.session_end_hour,
                enable_intrabar_sweep=getattr(cfg, "enable_intrabar_sweep", True),
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
            balance_max_age_seconds=getattr(cfg, "balance_max_age_seconds", BALANCE_MAX_AGE_SECONDS),
            risk_percent=Decimal(str(getattr(cfg, "risk_percent", RISK_PERCENT))),
            commission_per_lot_round_turn=Decimal(str(getattr(cfg, "commission_per_lot_round_turn", COMMISSION_PER_LOT_ROUND_TURN))),
            risk_deviation_tolerance_pct=getattr(cfg, "risk_deviation_tolerance_pct", RISK_DEVIATION_TOLERANCE_PCT),
            allow_post_entry_modifications=(
                False if mode_str in SCENARIO_MODES else getattr(cfg, "allow_post_entry_modifications", False)
            ),
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
