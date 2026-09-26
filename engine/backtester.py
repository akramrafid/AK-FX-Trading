"""
Event-Driven Backtest Simulator.

Uses the exact same RuleEngine from Phase 1 to guarantee zero code drift between
backtesting, forward testing, and live execution.
Models spread, slippage, dynamic position sizing, and position lifecycle without lookahead bias.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from engine.models import Candle, Direction, TradeSignal
from engine.rule_engine import RuleEngine, resample_m1_to_htf


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration parameters for backtesting execution."""
    initial_balance: float = 10000.0
    risk_pct: float = 1.0                  # Risk 1.0% of balance per trade
    spread_pips: float = 1.0               # Standard major pair spread in pips
    slippage_pips: float = 0.5             # Estimated execution slippage in pips
    pip_size: float = 0.0001               # 0.0001 for 4/5 digit pairs, 0.01 for JPY
    pip_value_per_lot: float = 10.0        # USD per pip for 1.0 standard lot on EUR/USD
    max_concurrent_trades: int = 1         # Position concurrency limit
    min_lot: float = 0.01
    max_lot: float = 50.0
    assume_worst_case_intrabar: bool = True # If bar touches both SL and TP, assume SL hit first


@dataclass
class BacktestTrade:
    """Record of an individual executed trade in the backtest."""
    trade_id: int
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    lots: float
    pnl_currency: float
    pnl_pips: float
    realized_r: float
    exit_reason: str                       # 'TP', 'SL', 'END_OF_DATA'
    bars_held: int


@dataclass
class BacktestResult:
    """Aggregated output of a backtest run."""
    config: BacktestConfig
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    initial_balance: float = 10000.0
    final_balance: float = 10000.0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> List[BacktestTrade]:
        return [t for t in self.trades if t.realized_r > 0]

    @property
    def losing_trades(self) -> List[BacktestTrade]:
        return [t for t in self.trades if t.realized_r <= 0]

    def save_to_database(self, db: any, symbol: str = "EURUSD", environment: str = "BACKTEST") -> int:
        """Persists all backtest trades to TradingDatabase trade_journal table.
        
        Enforces rule: 'Log every trade from the first test run, not just once live.
        This becomes the training data for any future ML/RL layer.'
        """
        count = 0
        for trade in self.trades:
            db.record_closed_trade(
                ticket=trade.trade_id,
                magic_number=100000 + (trade.trade_id % 900000),
                symbol=symbol,
                direction=trade.direction,
                open_time=trade.entry_time.isoformat(),
                close_time=trade.exit_time.isoformat(),
                open_price=trade.entry_price,
                close_price=trade.exit_price,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                lots=trade.lots,
                realized_pnl=trade.pnl_currency,
                exit_reason=trade.exit_reason,
                environment=environment,
            )
            count += 1
        return count


