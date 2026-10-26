"""
1-Minute Buy Strategy, Scenarios 1-2 (BUY_STRATEGY_PROMPT.md, Mission_Impossible_Pine_Script.docx).

- HTF (M5 or M15): a bearish candle X and the next candle Y, which must be bullish, form an
  EQUAL_LOW (Scenario 1) or a SWEEP_LOW (Scenario 2). The setup is armed from close(Y) until
  HTF_SETUP_EXPIRY_BARS candles later.
- 1m: the Mission Impossible 3-run (engine/three_run.py) fires an eligible bullish run, whose first
  candle (doji or bullish) is at or below the prior bearish run's low. The first candle opens at or
  after t_conf, the signal bar S closes at or before t_exp, and the first candle stays the run's lowest.
- BUY when S closes. SL = low(first) - SL_BUFFER_POINTS. TP = fill + RR x (fill - SL),
  priced by the caller from the actual fill (backtest) or the live quote (bridge).

The doc's candle kind (doji = body <= DOJI_BODY_PCT % of the range) is used on every timeframe.
Prices are compared as integer points. The same engine runs the backtest and the live bridge (plan.md §3.2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import config
from .models import Candle, TradeSignal
from .sell_scenarios import HTF_DELTAS, HTF_PRIORITY, M1, CandleKind, PointCandle, from_points, time_fields
from .three_run import DOJI_COUNTINGS, RunSignal, ThreeRunDetector

logger = logging.getLogger("buy_scenarios")

ENTRY_FILLS = ("signal_close", "next_bar_open")
EQUAL_LOW_MODES = ("low", "body", "either")
MAX_RUN_MEMBERS = 4  # doc_exact: an uncounted position-2 doji makes Bull, Doji, Bull, Bull/Doji


class BuyHtfPattern(str, Enum):
    NONE = "NONE"
    EQUAL_LOW = "EQUAL_LOW"
    SWEEP_LOW = "SWEEP_LOW"


class BuySkipReason(str, Enum):
    FIRST_NOT_LOWEST = "FIRST_NOT_LOWEST"
    TOO_MANY_DOJIS = "TOO_MANY_DOJIS"
    SCENARIO_DISABLED = "SCENARIO_DISABLED"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    POSITION_OPEN = "POSITION_OPEN"
    FILL_AT_OR_BELOW_SL = "FILL_AT_OR_BELOW_SL"  # backtest: the bid at the fill is at or below the SL
    NO_NEXT_BAR = "NO_NEXT_BAR"  # backtest: the feed has a gap before the fill bar


def candle_kind_pct(c: PointCandle, doji_body_pct: float) -> CandleKind:
    """Spec §4.1, in order: a doji has a body of at most doji_body_pct % of its range (zero range = doji)."""
    if abs(c.close - c.open) * 100 <= doji_body_pct * (c.high - c.low):
        return CandleKind.DOJI
    return CandleKind.BULL if c.close > c.open else CandleKind.BEAR


def bottom_pattern(
    x: PointCandle, y: PointCandle, tol_pts: int, mode: str = "low", doji_body_pct: float = 5.0
) -> BuyHtfPattern:
    """Spec §4.2 for adjacent closed candles: X bearish, Y bullish, Y's low equal to or below X's low.

    mode "low" compares true lows (the default); "body" compares body bottoms (close of X, open of Y);
    "either" takes the low result and falls back to the body one.
    """
    if candle_kind_pct(x, doji_body_pct) is not CandleKind.BEAR or candle_kind_pct(y, doji_body_pct) is not CandleKind.BULL:
        return BuyHtfPattern.NONE

    def compare(diff: int) -> BuyHtfPattern:
        if abs(diff) <= tol_pts:
            return BuyHtfPattern.EQUAL_LOW
        return BuyHtfPattern.SWEEP_LOW if diff < -tol_pts else BuyHtfPattern.NONE

    by_low = compare(y.low - x.low)
    if mode == "low":
        return by_low
    by_body = compare(y.open - x.close)
    if mode == "body":
        return by_body
    return by_low if by_low is not BuyHtfPattern.NONE else by_body


@dataclass(frozen=True)
class BuyScenarioParams:
    """BUY_STRATEGY_PROMPT.md §8 (defaults are the config.py constants) plus the symbol's pip and point size."""

    enabled_scenarios: Tuple[int, ...] = config.BUY_ENABLED_SCENARIOS
    htf_timeframes: Tuple[str, ...] = tuple(config.HTF)
    rr: float = float(config.RR_MULTIPLE)
    entry_fill: str = config.BUY_ENTRY_FILL
    doji_body_pct: float = config.BUY_DOJI_BODY_PCT
    max_doji_in_run: int = config.BUY_MAX_DOJI_IN_RUN
    doji_counting: str = config.BUY_DOJI_COUNTING
    ltf_eq_tol_points: int = config.BUY_LTF_EQ_TOL_POINTS
    equal_low_mode: str = config.BUY_EQUAL_LOW_MODE
    htf_eq_tol_points: int = config.BUY_HTF_EQ_TOL_POINTS
    sl_buffer_points: int = config.BUY_SL_BUFFER_POINTS
    first_must_be_lowest: bool = config.BUY_FIRST_MUST_BE_LOWEST
    htf_setup_expiry_bars: int = config.BUY_HTF_SETUP_EXPIRY_BARS
    run_must_start_after_htf: bool = config.BUY_RUN_MUST_START_AFTER_HTF
    invalidate_on_close_below_htf_low: bool = config.BUY_INVALIDATE_ON_CLOSE_BELOW_HTF_LOW
    ltf_near_htf_low_pips: Optional[float] = config.BUY_LTF_NEAR_HTF_LOW_PIPS
    max_trades_per_setup: int = config.BUY_MAX_TRADES_PER_SETUP
    max_open_positions: Optional[int] = config.BUY_MAX_OPEN_POSITIONS
    same_bar_sl_tp: str = config.BUY_SAME_BAR_SL_TP
    max_1m_gap_minutes: int = config.BUY_MAX_1M_GAP_MINUTES
    session_filter_enabled: bool = True
    session_start_hour: int = config.BUY_SESSION_START_HOUR
    session_end_hour: int = config.BUY_SESSION_END_HOUR
    session_weekdays: Tuple[int, ...] = config.BUY_SESSION_WEEKDAYS
    pip_size: float = 0.0001
    point_size: float = 0.00001

    def __post_init__(self) -> None:
        if not set(self.enabled_scenarios) <= {1, 2}:
            raise ValueError(f"enabled_scenarios must be within 1-2 (got {self.enabled_scenarios})")
        if not self.htf_timeframes or not set(self.htf_timeframes) <= set(HTF_DELTAS):
            raise ValueError(f"htf_timeframes must be M5 and/or M15 (got {self.htf_timeframes})")
        if self.rr <= 0:
            raise ValueError(f"rr must be positive (got {self.rr})")
        if self.entry_fill not in ENTRY_FILLS:
            raise ValueError(f"entry_fill must be one of {ENTRY_FILLS} (got {self.entry_fill!r})")
        if not 0 <= self.doji_body_pct < 100:
            raise ValueError(f"doji_body_pct must be in [0, 100) (got {self.doji_body_pct})")
        if self.doji_counting not in DOJI_COUNTINGS:
            raise ValueError(f"doji_counting must be one of {DOJI_COUNTINGS} (got {self.doji_counting!r})")
        if self.equal_low_mode not in EQUAL_LOW_MODES:
            raise ValueError(f"equal_low_mode must be one of {EQUAL_LOW_MODES} (got {self.equal_low_mode!r})")
        if min(self.ltf_eq_tol_points, self.htf_eq_tol_points, self.sl_buffer_points, self.max_doji_in_run) < 0:
            raise ValueError("Tolerances, sl_buffer_points and max_doji_in_run cannot be negative")
        if self.htf_setup_expiry_bars < 1 or self.max_trades_per_setup < 1:
            raise ValueError("htf_setup_expiry_bars and max_trades_per_setup must be >= 1")
        if self.max_open_positions is not None and self.max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1, or None for no limit")
        if self.ltf_near_htf_low_pips is not None and self.ltf_near_htf_low_pips < 0:
            raise ValueError("ltf_near_htf_low_pips cannot be negative (None turns the filter off)")
        if self.same_bar_sl_tp != "SL_FIRST":
            raise ValueError("same_bar_sl_tp must be SL_FIRST: bar data cannot order SL and TP inside one bar")
        if self.max_1m_gap_minutes < 1:
            raise ValueError("max_1m_gap_minutes must be >= 1")
        if not 0 <= self.session_start_hour < self.session_end_hour <= 24:
            raise ValueError("Session hours must satisfy 0 <= start < end <= 24")
        if self.pip_size <= 0 or self.point_size <= 0:
            raise ValueError("pip_size and point_size must be positive")

    def pips_to_points(self, pips: float) -> int:
        return int(round(pips * self.pip_size / self.point_size))

    @classmethod
    def for_symbol(cls, symbol: str, **overrides: Any) -> BuyScenarioParams:
        """Pip and point size from the symbol: JPY quotes have 3 digits, the others 5."""
        if "JPY" in symbol.upper():
            overrides = {"pip_size": 0.01, "point_size": 0.001, **overrides}
        return cls(**overrides)

    @classmethod
    def from_app_config(cls, cfg: Any, symbol: str) -> BuyScenarioParams:
        """Live parameters: the session and position limit come from the AppConfig the guardrails use."""
        return cls.for_symbol(
            symbol,
            session_filter_enabled=cfg.session_filter_enabled,
            session_start_hour=cfg.session_start_hour,
            session_end_hour=cfg.session_end_hour,
            max_open_positions=cfg.max_open_trades,
        )


