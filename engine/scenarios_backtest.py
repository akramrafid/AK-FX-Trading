"""
Backtest runner for the buy scenarios and for sell + buy together (BUY_STRATEGY_PROMPT.md §7, §12, §13).

Drives AkScenariosEngine (one side or both) over bid OHLC bars and fills exactly like
engine/sell_scenarios_backtest.py, so a sell-only run reproduces run_sell_backtest:
- a buy fills at the ask: the signal bar's close (ENTRY_FILL = signal_close) or the next 1m bar's
  open (next_bar_open), plus spread and slippage; it is skipped when the bid at the fill is at or
  below the SL (MT4 rejects such a stop; with spread 0 this is the spec's "fill - SL <= 0" rule);
- TP = fill + RR x (fill - SL); a long closes at the bid: SL when bid_low <= SL, TP when
  bid_high >= TP; both in one bar count as SL; a bar that opens through the SL fills at its open;
- sells as in engine/sell_scenarios_backtest.py. One book holds both sides, so the no-hedging
  rule sees every open position;
- exits are SL or TP only; positions still open at the end close at the last bar (END_OF_DATA).
Position size uses the existing backtester's model (engine/backtester.py): RISK_PERCENT of balance.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from engine.ak_scenarios import SAME_BAR_CONFLICT, AkScenariosEngine, Decision, OpenPositions, decision_side
from engine.backtester import BacktestConfig, BacktestEngine
from engine.buy_scenarios import MAX_RUN_MEMBERS, BuySkipReason
from engine.models import Candle
from engine.sell_scenarios import M1, SkipReason, from_points, time_fields, to_points
from engine.sell_scenarios_backtest import JOURNAL_COLUMNS as SELL_JOURNAL_COLUMNS
from engine.sell_scenarios_backtest import SellBacktestSettings as BacktestSettings
from engine.sell_scenarios_backtest import ScenarioStats, merge_events, summarize

SIGNAL_CLOSE_FILLS = ("signal_close", "b3_close")  # the buy and the sell name for "fill at the signal bar's close"


def _time_columns(name: str) -> List[str]:
    return [f"{name}_utc", f"{name}_utc6"]


BUY_JOURNAL_COLUMNS: Tuple[str, ...] = tuple(
    ["trade_id", "side", "event", "scenario", "htf_tf", "htf_pattern", "setup_id"]
    + _time_columns("htf_X_time")
    + _time_columns("htf_Y_time")
    + ["setup_low"]
    + _time_columns("t_conf")
    + _time_columns("t_exp")
    + _time_columns("prior_run_start")
    + _time_columns("prior_run_end")
    + ["prior_low", "ltf_type"]
    + [
        column
        for i in range(1, MAX_RUN_MEMBERS + 1)
        for column in _time_columns(f"run{i}_time") + [f"run{i}_{f}" for f in ("kind", "open", "high", "low", "close")]
    ]
    + _time_columns("first_candle_time")
    + ["doji_count", "doji_positions"]
    + _time_columns("signal_bar_time")
    + _time_columns("signal_time")
    + _time_columns("entry_time")
    + ["entry_price", "sl", "tp", "risk_pips", "spread_at_entry", "lots"]
    + _time_columns("exit_time")
    + ["exit_price", "exit_reason", "r_multiple", "net_r_after_commission", "pnl_usd", "held_through_feed_gap"]
    + ["matching_setup_ids", "skip_reason"]
)
COMBINED_JOURNAL_COLUMNS: Tuple[str, ...] = BUY_JOURNAL_COLUMNS + tuple(
    c for c in SELL_JOURNAL_COLUMNS if c not in BUY_JOURNAL_COLUMNS
)


@dataclass(frozen=True)
class ScenarioTrade:
    trade_id: int
    side: str  # "BUY" or "SELL"
    decision: Decision
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_pips: float
    spread_pips: float
    lots: float
    exit_time: datetime
    exit_price: float
    exit_reason: str  # "TP", "SL" or "END_OF_DATA"
    r_multiple: float
    net_r_after_commission: float
    pnl_currency: float
    held_through_feed_gap: bool

    @property
    def scenario(self) -> int:
        return self.decision.scenario


@dataclass(frozen=True)
class ScenarioSkip:
    decision: Decision
    reason: str  # a SkipReason or BuySkipReason value, or SAME_BAR_CONFLICT


@dataclass(frozen=True)
class ScenariosBacktestResult:
    settings: BacktestSettings
    decisions: Tuple[Decision, ...]
    trades: Tuple[ScenarioTrade, ...]
    skips: Tuple[ScenarioSkip, ...]
    equity_curve: Tuple[Tuple[datetime, float], ...]
    final_balance: float


@dataclass
class _OpenPosition:
    trade_id: int
    side: str
    decision: Decision
    entry_time: datetime
    fill_pts: int
    sl_pts: int
    tp_pts: int
    lots: float
    held_through_feed_gap: bool = False

    @property
    def sign(self) -> int:
        """+1 for a long, -1 for a short: profit in points = sign x (exit - fill)."""
        return 1 if self.side == "BUY" else -1


class _Book:
    """Open positions of both sides, balance and the trade/skip journal of one run."""

    def __init__(self, engine: AkScenariosEngine, settings: BacktestSettings) -> None:
        params = (engine.buy or engine.sell).params
        self.settings = settings
        self.rr = engine.reward_risk_ratio
        self.point_size = params.point_size
        self.balance = settings.initial_balance
        self.positions: List[_OpenPosition] = []
        self.trades: List[ScenarioTrade] = []
        self.skips: List[ScenarioSkip] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self._spread_pts = params.pips_to_points(settings.spread_pips)
        self._slip_pts = params.pips_to_points(settings.slippage_pips)
        self._points_per_pip = params.pips_to_points(1.0)
        self._sizer = BacktestEngine(
            BacktestConfig(
                initial_balance=settings.initial_balance,
                risk_pct=settings.risk_pct,
                pip_size=params.pip_size,
                pip_value_per_lot=settings.pip_value_per_lot,
            )
        )
        self._last_id = 0

    def open_by_side(self) -> OpenPositions:
        buys = sum(1 for pos in self.positions if pos.side == "BUY")
        return buys, len(self.positions) - buys

    def open(self, decision: Decision, bid: float, fill_time: datetime) -> None:
        """Fill at a bid bar price: a buy pays the ask, a sell gets the bid; the TP comes from the fill.

        Skipped when the stop is already on the wrong side of the market: a buy whose bid at the fill
        is at or below the SL, a sell whose ask is at or above it. MT4 rejects such a stop.
        """
        side = decision_side(decision)
        bid_pts = to_points(bid, self.point_size)
        sl_pts = to_points(decision.stop_loss, self.point_size)
        if side == "BUY":
            fill_pts = bid_pts + self._spread_pts + self._slip_pts
            if fill_pts - self._spread_pts <= sl_pts:
                self.skips.append(ScenarioSkip(decision, BuySkipReason.FILL_AT_OR_BELOW_SL.value))
                return
        else:
            fill_pts = bid_pts - self._slip_pts
            if fill_pts + self._spread_pts >= sl_pts:
                self.skips.append(ScenarioSkip(decision, SkipReason.FILL_AT_OR_ABOVE_SL.value))
                return
        sign = 1 if side == "BUY" else -1
        risk_pts = sign * (fill_pts - sl_pts)
        self._last_id += 1
        self.positions.append(
            _OpenPosition(
                trade_id=self._last_id,
                side=side,
                decision=decision,
                entry_time=fill_time,
                fill_pts=fill_pts,
                sl_pts=sl_pts,
                tp_pts=fill_pts + sign * int(round(self.rr * risk_pts)),
                lots=self._sizer.calculate_lot_size(self.balance, risk_pts * self.point_size),
            )
        )

    def manage(self, bar: Candle, after_gap: bool) -> None:
        """SL/TP for every open position on this bid bar: a long closes at the bid, a short at the ask."""
        bid_open, bid_high, bid_low = (to_points(p, self.point_size) for p in (bar.open, bar.high, bar.low))
        still_open: List[_OpenPosition] = []
        for pos in self.positions:
            pos.held_through_feed_gap = pos.held_through_feed_gap or after_gap
            exit_ = self._exit(pos, bid_open, bid_high, bid_low)
            if exit_ is None:
                still_open.append(pos)
            else:
                self._close(pos, bar.timestamp, *exit_)
        self.positions = still_open

    def _exit(self, pos: _OpenPosition, bid_open: int, bid_high: int, bid_low: int) -> Optional[Tuple[int, str]]:
        """SL first when one bar touches both; a bar that opens through the stop fills at its open."""
        if pos.side == "BUY":
            if bid_low <= pos.sl_pts:
                return min(pos.sl_pts, bid_open) - self._slip_pts, "SL"
            if bid_high >= pos.tp_pts:
                return pos.tp_pts - self._slip_pts, "TP"
            return None
        spread = self._spread_pts
        if bid_high + spread >= pos.sl_pts:
            return max(pos.sl_pts, bid_open + spread) + self._slip_pts, "SL"
        if bid_low + spread <= pos.tp_pts:
            return pos.tp_pts + self._slip_pts, "TP"
        return None

    def close_all(self, last_bar: Candle) -> None:
        bid_close = to_points(last_bar.close, self.point_size)
        for pos in self.positions:
            exit_pts = bid_close - self._slip_pts if pos.side == "BUY" else bid_close + self._spread_pts + self._slip_pts
            self._close(pos, last_bar.timestamp, exit_pts, "END_OF_DATA")
        self.positions = []

    def _close(self, pos: _OpenPosition, exit_time: datetime, exit_pts: int, reason: str) -> None:
        risk_pts = pos.sign * (pos.fill_pts - pos.sl_pts)
        r_multiple = pos.sign * (exit_pts - pos.fill_pts) / risk_pts
        risk_pips = risk_pts / self._points_per_pip
        pnl = pos.sign * (exit_pts - pos.fill_pts) / self._points_per_pip * pos.lots * self.settings.pip_value_per_lot
        self.balance += pnl
        # Live sizing (bridge/sizing.py R4) folds the round-turn commission into the 1% risk.
        risk_per_lot = risk_pips * self.settings.pip_value_per_lot
        commission = self.settings.commission_per_lot_round_turn
        net_r = (r_multiple * risk_per_lot - commission) / (risk_per_lot + commission)
        self.trades.append(
            ScenarioTrade(
                trade_id=pos.trade_id,
                side=pos.side,
                decision=pos.decision,
                entry_time=pos.entry_time,
                entry_price=from_points(pos.fill_pts, self.point_size),
                stop_loss=from_points(pos.sl_pts, self.point_size),
                take_profit=from_points(pos.tp_pts, self.point_size),
                risk_pips=risk_pips,
                spread_pips=self.settings.spread_pips,
                lots=pos.lots,
                exit_time=exit_time,
                exit_price=from_points(exit_pts, self.point_size),
                exit_reason=reason,
                r_multiple=r_multiple,
                net_r_after_commission=net_r,
                pnl_currency=pnl,
                held_through_feed_gap=pos.held_through_feed_gap,
            )
        )
        self.equity_curve.append((exit_time, self.balance))


def _fills_at_signal_close(engine: AkScenariosEngine, decision: Decision) -> bool:
    engine_of_side = engine.buy if decision_side(decision) == "BUY" else engine.sell
    return engine_of_side.params.entry_fill in SIGNAL_CLOSE_FILLS


def run_scenarios_backtest(
    m1: Sequence[Candle],
    htf: Mapping[str, Sequence[Candle]],
    engine: AkScenariosEngine,
    settings: Optional[BacktestSettings] = None,
) -> ScenariosBacktestResult:
    """Replay closed 1m and native HTF candles through the engine (reset first), filling and managing both sides."""
    settings = settings or BacktestSettings()
    engine.reset()
    book = _Book(engine, settings)
    max_gap = timedelta(minutes=(engine.buy or engine.sell).params.max_1m_gap_minutes)
    pending: List[Decision] = []  # next-bar-open fills waiting for the next bar
    prev: Optional[Candle] = None

    for _close_time, _priority, tf, bar in merge_events(m1, htf):
        if tf != "M1":
            engine.on_htf_candle(bar, tf)
            continue
        after_gap = prev is not None and bar.timestamp - prev.timestamp > max_gap
        for decision in pending:
            if after_gap:
                book.skips.append(ScenarioSkip(decision, SkipReason.NO_NEXT_BAR.value))
            else:
                book.open(decision, bar.open, bar.timestamp)
        pending = []
        book.manage(bar, after_gap)
        if engine.on_m1_candle(bar, open_positions=book.open_by_side()) is not None:
            decision = engine.last_decision
            if _fills_at_signal_close(engine, decision):
                book.open(decision, bar.close, bar.timestamp + M1)
            else:
                pending.append(decision)
        prev = bar

    book.skips.extend(ScenarioSkip(decision, SkipReason.NO_NEXT_BAR.value) for decision in pending)
    if prev is not None:
        book.close_all(prev)

    decisions = engine.decisions
    engine_skips = [ScenarioSkip(d, d.skip_reason.value) for d in decisions if d.skip_reason is not None]
    conflict_skips = [ScenarioSkip(d, SAME_BAR_CONFLICT) for pair in engine.conflicts for d in pair]
    return ScenariosBacktestResult(
        settings=settings,
        decisions=tuple(decisions),
        trades=tuple(sorted(book.trades, key=lambda t: t.trade_id)),
        skips=tuple(sorted(engine_skips + conflict_skips + book.skips, key=lambda s: s.decision.signal_time)),
        equity_curve=tuple(book.equity_curve),
        final_balance=book.balance,
    )


def journal_rows(result: ScenariosBacktestResult, side: Optional[str] = None) -> List[Dict[str, Any]]:
    """Spec §11: one row per trade and per skipped signal of one side (both when None), by signal time."""
    rows: List[Dict[str, Any]] = []
    for trade in result.trades:
        if side is not None and trade.side != side:
            continue
        row = trade.decision.to_record()
        row.update(
            trade_id=trade.trade_id,
            side=trade.side,
            event="TRADE",
            entry_price=trade.entry_price,
            sl=trade.stop_loss,
            tp=trade.take_profit,
            risk_pips=round(trade.risk_pips, 1),
            spread_at_entry=trade.spread_pips,
            lots=trade.lots,
            exit_price=trade.exit_price,
            exit_reason=trade.exit_reason,
            r_multiple=round(trade.r_multiple, 2),
            net_r_after_commission=round(trade.net_r_after_commission, 2),
            pnl_usd=round(trade.pnl_currency, 2),
            held_through_feed_gap=trade.held_through_feed_gap,
        )
        row.update(time_fields("entry_time", trade.entry_time))
        row.update(time_fields("exit_time", trade.exit_time))
        rows.append(row)
    for skip in result.skips:
        skip_side = decision_side(skip.decision)
        if side is not None and skip_side != side:
            continue
        row = skip.decision.to_record()
        row.update(trade_id="", side=skip_side, event="SKIPPED", skip_reason=skip.reason)
        rows.append(row)
    rows.sort(key=lambda row: row["signal_time_utc"])
    return rows


def scenario_stats(result: ScenariosBacktestResult, side: str = "BUY") -> List[ScenarioStats]:
    """Rows for each scenario of one side and its total (spec §13)."""
    trades = [t for t in result.trades if t.side == side]
    scenarios = (1, 2) if side == "BUY" else (1, 2, 3, 4)
    risk_pct = result.settings.risk_pct
    rows = [summarize(f"Scenario {n}", [t for t in trades if t.scenario == n], risk_pct) for n in scenarios]
    rows.append(summarize("Total", trades, risk_pct))
    return rows