class BacktestEngine:
    """
    Event-driven bar-by-bar backtesting simulator.
    """

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        self.config = config or BacktestConfig()
        self.rule_engine = RuleEngine(spread_pips=self.config.spread_pips)

    def calculate_lot_size(self, balance: float, risk_distance: float) -> float:
        """
        Dynamically calculate position lot size strictly adhering to Hard Rule 3.
        lot_size = (balance * risk_pct) / (risk_pips * pip_value_per_lot)
        """
        if risk_distance <= 0 or self.config.pip_size <= 0:
            return self.config.min_lot

        risk_pips = risk_distance / self.config.pip_size
        risk_cash = balance * (self.config.risk_pct / 100.0)

        cost_per_lot = risk_pips * self.config.pip_value_per_lot
        if cost_per_lot <= 0:
            return self.config.min_lot

        raw_lot = risk_cash / cost_per_lot
        # Round to 2 decimal places (standard broker lot step 0.01)
        rounded_lot = round(raw_lot, 2)
        # Apply safety clamps
        clamped_lot = max(self.config.min_lot, min(rounded_lot, self.config.max_lot))
        return clamped_lot

    def run(self, candles: List[Candle]) -> BacktestResult:
        """
        Execute full event-driven simulation over chronological closed candles.
        Zero look-ahead: only past candles are visible at any step.
        """
        if not candles:
            return BacktestResult(config=self.config)

        balance = self.config.initial_balance
        equity_curve: List[Tuple[datetime, float]] = [(candles[0].timestamp, balance)]
        trades: List[BacktestTrade] = []

        active_trade: Optional[dict] = None
        trade_counter = 0

        # Step through historical bars
        for idx in range(len(candles)):
            current_bar = candles[idx]

            # 1. Manage Active Position (if any)
            if active_trade is not None:
                active_trade["bars_held"] += 1
                exit_price = None
                exit_reason = None
                realized_r = 0.0

                sl = active_trade["stop_loss"]
                tp = active_trade["take_profit"]
                direction = active_trade["direction"]
                slip = self.config.slippage_pips * self.config.pip_size

                if direction == "BUY":
                    sl_hit = current_bar.low <= sl
                    tp_hit = current_bar.high >= tp

                    if sl_hit and tp_hit:
                        # Ambiguous intra-bar order: conservative model penalizes
                        if self.config.assume_worst_case_intrabar:
                            exit_price = sl - slip
                            exit_reason = "SL"
                            realized_r = -1.0
                        else:
                            exit_price = tp - slip
                            exit_reason = "TP"
                            realized_r = active_trade.get("reward_risk_ratio", 5.0)
                    elif sl_hit:
                        exit_price = sl - slip
                        exit_reason = "SL"
                        realized_r = -1.0
                    elif tp_hit:
                        exit_price = tp - slip
                        exit_reason = "TP"
                        realized_r = active_trade.get("reward_risk_ratio", 5.0)

                else:  # SELL
                    sl_hit = current_bar.high >= sl
                    tp_hit = current_bar.low <= tp

                    if sl_hit and tp_hit:
                        if self.config.assume_worst_case_intrabar:
                            exit_price = sl + slip
                            exit_reason = "SL"
                            realized_r = -1.0
                        else:
                            exit_price = tp + slip
                            exit_reason = "TP"
                            realized_r = active_trade.get("reward_risk_ratio", 5.0)
                    elif sl_hit:
                        exit_price = sl + slip
                        exit_reason = "SL"
                        realized_r = -1.0
                    elif tp_hit:
                        exit_price = tp + slip
                        exit_reason = "TP"
                        realized_r = active_trade.get("reward_risk_ratio", 5.0)

                if exit_price is not None:
                    # Position closed
                    if direction == "BUY":
                        pnl_pips = (exit_price - active_trade["entry_price"]) / self.config.pip_size
                    else:
                        pnl_pips = (active_trade["entry_price"] - exit_price) / self.config.pip_size

                    pnl_currency = pnl_pips * active_trade["lots"] * self.config.pip_value_per_lot
                    balance += pnl_currency

                    record = BacktestTrade(
                        trade_id=active_trade["trade_id"],
                        direction=direction,
                        entry_time=active_trade["entry_time"],
                        exit_time=current_bar.timestamp,
                        entry_price=active_trade["entry_price"],
                        exit_price=exit_price,
                        stop_loss=sl,
                        take_profit=tp,
                        lots=active_trade["lots"],
                        pnl_currency=pnl_currency,
                        pnl_pips=pnl_pips,
                        realized_r=realized_r,
                        exit_reason=exit_reason,
                        bars_held=active_trade["bars_held"],
                    )
                    trades.append(record)
                    equity_curve.append((current_bar.timestamp, balance))
                    active_trade = None

            # 2. Check for New Signal (only if no active trade or below concurrency limit)
            if active_trade is None:
                # Pass bounded closed history window up to current_bar into Phase 1 RuleEngine
                lookback_depth = self.rule_engine.swing_lookback + 10
                visible_candles = candles[max(0, idx + 1 - lookback_depth) : idx + 1]
                signal: Optional[TradeSignal] = self.rule_engine.evaluate_completed_candle(visible_candles)

                if signal is not None:
                    trade_counter += 1
                    slip = self.config.slippage_pips * self.config.pip_size
                    spread = self.config.spread_pips * self.config.pip_size

                    # Model execution fill price
                    if signal.direction == "BUY":
                        executed_entry = signal.entry_price + spread + slip
                    else:
                        executed_entry = signal.entry_price - slip

                    lots = self.calculate_lot_size(balance, signal.risk_distance)

                    active_trade = {
                        "trade_id": trade_counter,
                        "direction": signal.direction,
                        "entry_time": current_bar.timestamp,
                        "entry_price": executed_entry,
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "lots": lots,
                        "risk_distance": signal.risk_distance,
                        "reward_risk_ratio": getattr(signal, "reward_risk_ratio", getattr(self.rule_engine, "reward_risk_ratio", 5.0)),
                        "bars_held": 0,
                    }

        # 3. Close open trade at end of dataset if still active
        if active_trade is not None:
            last_bar = candles[-1]
            exit_price = last_bar.close
            direction = active_trade["direction"]
            if direction == "BUY":
                pnl_pips = (exit_price - active_trade["entry_price"]) / self.config.pip_size
            else:
                pnl_pips = (active_trade["entry_price"] - exit_price) / self.config.pip_size

            pnl_currency = pnl_pips * active_trade["lots"] * self.config.pip_value_per_lot
            balance += pnl_currency

            record = BacktestTrade(
                trade_id=active_trade["trade_id"],
                direction=direction,
                entry_time=active_trade["entry_time"],
                exit_time=last_bar.timestamp,
                entry_price=active_trade["entry_price"],
                exit_price=exit_price,
                stop_loss=active_trade["stop_loss"],
                take_profit=active_trade["take_profit"],
                lots=active_trade["lots"],
                pnl_currency=pnl_currency,
                pnl_pips=pnl_pips,
                realized_r=round(pnl_pips / (active_trade["risk_distance"] / self.config.pip_size), 2),
                exit_reason="END_OF_DATA",
                bars_held=active_trade["bars_held"],
            )
            trades.append(record)
            equity_curve.append((last_bar.timestamp, balance))

        return BacktestResult(
            config=self.config,
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=self.config.initial_balance,
            final_balance=balance,
        )

    def run_multitimeframe(
        self,
        m1_candles: Sequence[Candle],
        m5_candles: Optional[Sequence[Candle]] = None,
        m15_candles: Optional[Sequence[Candle]] = None,
    ) -> BacktestResult:
        """
        Execute full multi-timeframe event-driven simulation (Phase 1/2 Specification).
        
        Evaluates:
        - M5 & M15 candle closes to spot liquidity sweeps and arm 1-minute confirmation watch.
        - M1 candle closes to evaluate 3-candle confirmation, direction break disarm, and 15-candle expiry.
        - M1 candle high/low to monitor active position stop-loss and take-profit with realistic spread/slippage.
        """
        if not m1_candles:
            return BacktestResult(config=self.config)

        from datetime import timedelta
        self.rule_engine.reset()

        m1 = list(m1_candles)
        m5 = list(m5_candles) if m5_candles is not None else (resample_m1_to_htf(m1, 5) if self.rule_engine.check_m5 else [])
        m15 = list(m15_candles) if m15_candles is not None else (resample_m1_to_htf(m1, 15) if self.rule_engine.check_m15 else [])

        import heapq

        # Stream chronological closed bars using O(N) merge
        # Priority: M15 close (priority 0) -> M5 close (priority 1) -> M1 close (priority 2)
        m15_events = ((c.timestamp + timedelta(minutes=15), 0, "M15", c) for c in m15)
        m5_events = ((c.timestamp + timedelta(minutes=5), 1, "M5", c) for c in m5)
        m1_events = ((c.timestamp + timedelta(minutes=1), 2, "M1", c) for c in m1)

        events = heapq.merge(m15_events, m5_events, m1_events, key=lambda x: (x[0], x[1]))

        balance = self.config.initial_balance
        equity_curve: List[Tuple[datetime, float]] = [(m1[0].timestamp, balance)]
        trades: List[BacktestTrade] = []

        active_trade: Optional[dict] = None
        trade_counter = 0

        for close_time, priority, tf, bar in events:
            if tf in ("M5", "M15"):
                self.rule_engine.on_htf_candle(bar, timeframe=tf)
            elif tf == "M1":
                # 1. Manage Active Position on this 1m bar
                if active_trade is not None:
                    active_trade["bars_held"] += 1
                    exit_price = None
                    exit_reason = None
                    realized_r = 0.0

                    sl = active_trade["stop_loss"]
                    tp = active_trade["take_profit"]
                    direction = active_trade["direction"]
                    slip = self.config.slippage_pips * self.config.pip_size

                    if direction == "BUY":
                        sl_hit = bar.low <= sl
                        tp_hit = bar.high >= tp

                        if sl_hit and tp_hit:
                            if self.config.assume_worst_case_intrabar:
                                exit_price = sl - slip
                                exit_reason = "SL"
                                realized_r = -1.0
                            else:
                                exit_price = tp - slip
                                exit_reason = "TP"
                                realized_r = active_trade.get("reward_risk_ratio", 5.0)
                        elif sl_hit:
                            exit_price = sl - slip
                            exit_reason = "SL"
                            realized_r = -1.0
                        elif tp_hit:
                            exit_price = tp - slip
                            exit_reason = "TP"
                            realized_r = active_trade.get("reward_risk_ratio", 5.0)
                    else:  # SELL
                        sl_hit = bar.high >= sl
                        tp_hit = bar.low <= tp

                        if sl_hit and tp_hit:
                            if self.config.assume_worst_case_intrabar:
                                exit_price = sl + slip
                                exit_reason = "SL"
                                realized_r = -1.0
                            else:
                                exit_price = tp + slip
                                exit_reason = "TP"
                                realized_r = active_trade.get("reward_risk_ratio", 5.0)
                        elif sl_hit:
                            exit_price = sl + slip
                            exit_reason = "SL"
                            realized_r = -1.0
                        elif tp_hit:
                            exit_price = tp + slip
                            exit_reason = "TP"
                            realized_r = active_trade.get("reward_risk_ratio", 5.0)

                    if exit_price is not None:
                        if direction == "BUY":
                            pnl_pips = (exit_price - active_trade["entry_price"]) / self.config.pip_size
                        else:
                            pnl_pips = (active_trade["entry_price"] - exit_price) / self.config.pip_size

                        pnl_currency = pnl_pips * active_trade["lots"] * self.config.pip_value_per_lot
                        balance += pnl_currency

                        record = BacktestTrade(
                            trade_id=active_trade["trade_id"],
                            direction=direction,
                            entry_time=active_trade["entry_time"],
                            exit_time=bar.timestamp,
                            entry_price=active_trade["entry_price"],
                            exit_price=exit_price,
                            stop_loss=sl,
                            take_profit=tp,
                            lots=active_trade["lots"],
                            pnl_currency=pnl_currency,
                            pnl_pips=pnl_pips,
                            realized_r=realized_r,
                            exit_reason=exit_reason,
                            bars_held=active_trade["bars_held"],
                        )
                        trades.append(record)
                        equity_curve.append((bar.timestamp, balance))
                        active_trade = None

                # 2. Check for New Signal if no active trade
                if active_trade is None:
                    signal = self.rule_engine.on_m1_candle(bar)
                    if signal is not None:
                        trade_counter += 1
                        slip = self.config.slippage_pips * self.config.pip_size
                        spread = self.config.spread_pips * self.config.pip_size

                        if signal.direction == "BUY":
                            executed_entry = signal.entry_price + spread + slip
                        else:
                            executed_entry = signal.entry_price - slip

                        lots = self.calculate_lot_size(balance, signal.risk_distance)

                        active_trade = {
                            "trade_id": trade_counter,
                            "direction": signal.direction,
                            "entry_time": bar.timestamp,
                            "entry_price": executed_entry,
                            "stop_loss": signal.stop_loss,
                            "take_profit": signal.take_profit,
                            "lots": lots,
                            "risk_distance": signal.risk_distance,
                            "reward_risk_ratio": getattr(signal, "reward_risk_ratio", getattr(self.rule_engine, "reward_risk_ratio", 5.0)),
                            "bars_held": 0,
                        }

        # 3. Close open trade at end of data
        if active_trade is not None and m1:
            last_bar = m1[-1]
            exit_price = last_bar.close
            direction = active_trade["direction"]
            if direction == "BUY":
                pnl_pips = (exit_price - active_trade["entry_price"]) / self.config.pip_size
            else:
                pnl_pips = (active_trade["entry_price"] - exit_price) / self.config.pip_size

            pnl_currency = pnl_pips * active_trade["lots"] * self.config.pip_value_per_lot
            balance += pnl_currency

            record = BacktestTrade(
                trade_id=active_trade["trade_id"],
                direction=direction,
                entry_time=active_trade["entry_time"],
                exit_time=last_bar.timestamp,
                entry_price=active_trade["entry_price"],
                exit_price=exit_price,
                stop_loss=active_trade["stop_loss"],
                take_profit=active_trade["take_profit"],
                lots=active_trade["lots"],
                pnl_currency=pnl_currency,
                pnl_pips=pnl_pips,
                realized_r=round(pnl_pips / (active_trade["risk_distance"] / self.config.pip_size), 2),
                exit_reason="END_OF_DATA",
                bars_held=active_trade["bars_held"],
            )
            trades.append(record)
            equity_curve.append((last_bar.timestamp, balance))

        return BacktestResult(
            config=self.config,
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=self.config.initial_balance,
            final_balance=balance,
        )