@dataclass(frozen=True)
class BuyHtfSetup:
    """An armed HTF pattern (spec §6.4)."""
    setup_id: str
    timeframe: str
    pattern: BuyHtfPattern
    x: Candle
    y: Candle
    setup_low: float
    setup_low_pts: int
    t_conf: datetime
    t_exp: datetime


@dataclass(frozen=True)
class BuyDecision:
    """A bullish 3-run that matched an armed setup: a BUY signal, or a skip with its reason."""
    scenario: int
    setup: BuyHtfSetup
    matching_setup_ids: Tuple[str, ...]
    run: RunSignal
    ltf_type: str  # "EQUAL" or "SWEEP": the first candle's low against the prior run's low
    stop_loss: float
    point_size: float
    skip_reason: Optional[BuySkipReason] = None
    signal: Optional[TradeSignal] = None

    @property
    def signal_time(self) -> datetime:
        """close_time(S): the moment the buy is placed."""
        return self.run.signal.timestamp + M1

    @property
    def doji_positions(self) -> str:
        return "/".join(str(i) for i in self.run.doji_positions) or "none"

    def to_record(self) -> Dict[str, Any]:
        """Journal fields (spec §11) known when S closes, with times in UTC and UTC+6."""
        s, run = self.setup, self.run
        record: Dict[str, Any] = {
            "side": "BUY",
            "event": "SIGNAL" if self.signal is not None else "SKIPPED",
            "scenario": self.scenario,
            "htf_tf": s.timeframe,
            "htf_pattern": s.pattern.value,
            "setup_id": s.setup_id,
            "setup_low": s.setup_low,
            "prior_low": from_points(run.prior_low, self.point_size),
            "ltf_type": self.ltf_type,
            "doji_count": len(run.doji_positions),
            "doji_positions": self.doji_positions,
            "sl": self.stop_loss,
            "matching_setup_ids": "|".join(self.matching_setup_ids),
            "skip_reason": self.skip_reason.value if self.skip_reason is not None else "",
        }
        record.update(time_fields("htf_X_time", s.x.timestamp))
        record.update(time_fields("htf_Y_time", s.y.timestamp))
        record.update(time_fields("t_conf", s.t_conf))
        record.update(time_fields("t_exp", s.t_exp))
        record.update(time_fields("prior_run_start", run.prior_members[0].candle.timestamp))
        record.update(time_fields("prior_run_end", run.prior_members[-1].candle.timestamp))
        record.update(time_fields("first_candle_time", run.first.timestamp))
        record.update(time_fields("signal_bar_time", run.signal.timestamp))
        record.update(time_fields("signal_time", self.signal_time))
        for i, member in enumerate(run.members, start=1):
            c = member.candle.candle
            record.update(time_fields(f"run{i}_time", c.timestamp))
            record.update({f"run{i}_kind": member.kind.value, f"run{i}_open": c.open, f"run{i}_high": c.high,
                           f"run{i}_low": c.low, f"run{i}_close": c.close})
        return record


