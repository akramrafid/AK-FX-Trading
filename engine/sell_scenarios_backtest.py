"""
Backtest runner for the 1-minute Sell Scenarios (SELL_STRATEGY_PROMPT.md §6, §10, §12).

Drives the same SellScenarioEngine as the live bridge over bid OHLC bars:
- entry at the next 1m bar's open (ENTRY_FILL = next_bar_open) or at close(B3)
  (b3_close), less slippage; SL - fill <= 0 skips the trade;
- TP = fill - RR x (SL - fill), so the realised reward:risk is exactly RR;
- a short closes at the ask: SL is hit when bid_high + spread >= SL and TP when
  bid_low + spread <= TP; both in one bar count as SL (no tick data); a bar that opens
  through the SL fills at its open, a TP fills at its level;
- exits are SL or TP only; positions still open at the end close at the last ask (END_OF_DATA).
Position size uses the existing backtester's model (engine/backtester.py): RISK_PERCENT of balance.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import config
from engine.backtester import BacktestConfig, BacktestEngine
from engine.models import Candle
from engine.sell_scenarios import (
    HTF_DELTAS,
    M1,
    SellDecision,
    SellScenarioEngine,
    SellScenarioParams,
    SkipReason,
    from_points,
    time_fields,
    to_points,
)

EVENT_PRIORITY = {"M15": 1, "M5": 2, "M1": 3}  # HTF closes go before the 1m close at the same time


def _time_columns(name: str) -> List[str]:
    return [f"{name}_utc", f"{name}_utc6"]


JOURNAL_COLUMNS: Tuple[str, ...] = tuple(
    ["trade_id", "event", "scenario", "htf_tf", "htf_pattern", "setup_id"]
    + _time_columns("htf_X_time")
    + _time_columns("htf_Y_time")
    + ["setup_high"]
    + _time_columns("t_conf")
    + _time_columns("t_exp")
    + ["ltf_pattern"]
    + [
        column
        for name in ("A", "B1", "B2", "B3")
        for column in _time_columns(f"{name}_time") + [f"{name}_{f}" for f in ("open", "high", "low", "close")]
    ]
    + ["doji_position"]
    + _time_columns("signal_time")
    + _time_columns("entry_time")
    + ["entry_price", "sl", "tp", "risk_pips", "spread_at_entry", "lots"]
    + _time_columns("exit_time")
    + ["exit_price", "exit_reason", "r_multiple", "net_r_after_commission", "pnl_usd", "held_through_feed_gap"]
    + ["matching_setup_ids", "skip_reason"]
)


@dataclass(frozen=True)
class SellBacktestSettings:
    """Account and cost model. Spread and slippage are constant pips (the existing model)."""
    initial_balance: float = 5000.0
    risk_pct: float = config.RISK_PERCENT
    spread_pips: float = 0.0
    slippage_pips: float = 0.0
    pip_value_per_lot: float = 7.14  # USD per pip per lot on USDCAD near 1.40 (run_current_strategy_backtest.py)
    commission_per_lot_round_turn: float = config.COMMISSION_PER_LOT_ROUND_TURN  # net-R column only


@dataclass(frozen=True)
class SellTrade:
    trade_id: int
    decision: SellDecision
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
class SellSkip:
    decision: SellDecision
    reason: SkipReason


@dataclass(frozen=True)
class SellBacktestResult:
    params: SellScenarioParams
    settings: SellBacktestSettings
    decisions: Tuple[SellDecision, ...]
    trades: Tuple[SellTrade, ...]
    skips: Tuple[SellSkip, ...]
    equity_curve: Tuple[Tuple[datetime, float], ...]
    final_balance: float


@dataclass
class _OpenPosition:
    trade_id: int
    decision: SellDecision
    entry_time: datetime
    fill_pts: int
    sl_pts: int
    tp_pts: int
    lots: float
    held_through_feed_gap: bool = False


class _Book:
    """Open shorts, balance and the trade/skip journal of one run."""

    def __init__(self, params: SellScenarioParams, settings: SellBacktestSettings) -> None:
        self.params = params
        self.settings = settings
        self.balance = settings.initial_balance
        self.positions: List[_OpenPosition] = []
        self.trades: List[SellTrade] = []
        self.skips: List[SellSkip] = []
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

    def open(self, decision: SellDecision, fill_bid: float, fill_time: datetime) -> None:
        """Sell at the bid; TP comes from the fill.

        Skipped when the ask at the fill is at or above the SL: the broker rejects a sell whose
        stop is not above the ask. With spread 0 this is the spec's "fill at or above SL" rule.
        """
        fill_pts = to_points(fill_bid, self.params.point_size) - self._slip_pts
        sl_pts = to_points(decision.stop_loss, self.params.point_size)
        risk_pts = sl_pts - fill_pts
        if fill_pts + self._spread_pts >= sl_pts:
            self.skips.append(SellSkip(decision, SkipReason.FILL_AT_OR_ABOVE_SL))
            return
        self._last_id += 1
        self.positions.append(
            _OpenPosition(
                trade_id=self._last_id,
                decision=decision,
                entry_time=fill_time,
                fill_pts=fill_pts,
                sl_pts=sl_pts,
                tp_pts=fill_pts - int(round(self.params.rr * risk_pts)),
                lots=self._sizer.calculate_lot_size(self.balance, risk_pts * self.params.point_size),
            )
        )

    def manage(self, bar: Candle, after_gap: bool) -> None:
        """SL/TP for every open short on this bid bar: the short closes at the ask (bid + spread)."""
        ask_open = to_points(bar.open, self.params.point_size) + self._spread_pts
        ask_high = to_points(bar.high, self.params.point_size) + self._spread_pts
        ask_low = to_points(bar.low, self.params.point_size) + self._spread_pts
        still_open: List[_OpenPosition] = []
        for pos in self.positions:
            pos.held_through_feed_gap = pos.held_through_feed_gap or after_gap
            if ask_high >= pos.sl_pts:  # SL first when one bar touches both; a gap through the stop fills at the open
                self._close(pos, bar.timestamp, max(pos.sl_pts, ask_open) + self._slip_pts, "SL")
            elif ask_low <= pos.tp_pts:
                self._close(pos, bar.timestamp, pos.tp_pts + self._slip_pts, "TP")
            else:
                still_open.append(pos)
        self.positions = still_open

    def close_all(self, last_bar: Candle) -> None:
        ask_close = to_points(last_bar.close, self.params.point_size) + self._spread_pts
        for pos in self.positions:
            self._close(pos, last_bar.timestamp, ask_close + self._slip_pts, "END_OF_DATA")
        self.positions = []

    def _close(self, pos: _OpenPosition, exit_time: datetime, exit_pts: int, reason: str) -> None:
        ps = self.params.point_size
        risk_pts = pos.sl_pts - pos.fill_pts
        r_multiple = (pos.fill_pts - exit_pts) / risk_pts
        risk_pips = risk_pts / self._points_per_pip
        pnl = (pos.fill_pts - exit_pts) / self._points_per_pip * pos.lots * self.settings.pip_value_per_lot
        self.balance += pnl
        # Live sizing (bridge/sizing.py R4) folds the round-turn commission into the 1% risk.
        risk_per_lot = risk_pips * self.settings.pip_value_per_lot
        commission = self.settings.commission_per_lot_round_turn
        net_r = (r_multiple * risk_per_lot - commission) / (risk_per_lot + commission)
        self.trades.append(
            SellTrade(
                trade_id=pos.trade_id,
                decision=pos.decision,
                entry_time=pos.entry_time,
                entry_price=from_points(pos.fill_pts, ps),
                stop_loss=from_points(pos.sl_pts, ps),
                take_profit=from_points(pos.tp_pts, ps),
                risk_pips=risk_pips,
                spread_pips=self.settings.spread_pips,
                lots=pos.lots,
                exit_time=exit_time,
                exit_price=from_points(exit_pts, ps),
                exit_reason=reason,
                r_multiple=r_multiple,
                net_r_after_commission=net_r,
                pnl_currency=pnl,
                held_through_feed_gap=pos.held_through_feed_gap,
            )
        )
        self.equity_curve.append((exit_time, self.balance))


def merge_events(
    m1: Sequence[Candle], htf: Mapping[str, Sequence[Candle]]
) -> List[Tuple[datetime, int, str, Candle]]:
    """Closed-candle events in close-time order; at the same time M15 closes first, then M5, then M1."""
    unknown = set(htf) - set(HTF_DELTAS)
    if unknown:
        raise ValueError(f"Unsupported HTF timeframes: {sorted(unknown)} (expected M5, M15)")
    events = [
        (c.timestamp + HTF_DELTAS[tf], EVENT_PRIORITY[tf], tf, c) for tf, candles in htf.items() for c in candles
    ]
    events.extend((c.timestamp + M1, EVENT_PRIORITY["M1"], "M1", c) for c in m1)
    events.sort(key=lambda event: (event[0], event[1]))
    return events


def run_sell_backtest(
    m1: Sequence[Candle],
    htf: Mapping[str, Sequence[Candle]],
    params: Optional[SellScenarioParams] = None,
    settings: Optional[SellBacktestSettings] = None,
) -> SellBacktestResult:
    """Replay closed 1m and native HTF candles through the engine, filling and managing the shorts."""
    params = params or SellScenarioParams()
    settings = settings or SellBacktestSettings()
    engine = SellScenarioEngine(params)
    book = _Book(params, settings)
    max_gap = timedelta(minutes=params.max_1m_gap_minutes)
    pending: Optional[SellDecision] = None
    prev: Optional[Candle] = None

    for _close_time, _priority, tf, bar in merge_events(m1, htf):
        if tf != "M1":
            engine.on_htf_candle(bar, tf)
            continue
        after_gap = prev is not None and bar.timestamp - prev.timestamp > max_gap
        if pending is not None:
            if after_gap:
                book.skips.append(SellSkip(pending, SkipReason.NO_NEXT_BAR))
            else:
                book.open(pending, bar.open, bar.timestamp)
            pending = None
        book.manage(bar, after_gap)
        if engine.on_m1_candle(bar, open_positions=len(book.positions)) is not None:
            decision = engine.decisions[-1]
            if params.entry_fill == "b3_close":
                book.open(decision, bar.close, bar.timestamp + M1)
            else:
                pending = decision
        prev = bar

    if pending is not None:
        book.skips.append(SellSkip(pending, SkipReason.NO_NEXT_BAR))
    if prev is not None:
        book.close_all(prev)

    engine_skips = [SellSkip(d, d.skip_reason) for d in engine.decisions if d.skip_reason is not None]
    return SellBacktestResult(
        params=params,
        settings=settings,
        decisions=tuple(engine.decisions),
        trades=tuple(sorted(book.trades, key=lambda t: t.trade_id)),
        skips=tuple(sorted(engine_skips + book.skips, key=lambda s: s.decision.signal_time)),
        equity_curve=tuple(book.equity_curve),
        final_balance=book.balance,
    )


def journal_rows(result: SellBacktestResult) -> List[Dict[str, Any]]:
    """Spec §10: one row per trade and per skipped signal, ordered by signal time."""
    rows: List[Dict[str, Any]] = []
    for trade in result.trades:
        row = trade.decision.to_record()
        row.update(
            trade_id=trade.trade_id,
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
        row = skip.decision.to_record()
        row.update(trade_id="", event="SKIPPED", skip_reason=skip.reason.value)
        rows.append(row)
    for row in rows:
        for column in JOURNAL_COLUMNS:
            row.setdefault(column, "")
    rows.sort(key=lambda row: row["signal_time_utc"])
    return rows


@dataclass(frozen=True)
class ScenarioStats:
    """Spec §12 metrics for one group of trades."""
    label: str
    trades: int
    win_rate_pct: float
    avg_r: float
    net_r: float
    max_dd_r: float
    max_dd_pct: float
    longest_losing_streak: int
    avg_sl_pips: float
    avg_spread_pct_of_risk: float
    net_r_after_commission: float


def summarize(label: str, trades: Sequence[SellTrade], risk_pct: float) -> ScenarioStats:
    """Metrics in exit order. Max DD % compounds risk_pct of the balance per trade."""
    ordered = sorted(trades, key=lambda t: (t.exit_time, t.trade_id))
    n = len(ordered)
    if n == 0:
        return ScenarioStats(label, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0)
    cum_r = peak_r = max_dd_r = 0.0
    balance = peak_balance = 1.0
    max_dd_pct = 0.0
    streak = longest = 0
    for trade in ordered:
        cum_r += trade.r_multiple
        peak_r = max(peak_r, cum_r)
        max_dd_r = max(max_dd_r, peak_r - cum_r)
        balance *= 1.0 + trade.r_multiple * risk_pct / 100.0
        peak_balance = max(peak_balance, balance)
        max_dd_pct = max(max_dd_pct, (peak_balance - balance) / peak_balance * 100.0)
        streak = streak + 1 if trade.r_multiple <= 0 else 0
        longest = max(longest, streak)
    r_values = [t.r_multiple for t in ordered]
    return ScenarioStats(
        label=label,
        trades=n,
        win_rate_pct=sum(1 for r in r_values if r > 0) / n * 100.0,
        avg_r=sum(r_values) / n,
        net_r=sum(r_values),
        max_dd_r=max_dd_r,
        max_dd_pct=max_dd_pct,
        longest_losing_streak=longest,
        avg_sl_pips=sum(t.risk_pips for t in ordered) / n,
        avg_spread_pct_of_risk=sum(t.spread_pips / t.risk_pips for t in ordered) / n * 100.0,
        net_r_after_commission=sum(t.net_r_after_commission for t in ordered),
    )


def scenario_stats(result: SellBacktestResult) -> List[ScenarioStats]:
    """Rows for Scenarios 1-4 and the total."""
    risk_pct = result.settings.risk_pct
    rows = [
        summarize(f"Scenario {n}", [t for t in result.trades if t.scenario == n], risk_pct) for n in (1, 2, 3, 4)
    ]
    rows.append(summarize("Total", result.trades, risk_pct))
    return rows
