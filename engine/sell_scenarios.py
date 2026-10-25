"""
1-Minute Sell Strategy, Scenarios 1-4 (SELL_STRATEGY_PROMPT.md).

One mechanical 1m trigger, qualified by a closed 5m or 15m pattern:
- HTF (M5 or M15): a bullish candle X and the next candle Y, which must be bearish,
  form an EQUAL_TOP (Scenarios 1/3) or a WICK_SWEEP (Scenarios 2/4). The setup is
  armed from close(Y) until HTF_SETUP_EXPIRY_BARS candles later.
- 1m: adjacent closed candles A, B1, B2, B3. A is bullish, top_pattern(A, B1) is
  EQUAL_TOP or WICK_SWEEP, B1-B3 hold no bullish candle and at most
  MAX_DOJI_IN_SEQUENCE dojis (a doji makes it Scenario 3/4), and B1 keeps the
  highest high. A opens at or after t_conf; B3 closes at or before t_exp.
- SELL when B3 closes. SL = high(B1) + SL_BUFFER_POINTS. TP = fill - RR x (SL - fill),
  priced by the caller from the actual fill (backtest) or the live quote (bridge).

Prices are compared as integer points, never as raw floats.
The same engine runs the backtest and the live bridge (plan.md §3.2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import config
from .models import Candle, TradeSignal

logger = logging.getLogger("sell_scenarios")

M1 = timedelta(minutes=1)
HTF_DELTAS: Dict[str, timedelta] = {"M5": timedelta(minutes=5), "M15": timedelta(minutes=15)}
HTF_PRIORITY: Dict[str, int] = {"M15": 0, "M5": 1}  # a 15m setup labels the trade before a 5m one
UTC_PLUS_6 = timezone(timedelta(hours=6), "UTC+6")  # the trader's TradingView chart time zone
ENTRY_FILLS = ("next_bar_open", "b3_close")


class CandleKind(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    DOJI = "DOJI"


class TopPattern(str, Enum):
    NONE = "NONE"
    EQUAL_TOP = "EQUAL_TOP"
    WICK_SWEEP = "WICK_SWEEP"


class SkipReason(str, Enum):
    SCENARIO_DISABLED = "SCENARIO_DISABLED"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    POSITION_OPEN = "POSITION_OPEN"
    FILL_AT_OR_ABOVE_SL = "FILL_AT_OR_ABOVE_SL"  # backtest: the entry's ask (fill + spread) is at or above the SL
    NO_NEXT_BAR = "NO_NEXT_BAR"  # backtest: the feed has a gap before the fill bar


def to_points(price: float, point_size: float) -> int:
    """pts(p) = round(p / point_size)."""
    return int(round(price / point_size))


def from_points(points: int, point_size: float) -> float:
    return round(points * point_size, _decimals(point_size))


def _decimals(point_size: float) -> int:
    text = f"{point_size:.10f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


def time_fields(name: str, ts: datetime) -> Dict[str, str]:
    """`<name>_utc` and `<name>_utc6` for a timestamp (the data feed's time zone is UTC)."""
    utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    return {
        f"{name}_utc": f"{utc:%Y-%m-%d %H:%M}",
        f"{name}_utc6": f"{utc.astimezone(UTC_PLUS_6):%Y-%m-%d %H:%M}",
    }


@dataclass(frozen=True, slots=True)
class PointCandle:
    """A closed candle with its prices in integer points."""
    candle: Candle
    open: int
    high: int
    low: int
    close: int

    @classmethod
    def of(cls, candle: Candle, point_size: float) -> PointCandle:
        return cls(
            candle=candle,
            open=to_points(candle.open, point_size),
            high=to_points(candle.high, point_size),
            low=to_points(candle.low, point_size),
            close=to_points(candle.close, point_size),
        )

    @property
    def timestamp(self) -> datetime:
        return self.candle.timestamp


def candle_kind(c: PointCandle, doji_tol_pts: int = 0) -> CandleKind:
    """Spec §3.1, in order: a doji is never counted as bullish or bearish."""
    if abs(c.close - c.open) <= doji_tol_pts:
        return CandleKind.DOJI
    return CandleKind.BULL if c.close > c.open else CandleKind.BEAR


def top_pattern(x: PointCandle, y: PointCandle, tol_pts: int, doji_tol_pts: int = 0) -> TopPattern:
    """Spec §3.2 for adjacent closed candles: X must be bullish; only Y's upper wick may pass X's high."""
    if candle_kind(x, doji_tol_pts) is not CandleKind.BULL:
        return TopPattern.NONE
    if abs(y.high - x.high) <= tol_pts:
        return TopPattern.EQUAL_TOP
    if y.high > x.high + tol_pts and y.open <= x.high and y.close < x.high:
        return TopPattern.WICK_SWEEP
    return TopPattern.NONE


@dataclass(frozen=True)
class SellScenarioParams:
    """SELL_STRATEGY_PROMPT.md §7 (defaults are the config.py constants) plus the symbol's pip and point size."""

    enabled_scenarios: Tuple[int, ...] = config.SELL_ENABLED_SCENARIOS
    htf_timeframes: Tuple[str, ...] = tuple(config.HTF)
    rr: float = float(config.RR_MULTIPLE)
    htf_eq_tol_pips: float = config.SELL_HTF_EQ_TOL_PIPS
    ltf_eq_tol_pips: float = config.SELL_LTF_EQ_TOL_PIPS
    doji_body_tol_pips: float = config.SELL_DOJI_BODY_TOL_PIPS
    max_doji_in_sequence: int = config.SELL_MAX_DOJI_IN_SEQUENCE
    sl_buffer_points: int = config.SELL_SL_BUFFER_POINTS
    b1_must_be_highest: bool = config.SELL_B1_MUST_BE_HIGHEST
    htf_setup_expiry_bars: int = config.SELL_HTF_SETUP_EXPIRY_BARS
    invalidate_on_close_above_htf_high: bool = config.SELL_INVALIDATE_ON_CLOSE_ABOVE_HTF_HIGH
    ltf_near_htf_high_pips: Optional[float] = config.SELL_LTF_NEAR_HTF_HIGH_PIPS
    max_trades_per_setup: int = config.SELL_MAX_TRADES_PER_SETUP
    max_open_positions: Optional[int] = config.SELL_MAX_OPEN_POSITIONS
    entry_fill: str = config.SELL_ENTRY_FILL
    same_bar_sl_tp: str = config.SELL_SAME_BAR_SL_TP
    max_1m_gap_minutes: int = config.SELL_MAX_1M_GAP_MINUTES
    session_filter_enabled: bool = True
    session_start_hour: int = config.SELL_SESSION_START_HOUR
    session_end_hour: int = config.SELL_SESSION_END_HOUR
    session_weekdays: Tuple[int, ...] = config.SELL_SESSION_WEEKDAYS
    pip_size: float = 0.0001
    point_size: float = 0.00001

    def __post_init__(self) -> None:
        if not set(self.enabled_scenarios) <= {1, 2, 3, 4}:
            raise ValueError(f"enabled_scenarios must be within 1-4 (got {self.enabled_scenarios})")
        if not self.htf_timeframes or not set(self.htf_timeframes) <= set(HTF_DELTAS):
            raise ValueError(f"htf_timeframes must be M5 and/or M15 (got {self.htf_timeframes})")
        if self.rr <= 0:
            raise ValueError(f"rr must be positive (got {self.rr})")
        if min(self.htf_eq_tol_pips, self.ltf_eq_tol_pips, self.doji_body_tol_pips) < 0:
            raise ValueError("Equal-top and doji tolerances cannot be negative")
        if self.max_doji_in_sequence < 0 or self.sl_buffer_points < 0:
            raise ValueError("max_doji_in_sequence and sl_buffer_points cannot be negative")
        if self.htf_setup_expiry_bars < 1 or self.max_trades_per_setup < 1:
            raise ValueError("htf_setup_expiry_bars and max_trades_per_setup must be >= 1")
        if self.max_open_positions is not None and self.max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1, or None for no limit")
        if self.ltf_near_htf_high_pips is not None and self.ltf_near_htf_high_pips < 0:
            raise ValueError("ltf_near_htf_high_pips cannot be negative (None turns the filter off)")
        if self.entry_fill not in ENTRY_FILLS:
            raise ValueError(f"entry_fill must be one of {ENTRY_FILLS} (got {self.entry_fill!r})")
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
    def for_symbol(cls, symbol: str, **overrides: Any) -> SellScenarioParams:
        """Pip and point size from the symbol: JPY quotes have 3 digits, the others 5."""
        if "JPY" in symbol.upper():
            overrides = {"pip_size": 0.01, "point_size": 0.001, **overrides}
        return cls(**overrides)

    @classmethod
    def from_app_config(cls, cfg: Any, symbol: str) -> SellScenarioParams:
        """Live parameters: the session and position limit come from the AppConfig the guardrails use."""
        return cls.for_symbol(
            symbol,
            session_filter_enabled=cfg.session_filter_enabled,
            session_start_hour=cfg.session_start_hour,
            session_end_hour=cfg.session_end_hour,
            max_open_positions=cfg.max_open_trades,
        )


@dataclass(frozen=True)
class HtfSetup:
    """An armed HTF pattern (spec §5.4)."""
    setup_id: str
    timeframe: str
    pattern: TopPattern
    x: Candle
    y: Candle
    setup_high: float
    setup_high_pts: int
    t_conf: datetime
    t_exp: datetime


@dataclass(frozen=True)
class SellDecision:
    """A 1m sequence that matched an armed setup: a SELL signal, or a skip with its reason."""
    scenario: int
    setup: HtfSetup
    matching_setup_ids: Tuple[str, ...]
    ltf_pattern: TopPattern
    a: Candle
    b1: Candle
    b2: Candle
    b3: Candle
    doji_positions: Tuple[int, ...]
    stop_loss: float
    skip_reason: Optional[SkipReason] = None
    signal: Optional[TradeSignal] = None

    @property
    def signal_time(self) -> datetime:
        """close_time(B3): the moment the sell is placed."""
        return self.b3.timestamp + M1

    @property
    def doji_position(self) -> str:
        return "/".join(str(i) for i in self.doji_positions) or "none"

    def to_record(self) -> Dict[str, Any]:
        """Journal fields (spec §10) known when B3 closes, with times in UTC and UTC+6."""
        s = self.setup
        record: Dict[str, Any] = {
            "event": "SIGNAL" if self.signal is not None else "SKIPPED",
            "scenario": self.scenario,
            "htf_tf": s.timeframe,
            "htf_pattern": s.pattern.value,
            "setup_id": s.setup_id,
            "setup_high": s.setup_high,
            "ltf_pattern": self.ltf_pattern.value,
            "doji_position": self.doji_position,
            "sl": self.stop_loss,
            "matching_setup_ids": "|".join(self.matching_setup_ids),
            "skip_reason": self.skip_reason.value if self.skip_reason is not None else "",
        }
        record.update(time_fields("htf_X_time", s.x.timestamp))
        record.update(time_fields("htf_Y_time", s.y.timestamp))
        record.update(time_fields("t_conf", s.t_conf))
        record.update(time_fields("t_exp", s.t_exp))
        record.update(time_fields("signal_time", self.signal_time))
        for name, c in (("A", self.a), ("B1", self.b1), ("B2", self.b2), ("B3", self.b3)):
            record.update(time_fields(f"{name}_time", c.timestamp))
            record.update({f"{name}_open": c.open, f"{name}_high": c.high, f"{name}_low": c.low, f"{name}_close": c.close})
        return record


def _normalize_timeframe(timeframe: str) -> str:
    tf = timeframe.upper().strip()
    return {"5M": "M5", "5": "M5", "15M": "M15", "15": "M15"}.get(tf, tf)


class SellScenarioEngine:
    """
    Streaming evaluation of closed candles. Feed HTF closes to on_htf_candle() and 1m closes
    to on_m1_candle() in close-time order, HTF first when they close together.

    A returned TradeSignal carries entry = close(B3) and the TP for that price; the backtest
    re-prices the TP from its fill and the bridge from the live quote (see tp_from_fill).
    In the live bridge, open positions are capped by the risk guardrail (MAX_OPEN_TRADES);
    the backtest passes its own open-position count to on_m1_candle().
    """

    tp_from_fill = True  # read by bridge/executor.py: price the TP from the live quote, not close(B3)

    def __init__(
        self,
        params: Optional[SellScenarioParams] = None,
        symbol: str = "USDCAD",
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.params = params or SellScenarioParams.for_symbol(symbol)
        self.symbol = symbol
        self.event_sink = event_sink
        self.reward_risk_ratio = self.params.rr
        # bridge/executor.py sets or reads these on every rule engine; they do not affect this strategy.
        self.spread_pips = 0.0
        self._m1_body_sum = 0.0
        self._m1_body_count = 0

        p = self.params
        self._htf_tol = p.pips_to_points(p.htf_eq_tol_pips)
        self._ltf_tol = p.pips_to_points(p.ltf_eq_tol_pips)
        self._doji_tol = p.pips_to_points(p.doji_body_tol_pips)
        self._near_pts = None if p.ltf_near_htf_high_pips is None else p.pips_to_points(p.ltf_near_htf_high_pips)
        self._max_gap = timedelta(minutes=p.max_1m_gap_minutes)
        self.reset()

    def reset(self) -> None:
        """Clear armed setups, candle history and the decision log."""
        self.decisions: List[SellDecision] = []
        self._armed: List[HtfSetup] = []
        self._trades_per_setup: Dict[str, int] = {}
        self._last_htf: Dict[str, PointCandle] = {}
        self._m1: List[PointCandle] = []
        self._warned_no_m1 = False

    @property
    def armed_setups(self) -> Tuple[HtfSetup, ...]:
        return tuple(self._armed)

    def on_htf_candle(self, raw_candle: Union[Candle, Dict[str, Any]], timeframe: str = "M5") -> Optional[HtfSetup]:
        """Ingest one closed HTF candle as Y; the previous candle of that timeframe is X (spec §5)."""
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
        if candle_kind(y, self._doji_tol) is not CandleKind.BEAR:
            return None
        pattern = top_pattern(x, y, self._htf_tol, self._doji_tol)
        if pattern is TopPattern.NONE:
            return None
        t_conf = y.timestamp + delta
        setup = HtfSetup(
            setup_id=f"{tf}@{y.timestamp:%Y-%m-%dT%H:%M}",
            timeframe=tf,
            pattern=pattern,
            x=x.candle,
            y=candle,
            setup_high=max(x.candle.high, candle.high),
            setup_high_pts=max(x.high, y.high),
            t_conf=t_conf,
            t_exp=t_conf + self.params.htf_setup_expiry_bars * delta,
        )
        self._armed.append(setup)
        return setup

    def on_m1_candle(self, raw_candle: Union[Candle, Dict[str, Any]], open_positions: int = 0) -> Optional[TradeSignal]:
        """Ingest one closed 1m candle as B3 of the candidate sequence (spec §8 on_1m_close)."""
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        c = PointCandle.of(candle, self.params.point_size)
        if self._m1:
            step = c.timestamp - self._m1[-1].timestamp
            if step <= timedelta(0):
                return None  # already seen
            if step > self._max_gap:
                self._m1.clear()  # feed outage: no sequence spans the gap
        self._m1.append(c)
        del self._m1[:-4]

        now = c.timestamp + M1
        self._armed = [s for s in self._armed if s.t_exp >= now]
        if self.params.invalidate_on_close_above_htf_high:
            self._armed = [s for s in self._armed if c.close <= s.setup_high_pts]
        live_ids = {s.setup_id for s in self._armed}
        self._trades_per_setup = {k: v for k, v in self._trades_per_setup.items() if k in live_ids}

        if len(self._m1) < 4 or not self._armed:
            return None
        return self._evaluate(open_positions)

    def evaluate_completed_candle(self, raw_candles: Sequence[Any]) -> None:
        """The bridge's single-timeframe path cannot run this strategy: it needs the M1 bar export."""
        if not self._warned_no_m1:
            logger.warning("Sell scenarios need the MT4 M1 bar export; no M1 file found, so no signals.")
            self._warned_no_m1 = True
        return None

    def _evaluate(self, open_positions: int) -> Optional[TradeSignal]:
        a, b1, b2, b3 = self._m1
        now = b3.timestamp + M1
        if candle_kind(a, self._doji_tol) is not CandleKind.BULL:
            return None
        kinds = [candle_kind(b, self._doji_tol) for b in (b1, b2, b3)]
        if CandleKind.BULL in kinds:
            return None
        dojis = tuple(i for i, kind in enumerate(kinds, start=1) if kind is CandleKind.DOJI)
        if len(dojis) > self.params.max_doji_in_sequence:
            return None
        ltf = top_pattern(a, b1, self._ltf_tol, self._doji_tol)
        if ltf is TopPattern.NONE:
            return None
        if self.params.b1_must_be_highest and max(b2.high, b3.high) > b1.high:
            return None

        matches = sorted(
            (s for s in self._armed if a.timestamp >= s.t_conf and now <= s.t_exp and self._near_htf_high(s, b1)),
            key=lambda s: (HTF_PRIORITY[s.timeframe], -s.t_conf.timestamp()),
        )
        if not matches:
            return None
        setup = matches[0]
        scenario = (1 if setup.pattern is TopPattern.EQUAL_TOP else 2) + (2 if dojis else 0)
        sl_pts = b1.high + self.params.sl_buffer_points
        decision = SellDecision(
            scenario=scenario,
            setup=setup,
            matching_setup_ids=tuple(s.setup_id for s in matches),
            ltf_pattern=ltf,
            a=a.candle,
            b1=b1.candle,
            b2=b2.candle,
            b3=b3.candle,
            doji_positions=dojis,
            stop_loss=from_points(sl_pts, self.params.point_size),
        )
        skip = self._skip_reason(scenario, b3.timestamp, open_positions)
        if skip is not None:
            self._record(replace(decision, skip_reason=skip))
            return None

        signal = self._signal(decision, b3, sl_pts)
        self._consume(setup)
        self._record(replace(decision, signal=signal))
        return signal

    def _near_htf_high(self, setup: HtfSetup, b1: PointCandle) -> bool:
        return self._near_pts is None or abs(b1.high - setup.setup_high_pts) <= self._near_pts

    def _skip_reason(self, scenario: int, b3_open: datetime, open_positions: int) -> Optional[SkipReason]:
        p = self.params
        if scenario not in p.enabled_scenarios:
            return SkipReason.SCENARIO_DISABLED
        if not self._in_session(b3_open):
            return SkipReason.OUTSIDE_SESSION
        if p.max_open_positions is not None and open_positions >= p.max_open_positions:
            return SkipReason.POSITION_OPEN
        return None

    def _in_session(self, b3_open: datetime) -> bool:
        """The existing session gate (07:00-21:00 UTC, Monday-Friday by default), on B3's open time."""
        p = self.params
        if not p.session_filter_enabled:
            return True
        utc = b3_open.replace(tzinfo=timezone.utc) if b3_open.tzinfo is None else b3_open.astimezone(timezone.utc)
        return utc.weekday() in p.session_weekdays and p.session_start_hour <= utc.hour < p.session_end_hour

    def _signal(self, decision: SellDecision, b3: PointCandle, sl_pts: int) -> TradeSignal:
        p = self.params
        risk_pts = sl_pts - b3.close
        tp_pts = b3.close - int(round(p.rr * risk_pts))
        return TradeSignal(
            direction="SELL",
            entry_price=b3.candle.close,
            stop_loss=decision.stop_loss,
            take_profit=from_points(tp_pts, p.point_size),
            risk_distance=from_points(risk_pts, p.point_size),
            reward_distance=from_points(b3.close - tp_pts, p.point_size),
            reward_risk_ratio=p.rr,
            sweep_type=f"SELL_S{decision.scenario}",
            timestamp=b3.timestamp,
            sweep_timeframe=decision.setup.timeframe,
            timeframe="M1",
            extreme_price=decision.setup.setup_high,
        )

    def _consume(self, setup: HtfSetup) -> None:
        count = self._trades_per_setup.get(setup.setup_id, 0) + 1
        self._trades_per_setup[setup.setup_id] = count
        if count >= self.params.max_trades_per_setup:
            self._armed = [s for s in self._armed if s.setup_id != setup.setup_id]

    def _record(self, decision: SellDecision) -> None:
        self.decisions.append(decision)
        if self.event_sink is None:
            return
        try:
            self.event_sink(decision.to_record())
        except Exception as exc:  # journaling must never block a trade
            logger.error(f"Sell scenario journal write failed: {exc}")