def _normalize_timeframe(timeframe: str) -> str:
    tf = timeframe.upper().strip()
    return {"5M": "M5", "5": "M5", "15M": "M15", "15": "M15"}.get(tf, tf)


class BuyScenarioEngine:
    """
    Streaming evaluation of closed candles, the buy mirror of SellScenarioEngine. Feed HTF closes to
    on_htf_candle() and 1m closes to on_m1_candle() in close-time order, HTF first when they close together.

    A returned TradeSignal carries entry = close(S) and the TP for that price; the backtest
    re-prices the TP from its fill and the bridge from the live quote (see tp_from_fill).
    """

    tp_from_fill = True  # read by bridge/executor.py: price the TP from the live quote, not close(S)

    def __init__(
        self,
        params: Optional[BuyScenarioParams] = None,
        symbol: str = "USDCAD",
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.params = params or BuyScenarioParams.for_symbol(symbol)
        self.symbol = symbol
        self.event_sink = event_sink
        self.reward_risk_ratio = self.params.rr
        # bridge/executor.py sets or reads these on every rule engine; they do not affect this strategy.
        self.spread_pips = 0.0
        self._m1_body_sum = 0.0
        self._m1_body_count = 0

        p = self.params
        self._near_pts = None if p.ltf_near_htf_low_pips is None else p.pips_to_points(p.ltf_near_htf_low_pips)
        self._max_gap = timedelta(minutes=p.max_1m_gap_minutes)
        self.reset()

    def reset(self) -> None:
        """Clear armed setups, the 3-run detector and the decision log."""
        self.decisions: List[BuyDecision] = []
        self._armed: List[BuyHtfSetup] = []
        self._trades_per_setup: Dict[str, int] = {}
        self._last_htf: Dict[str, PointCandle] = {}
        self._last_m1: Optional[datetime] = None
        self._detector = ThreeRunDetector(self.params.doji_counting, self.params.ltf_eq_tol_points)
        self._warned_no_m1 = False

    @property
    def armed_setups(self) -> Tuple[BuyHtfSetup, ...]:
        return tuple(self._armed)

    def on_htf_candle(self, raw_candle: Union[Candle, Dict[str, Any]], timeframe: str = "M5") -> Optional[BuyHtfSetup]:
        """Ingest one closed HTF candle as Y; the previous candle of that timeframe is X (spec §6)."""
        tf = _normalize_timeframe(timeframe)
        if tf not in self.params.htf_timeframes:
            return None
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        y = PointCandle.of(candle, self.params.point_size)
        x = self._last_htf.get(tf)
        if x is not None and y.timestamp <= x.timestamp:
            return None  # already seen: the bridge re-reads its bar files
        self._last_htf[tf] = y
        delta = HTF_DELTAS[tf]
        if x is None or y.timestamp - x.timestamp != delta:
            return None  # X and Y must be adjacent candles
        p = self.params
        pattern = bottom_pattern(x, y, p.htf_eq_tol_points, p.equal_low_mode, p.doji_body_pct)
        if pattern is BuyHtfPattern.NONE:
            return None
        t_conf = y.timestamp + delta
        setup = BuyHtfSetup(
            setup_id=f"{tf}@{y.timestamp:%Y-%m-%dT%H:%M}",
            timeframe=tf,
            pattern=pattern,
            x=x.candle,
            y=candle,
            setup_low=min(x.candle.low, candle.low),
            setup_low_pts=min(x.low, y.low),
            t_conf=t_conf,
            t_exp=t_conf + p.htf_setup_expiry_bars * delta,
        )
        self._armed.append(setup)
        return setup

    def on_m1_candle(self, raw_candle: Union[Candle, Dict[str, Any]], open_positions: int = 0) -> Optional[TradeSignal]:
        """Ingest one closed 1m candle; a bullish 3-run fired on it is S (spec §9 on_1m_close)."""
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        c = PointCandle.of(candle, self.params.point_size)
        if self._last_m1 is not None:
            step = c.timestamp - self._last_m1
            if step <= timedelta(0):
                return None  # already seen
            if step > self._max_gap:
                self._detector.reset()  # feed outage: no run spans the gap
        self._last_m1 = c.timestamp

        now = c.timestamp + M1
        self._armed = [s for s in self._armed if s.t_exp >= now]
        if self.params.invalidate_on_close_below_htf_low:
            self._armed = [s for s in self._armed if c.close >= s.setup_low_pts]
        live_ids = {s.setup_id for s in self._armed}
        self._trades_per_setup = {k: v for k, v in self._trades_per_setup.items() if k in live_ids}

        run = self._detector.push(c, candle_kind_pct(c, self.params.doji_body_pct))
        if run is None or run.direction is not CandleKind.BULL or not self._armed:
            return None
        return self._evaluate(run, now, open_positions)

    def evaluate_completed_candle(self, raw_candles: Sequence[Any]) -> None:
        """The bridge's single-timeframe path cannot run this strategy: it needs the M1 bar export."""
        if not self._warned_no_m1:
            logger.warning("Buy scenarios need the MT4 M1 bar export; no M1 file found, so no signals.")
            self._warned_no_m1 = True
        return None

    def _evaluate(self, run: RunSignal, now: datetime, open_positions: int) -> Optional[TradeSignal]:
        p = self.params
        first = run.first
        matches = sorted(
            (
                s for s in self._armed
                if (first.timestamp >= s.t_conf or not p.run_must_start_after_htf)
                and now <= s.t_exp
                and self._near_htf_low(s, first)
            ),
            key=lambda s: (HTF_PRIORITY[s.timeframe], -s.t_conf.timestamp()),
        )
        if not matches:
            return None
        setup = matches[0]
        scenario = 1 if setup.pattern is BuyHtfPattern.EQUAL_LOW else 2
        sl_pts = first.low - p.sl_buffer_points
        decision = BuyDecision(
            scenario=scenario,
            setup=setup,
            matching_setup_ids=tuple(s.setup_id for s in matches),
            run=run,
            ltf_type="EQUAL" if abs(first.low - run.prior_low) <= p.ltf_eq_tol_points else "SWEEP",
            stop_loss=from_points(sl_pts, p.point_size),
            point_size=p.point_size,
        )
        skip = self._skip_reason(run, scenario, open_positions)
        if skip is not None:
            self._record(replace(decision, skip_reason=skip))
            return None

        signal = self._signal(decision, run.signal, sl_pts)
        self._consume(setup)
        self._record(replace(decision, signal=signal))
        return signal

    def _near_htf_low(self, setup: BuyHtfSetup, first: PointCandle) -> bool:
        return self._near_pts is None or abs(first.low - setup.setup_low_pts) <= self._near_pts

    def _skip_reason(self, run: RunSignal, scenario: int, open_positions: int) -> Optional[BuySkipReason]:
        p = self.params
        if p.first_must_be_lowest and run.low < run.first.low:
            return BuySkipReason.FIRST_NOT_LOWEST
        if len(run.doji_positions) > p.max_doji_in_run:
            return BuySkipReason.TOO_MANY_DOJIS
        if scenario not in p.enabled_scenarios:
            return BuySkipReason.SCENARIO_DISABLED
        if not self._in_session(run.signal.timestamp):
            return BuySkipReason.OUTSIDE_SESSION
        if p.max_open_positions is not None and open_positions >= p.max_open_positions:
            return BuySkipReason.POSITION_OPEN
        return None

    def _in_session(self, bar_open: datetime) -> bool:
        """The existing session gate (07:00-21:00 UTC, Monday-Friday by default), on S's open time."""
        p = self.params
        if not p.session_filter_enabled:
            return True
        utc = bar_open.replace(tzinfo=timezone.utc) if bar_open.tzinfo is None else bar_open.astimezone(timezone.utc)
        return utc.weekday() in p.session_weekdays and p.session_start_hour <= utc.hour < p.session_end_hour

    def _signal(self, decision: BuyDecision, s: PointCandle, sl_pts: int) -> TradeSignal:
        p = self.params
        risk_pts = s.close - sl_pts
        tp_pts = s.close + int(round(p.rr * risk_pts))
        return TradeSignal(
            direction="BUY",
            entry_price=s.candle.close,
            stop_loss=decision.stop_loss,
            take_profit=from_points(tp_pts, p.point_size),
            risk_distance=from_points(risk_pts, p.point_size),
            reward_distance=from_points(tp_pts - s.close, p.point_size),
            reward_risk_ratio=p.rr,
            sweep_type=f"BUY_S{decision.scenario}",
            timestamp=s.timestamp,
            sweep_timeframe=decision.setup.timeframe,
            timeframe="M1",
            extreme_price=decision.setup.setup_low,
        )

    def _consume(self, setup: BuyHtfSetup) -> None:
        count = self._trades_per_setup.get(setup.setup_id, 0) + 1
        self._trades_per_setup[setup.setup_id] = count
        if count >= self.params.max_trades_per_setup:
            self._armed = [s for s in self._armed if s.setup_id != setup.setup_id]

    def _record(self, decision: BuyDecision) -> None:
        self.decisions.append(decision)
        if self.event_sink is None:
            return
        try:
            self.event_sink(decision.to_record())
        except Exception as exc:  # journaling must never block a trade
            logger.error(f"Buy scenario journal write failed: {exc}")
