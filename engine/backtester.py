"""
Event-Driven Backtest Simulator.

Uses the exact same RuleEngine from Phase 1 to guarantee zero code drift between
backtesting, forward testing, and live execution.
Models spread, slippage, dynamic position sizing, and position lifecycle without lookahead bias.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    breakeven_trigger_r: Optional[float] = None
    breakeven_buffer_pips: float = 0.5
    partial_bank_trigger_r: Optional[float] = None
    partial_bank_pct: float = 0.0

    @classmethod
    def institutional_preset(cls, **kwargs) -> BacktestConfig:
        """Standard institutional configuration (Pillars 1 - 5)."""
        defaults = {
            "initial_balance": 10000.0,
            "risk_pct": 1.0,
            "spread_pips": 1.0,
            "slippage_pips": 0.5,
            "pip_size": 0.0001,
            "pip_value_per_lot": 10.0,
            "max_concurrent_trades": 1,
            "min_lot": 0.01,
            "max_lot": 50.0,
            "assume_worst_case_intrabar": True,
            "breakeven_trigger_r": 2.0,
            "breakeven_buffer_pips": 0.5,
            "partial_bank_trigger_r": 2.0,
            "partial_bank_pct": 0.70,
        }
        defaults.update(kwargs)
        return cls(**defaults)

    @classmethod
    def c1_wickswap_preset(cls, **kwargs) -> BacktestConfig:
        """C1 Wick-Swap strategy configuration (1:5 R:R, breakeven at 1:2 R:R strictly to entry)."""
        defaults = {
            "initial_balance": 10000.0,
            "risk_pct": 1.0,
            "spread_pips": 0.0,
            "slippage_pips": 0.0,
            "pip_size": 0.0001,
            "pip_value_per_lot": 10.0,
            "max_concurrent_trades": 1,
            "min_lot": 0.01,
            "max_lot": 50.0,
            "assume_worst_case_intrabar": True,
            "breakeven_trigger_r": 2.0,
            "breakeven_buffer_pips": 0.0,
            "partial_bank_trigger_r": None,
            "partial_bank_pct": 0.0,
        }
        defaults.update(kwargs)
        return cls(**defaults)


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
    exit_reason: str                       # 'TP', 'SL', 'BE', 'END_OF_DATA'
    bars_held: int
    partial_banked: bool = False


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

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        rule_engine: Optional[RuleEngine] = None,
    ) -> None:
        self.config = config or BacktestConfig()
        self.rule_engine = rule_engine or RuleEngine(spread_pips=self.config.spread_pips)

    @classmethod
    def institutional_preset(
        cls,
        config: Optional[BacktestConfig] = None,
        rule_engine: Optional[RuleEngine] = None,
        **kwargs,
    ) -> BacktestEngine:
        """
        Factory constructor for institutional 5-pillar trading backtester.
        """
        config_kwargs = {k: v for k, v in kwargs.items() if hasattr(BacktestConfig, k)}
        rule_kwargs = {k: v for k, v in kwargs.items() if hasattr(RuleEngine, k)}
        cfg = config or BacktestConfig.institutional_preset(**config_kwargs)
        re = rule_engine or RuleEngine.institutional_preset(spread_pips=cfg.spread_pips, **rule_kwargs)
        return cls(config=cfg, rule_engine=re)

    @classmethod
    def c1_wickswap_preset(
        cls,
        config: Optional[BacktestConfig] = None,
        rule_engine: Optional[RuleEngine] = None,
        **kwargs,
    ) -> BacktestEngine:
        """Factory constructor for C1 Wick-Swap strategy backtester."""
        config_kwargs = {k: v for k, v in kwargs.items() if hasattr(BacktestConfig, k)}
        rule_kwargs = {k: v for k, v in kwargs.items() if hasattr(RuleEngine, k)}
        cfg = config or BacktestConfig.c1_wickswap_preset(**config_kwargs)
        re = rule_engine or RuleEngine.c1_wickswap_preset(spread_pips=cfg.spread_pips, **rule_kwargs)
        return cls(config=cfg, rule_engine=re)

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

    def _create_active_trade(
        self,
        trade_id: int,
        signal: TradeSignal,
        timestamp: datetime,
        balance: float,
    ) -> dict:
        slip = self.config.slippage_pips * self.config.pip_size
        spread = self.config.spread_pips * self.config.pip_size

        if signal.direction == "BUY":
            executed_entry = signal.entry_price + spread + slip
        else:
            executed_entry = signal.entry_price - slip

        lots = self.calculate_lot_size(balance, signal.risk_distance)

        pb_r = getattr(signal, "partial_bank_r", None)
        if pb_r is None:
            pb_r = self.config.partial_bank_trigger_r

        pb_pct = getattr(signal, "partial_bank_pct", None)
        if pb_pct is None:
            pb_pct = self.config.partial_bank_pct

        be_r = getattr(signal, "breakeven_trigger_r", None)
        if be_r is None:
            be_r = self.config.breakeven_trigger_r

        return {
            "trade_id": trade_id,
            "direction": signal.direction,
            "entry_time": timestamp,
            "entry_price": executed_entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "lots": lots,
            "initial_lots": lots,
            "risk_distance": signal.risk_distance,
            "reward_risk_ratio": getattr(signal, "reward_risk_ratio", getattr(self.rule_engine, "reward_risk_ratio", 5.0)),
            "bars_held": 0,
            "partial_bank_r": pb_r,
            "partial_bank_pct": pb_pct or 0.0,
            "breakeven_trigger_r": be_r,
            "breakeven_buffer_pips": self.config.breakeven_buffer_pips,
            "partial_banked": False,
            "sl_moved_to_be": False,
            "banked_pnl_currency": 0.0,
        }

    def _manage_position_on_bar(
        self,
        bar: Candle,
        active_trade: dict,
        balance: float,
    ) -> Tuple[Optional[BacktestTrade], float, Optional[dict]]:
        active_trade["bars_held"] += 1
        exit_price = None
        exit_reason = None
        runner_r = 0.0

        sl = active_trade["stop_loss"]
        tp = active_trade["take_profit"]
        direction = active_trade["direction"]
        slip = self.config.slippage_pips * self.config.pip_size
        pip_size = self.config.pip_size
        risk_dist = active_trade["risk_distance"]
        pb_r = active_trade["partial_bank_r"]
        pb_pct = active_trade["partial_bank_pct"]
        be_r = active_trade["breakeven_trigger_r"]
        be_buf = active_trade["breakeven_buffer_pips"] * pip_size

        if direction == "BUY":
            # 1. Check partial bank trigger
            if not active_trade["partial_banked"] and pb_r is not None and pb_pct > 0.0:
                pb_price = active_trade["entry_price"] + (pb_r * risk_dist)
                if bar.high >= pb_price:
                    if not (bar.low <= sl and self.config.assume_worst_case_intrabar):
                        active_trade["partial_banked"] = True
                        banked_lots = active_trade["initial_lots"] * pb_pct
                        banked_pips = (pb_price - active_trade["entry_price"]) / pip_size
                        banked_cash = banked_pips * banked_lots * self.config.pip_value_per_lot
                        active_trade["banked_pnl_currency"] += banked_cash
                        balance += banked_cash

                        be_sl = active_trade["entry_price"] + be_buf
                        active_trade["stop_loss"] = max(active_trade["stop_loss"], be_sl)
                        active_trade["sl_moved_to_be"] = True
                        sl = active_trade["stop_loss"]

            elif not active_trade["sl_moved_to_be"] and be_r is not None:
                be_price = active_trade["entry_price"] + (be_r * risk_dist)
                if bar.high >= be_price:
                    if not (bar.low <= sl and self.config.assume_worst_case_intrabar):
                        be_sl = active_trade["entry_price"] + be_buf
                        active_trade["stop_loss"] = max(active_trade["stop_loss"], be_sl)
                        active_trade["sl_moved_to_be"] = True
                        sl = active_trade["stop_loss"]

            sl_hit = bar.low <= sl
            tp_hit = bar.high >= tp

            if sl_hit and tp_hit:
                if self.config.assume_worst_case_intrabar:
                    exit_price = sl - slip
                    exit_reason = "BE" if active_trade["sl_moved_to_be"] else "SL"
                    runner_r = 0.0 if active_trade["sl_moved_to_be"] else -1.0
                else:
                    exit_price = tp - slip
                    exit_reason = "TP"
                    runner_r = active_trade.get("reward_risk_ratio", 5.0)
            elif sl_hit:
                exit_price = sl - slip
                exit_reason = "BE" if active_trade["sl_moved_to_be"] else "SL"
                runner_r = 0.0 if active_trade["sl_moved_to_be"] else -1.0
            elif tp_hit:
                exit_price = tp - slip
                exit_reason = "TP"
                runner_r = active_trade.get("reward_risk_ratio", 5.0)

        else:  # SELL
            if not active_trade["partial_banked"] and pb_r is not None and pb_pct > 0.0:
                pb_price = active_trade["entry_price"] - (pb_r * risk_dist)
                if bar.low <= pb_price:
                    if not (bar.high >= sl and self.config.assume_worst_case_intrabar):
                        active_trade["partial_banked"] = True
                        banked_lots = active_trade["initial_lots"] * pb_pct
                        banked_pips = (active_trade["entry_price"] - pb_price) / pip_size
                        banked_cash = banked_pips * banked_lots * self.config.pip_value_per_lot
                        active_trade["banked_pnl_currency"] += banked_cash
                        balance += banked_cash

                        be_sl = active_trade["entry_price"] - be_buf
                        active_trade["stop_loss"] = min(active_trade["stop_loss"], be_sl)
                        active_trade["sl_moved_to_be"] = True
                        sl = active_trade["stop_loss"]

            elif not active_trade["sl_moved_to_be"] and be_r is not None:
                be_price = active_trade["entry_price"] - (be_r * risk_dist)
                if bar.low <= be_price:
                    if not (bar.high >= sl and self.config.assume_worst_case_intrabar):
                        be_sl = active_trade["entry_price"] - be_buf
                        active_trade["stop_loss"] = min(active_trade["stop_loss"], be_sl)
                        active_trade["sl_moved_to_be"] = True
                        sl = active_trade["stop_loss"]

            sl_hit = bar.high >= sl
            tp_hit = bar.low <= tp

            if sl_hit and tp_hit:
                if self.config.assume_worst_case_intrabar:
                    exit_price = sl + slip
                    exit_reason = "BE" if active_trade["sl_moved_to_be"] else "SL"
                    runner_r = 0.0 if active_trade["sl_moved_to_be"] else -1.0
                else:
                    exit_price = tp + slip
                    exit_reason = "TP"
                    runner_r = active_trade.get("reward_risk_ratio", 5.0)
            elif sl_hit:
                exit_price = sl + slip
                exit_reason = "BE" if active_trade["sl_moved_to_be"] else "SL"
                runner_r = 0.0 if active_trade["sl_moved_to_be"] else -1.0
            elif tp_hit:
                exit_price = tp + slip
                exit_reason = "TP"
                runner_r = active_trade.get("reward_risk_ratio", 5.0)

        if exit_price is not None:
            runner_pct = (1.0 - pb_pct) if active_trade["partial_banked"] else 1.0
            runner_lots = active_trade["initial_lots"] * runner_pct

            if direction == "BUY":
                runner_pnl_pips = (exit_price - active_trade["entry_price"]) / pip_size
            else:
                runner_pnl_pips = (active_trade["entry_price"] - exit_price) / pip_size

            runner_pnl_currency = runner_pnl_pips * runner_lots * self.config.pip_value_per_lot
            total_pnl_currency = active_trade["banked_pnl_currency"] + runner_pnl_currency
            balance += runner_pnl_currency

            total_pnl_pips = total_pnl_currency / (active_trade["initial_lots"] * self.config.pip_value_per_lot)

            if active_trade["partial_banked"]:
                realized_r = round((pb_r * pb_pct) + (runner_r * (1.0 - pb_pct)), 2)
            else:
                realized_r = runner_r

            record = BacktestTrade(
                trade_id=active_trade["trade_id"],
                direction=direction,
                entry_time=active_trade["entry_time"],
                exit_time=bar.timestamp,
                entry_price=active_trade["entry_price"],
                exit_price=exit_price,
                stop_loss=sl,
                take_profit=tp,
                lots=active_trade["initial_lots"],
                pnl_currency=total_pnl_currency,
                pnl_pips=total_pnl_pips,
                realized_r=realized_r,
                exit_reason=exit_reason,
                bars_held=active_trade["bars_held"],
                partial_banked=active_trade["partial_banked"],
            )
            return record, balance, None

        return None, balance, active_trade

    def _close_at_end_of_data(
        self,
        last_bar: Candle,
        active_trade: dict,
        balance: float,
    ) -> Tuple[BacktestTrade, float]:
        exit_price = last_bar.close
        direction = active_trade["direction"]
        pip_size = self.config.pip_size
        pb_r = active_trade["partial_bank_r"]
        pb_pct = active_trade["partial_bank_pct"]

        runner_pct = (1.0 - pb_pct) if active_trade["partial_banked"] else 1.0
        runner_lots = active_trade["initial_lots"] * runner_pct

        if direction == "BUY":
            runner_pnl_pips = (exit_price - active_trade["entry_price"]) / pip_size
        else:
            runner_pnl_pips = (active_trade["entry_price"] - exit_price) / pip_size

        runner_pnl_currency = runner_pnl_pips * runner_lots * self.config.pip_value_per_lot
        total_pnl_currency = active_trade["banked_pnl_currency"] + runner_pnl_currency
        balance += runner_pnl_currency

        total_pnl_pips = total_pnl_currency / (active_trade["initial_lots"] * self.config.pip_value_per_lot)
        risk_pips = active_trade["risk_distance"] / pip_size
        runner_r = runner_pnl_pips / risk_pips if risk_pips > 0 else 0.0

        if active_trade["partial_banked"]:
            realized_r = round((pb_r * pb_pct) + (runner_r * (1.0 - pb_pct)), 2)
        else:
            realized_r = round(runner_r, 2)

        record = BacktestTrade(
            trade_id=active_trade["trade_id"],
            direction=direction,
            entry_time=active_trade["entry_time"],
            exit_time=last_bar.timestamp,
            entry_price=active_trade["entry_price"],
            exit_price=exit_price,
            stop_loss=active_trade["stop_loss"],
            take_profit=active_trade["take_profit"],
            lots=active_trade["initial_lots"],
            pnl_currency=total_pnl_currency,
            pnl_pips=total_pnl_pips,
            realized_r=realized_r,
            exit_reason="END_OF_DATA",
            bars_held=active_trade["bars_held"],
            partial_banked=active_trade["partial_banked"],
        )
        return record, balance

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
                closed_trade, balance, active_trade = self._manage_position_on_bar(
                    current_bar, active_trade, balance
                )
                if closed_trade is not None:
                    trades.append(closed_trade)
                    equity_curve.append((current_bar.timestamp, balance))

            # 2. Check for New Signal (only if no active trade or below concurrency limit)
            if active_trade is None:
                lookback_depth = self.rule_engine.swing_lookback + 10
                visible_candles = candles[max(0, idx + 1 - lookback_depth) : idx + 1]
                signal: Optional[TradeSignal] = self.rule_engine.evaluate_completed_candle(visible_candles)

                if signal is not None:
                    trade_counter += 1
                    active_trade = self._create_active_trade(
                        trade_counter, signal, current_bar.timestamp, balance
                    )

        # 3. Close open trade at end of dataset if still active
        if active_trade is not None:
            closed_trade, balance = self._close_at_end_of_data(
                candles[-1], active_trade, balance
            )
            trades.append(closed_trade)
            equity_curve.append((candles[-1].timestamp, balance))

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
        h1_candles: Optional[Sequence[Candle]] = None,
    ) -> BacktestResult:
        """
        Execute full multi-timeframe event-driven simulation (Phase 1/2 Specification).
        
        Evaluates:
        - H1 candle closes to update 50 EMA trend filter (priority 0).
        - M5 & M15 candle closes to spot liquidity sweeps and arm 1-minute confirmation watch.
        - M1 candle closes to evaluate 3-candle confirmation, direction break disarm, and 15-candle expiry.
        - M1 candle high/low to monitor active position stop-loss, partial bank, breakeven, and take-profit.
        """
        if not m1_candles:
            return BacktestResult(config=self.config)

        self.rule_engine.reset()

        m1 = list(m1_candles)
        m5 = list(m5_candles) if m5_candles is not None else (resample_m1_to_htf(m1, 5) if self.rule_engine.check_m5 else [])
        m15 = list(m15_candles) if m15_candles is not None else (resample_m1_to_htf(m1, 15) if self.rule_engine.check_m15 else [])
        h1 = list(h1_candles) if h1_candles is not None else (resample_m1_to_htf(m1, 60) if self.rule_engine.h1_trend_filter else [])

        import heapq

        # Stream chronological closed bars using O(N) merge
        # Priority: H1 close (priority 0) -> M15 close (priority 1) -> M5 close (priority 2) -> M1 close (priority 3)
        h1_events = ((c.timestamp + timedelta(hours=1), 0, "H1", c) for c in h1)
        m15_events = ((c.timestamp + timedelta(minutes=15), 1, "M15", c) for c in m15)
        m5_events = ((c.timestamp + timedelta(minutes=5), 2, "M5", c) for c in m5)
        m1_events = ((c.timestamp + timedelta(minutes=1), 3, "M1", c) for c in m1)

        events = heapq.merge(h1_events, m15_events, m5_events, m1_events, key=lambda x: (x[0], x[1]))

        balance = self.config.initial_balance
        equity_curve: List[Tuple[datetime, float]] = [(m1[0].timestamp, balance)]
        trades: List[BacktestTrade] = []

        active_trade: Optional[dict] = None
        trade_counter = 0

        for close_time, priority, tf, bar in events:
            if tf in ("H1", "M5", "M15"):
                self.rule_engine.on_htf_candle(bar, timeframe=tf)
            elif tf == "M1":
                # 1. Manage Active Position on this 1m bar
                if active_trade is not None:
                    closed_trade, balance, active_trade = self._manage_position_on_bar(
                        bar, active_trade, balance
                    )
                    if closed_trade is not None:
                        trades.append(closed_trade)
                        equity_curve.append((bar.timestamp, balance))

                # 2. Check for New Signal if no active trade
                if active_trade is None:
                    signal = self.rule_engine.on_m1_candle(bar)
                    if signal is not None:
                        trade_counter += 1
                        active_trade = self._create_active_trade(
                            trade_counter, signal, bar.timestamp, balance
                        )

        # 3. Close open trade at end of data
        if active_trade is not None and m1:
            closed_trade, balance = self._close_at_end_of_data(
                m1[-1], active_trade, balance
            )
            trades.append(closed_trade)
            equity_curve.append((m1[-1].timestamp, balance))

        return BacktestResult(
            config=self.config,
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=self.config.initial_balance,
            final_balance=balance,
        )
