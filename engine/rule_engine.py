"""
Core Rule Engine for AK Forex Trading System.

Pure Python, zero-dependency algorithmic execution engine.
Evaluates closed OHLC candles sequentially without intrabar tick data or future look-ahead.
Directly implements:
- Multi-timeframe liquidity sweep detection (5-minute and 15-minute bars).
- 1-minute 3-consecutive-candle directional confirmation.
- 15-candle armed-state watch window with disarm on direction break or expiry.
- Asymmetrical Stop-Loss (highest high for Sell, lowest low for Buy across the 3 confirming candles).
- 10:1 Reward-to-Risk mathematical pricing (Entry = C3.close, TP = Entry ± 10x SL).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .models import ArmedState, Candle, Direction, SweepEvent, SweepType, TradeSignal
from .sweep_detector import detect_sweep, detect_variant_a, detect_variant_b
from .confirmation import evaluate_confirmation, evaluate_3_candles


def resample_m1_to_htf(m1_candles: Sequence[Candle], timeframe_minutes: int) -> List[Candle]:
    """
    Resample a sequence of M1 closed candles into higher-timeframe (e.g. M5 or M15) closed candles.
    Aligns to clock intervals (0, 5, 10, ... or 0, 15, 30, ...).
    Zero look-ahead: an HTF bar is only output once its constituent M1 bars have closed.
    """
    if not m1_candles:
        return []

    htf_bars: List[Candle] = []
    bucket_candles: List[Candle] = []
    current_bucket_key: Optional[datetime] = None

    for c in m1_candles:
        minute = c.timestamp.minute
        bucket_minute = (minute // timeframe_minutes) * timeframe_minutes
        bucket_time = c.timestamp.replace(minute=bucket_minute, second=0, microsecond=0)

        if current_bucket_key is None:
            current_bucket_key = bucket_time
            bucket_candles = [c]
        elif bucket_time == current_bucket_key:
            bucket_candles.append(c)
        else:
            if bucket_candles:
                htf_candle = Candle(
                    timestamp=current_bucket_key,
                    open=bucket_candles[0].open,
                    high=max(b.high for b in bucket_candles),
                    low=min(b.low for b in bucket_candles),
                    close=bucket_candles[-1].close,
                    volume=sum(b.volume for b in bucket_candles),
                )
                htf_bars.append(htf_candle)
            current_bucket_key = bucket_time
            bucket_candles = [c]

    # Handle the final bucket if it has bars
    if bucket_candles:
        htf_candle = Candle(
            timestamp=current_bucket_key,
            open=bucket_candles[0].open,
            high=max(b.high for b in bucket_candles),
            low=min(b.low for b in bucket_candles),
            close=bucket_candles[-1].close,
            volume=sum(b.volume for b in bucket_candles),
        )
        htf_bars.append(htf_candle)

    return htf_bars


class RuleEngine:
    """
    Deterministic trading rule engine supporting both multi-timeframe streaming (HTF sweep + M1 confirmation)
    and single-timeframe historical walk. Operates exclusively on closed bars.
    """

    def __init__(
        self,
        allow_variant_a: bool = True,
        allow_variant_b: bool = True,
        swing_lookback: int = 20,
        swing_strength: int = 2,
        buffer_pips: float = 0.0,
        spread_pips: float = 0.0,
        pip_size: float = 0.0001,
        min_risk_pips: float = 1.0,
        check_m5: bool = True,
        check_m15: bool = True,
        max_watch_candles: int = 15,
        disarm_on_break: bool = True,
        reward_risk_ratio: float = 5.0,
    ) -> None:
        self.allow_variant_a = allow_variant_a
        self.allow_variant_b = allow_variant_b
        self.swing_lookback = swing_lookback
        self.swing_strength = swing_strength
        self.buffer_pips = buffer_pips
        self.spread_pips = spread_pips
        self.pip_size = pip_size
        self.min_risk_pips = min_risk_pips
        self.check_m5 = check_m5
        self.check_m15 = check_m15
        self.max_watch_candles = max_watch_candles
        self.disarm_on_break = disarm_on_break
        self.reward_risk_ratio = reward_risk_ratio

        # State tracking for multi-timeframe streaming
        self.armed_state: Optional[ArmedState] = None
        self._htf_history: Dict[str, List[Candle]] = {"M5": [], "M15": []}
        self._m1_history: List[Candle] = []

    @property
    def is_armed(self) -> bool:
        """True if currently watching the 1-minute chart for confirmation."""
        return self.armed_state is not None and not self.armed_state.is_expired

    def arm(
        self,
        direction: Direction,
        sweep_candle: Candle,
        sweep_timeframe: str,
        swept_level: float,
        extreme_price: float,
        sweep_type: str = "VARIANT_A",
    ) -> ArmedState:
        """Arm the 1-minute confirmation watch state."""
        self.armed_state = ArmedState(
            direction=direction,
            sweep_timeframe=sweep_timeframe,
            sweep_candle=sweep_candle,
            swept_level=swept_level,
            extreme_price=extreme_price,
            armed_at_timestamp=sweep_candle.timestamp,
            candles_watched=0,
            max_watch_candles=self.max_watch_candles,
            confirming_candles=[],
        )
        return self.armed_state

    def disarm(self) -> None:
        """Disarm and resume waiting for a higher-timeframe sweep."""
        self.armed_state = None

    def reset(self) -> None:
        """Reset all active state and candle histories."""
        self.disarm()
        self._htf_history = {"M5": [], "M15": []}
        self._m1_history = []

    def _coerce_candles(self, raw_candles: Sequence[Union[Candle, Dict[str, Any]]]) -> List[Candle]:
        """Convert input sequence into a list of verified Candle objects."""
        candles: List[Candle] = []
        for item in raw_candles:
            if isinstance(item, Candle):
                candles.append(item)
            elif isinstance(item, dict):
                candles.append(Candle.from_dict(item))
            else:
                raise TypeError(f"Expected Candle or dict, got {type(item)}")
        return candles

    # -------------------------------------------------------------------------
    # Multi-Timeframe Streaming Interface (Phase 1 Specification)
    # -------------------------------------------------------------------------

    def on_htf_candle(
        self,
        raw_candle: Union[Candle, Dict[str, Any]],
        timeframe: str = "M5",
    ) -> Optional[ArmedState]:
        """
        Ingest a closed higher-timeframe candle (5-min or 15-min).
        Evaluates whether a liquidity sweep occurred:
        - Bullish sweep (seeking BUY): current candle is bullish, prior was bearish,
          current wick extends below prior low, closes back at/above prior low.
        - Bearish sweep (seeking SELL): current candle is bearish, prior was bullish,
          current wick extends above prior high, closes back at/below prior high.
        If yes, arms the 1-minute confirmation watch state.
        """
        tf = timeframe.upper().strip()
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        history = self._htf_history.setdefault(tf, [])

        if len(history) >= 1:
            prev = history[-1]
            sweep_event: Optional[SweepEvent] = None

            # Check Variant A: Candle-to-Candle liquidity sweep of prior opposite candle
            if self.allow_variant_a:
                # Bullish sweep check
                if prev.is_bearish and candle.is_bullish:
                    if candle.low < prev.low and candle.close >= prev.low:
                        sweep_event = SweepEvent(
                            sweep_type=SweepType.VARIANT_A,
                            direction=Direction.BUY,
                            candle_index=len(history),
                            sweep_candle=candle,
                            swept_level=prev.low,
                            extreme_price=candle.low,
                        )
                # Bearish sweep check
                elif prev.is_bullish and candle.is_bearish:
                    if candle.high > prev.high and candle.close <= prev.high:
                        sweep_event = SweepEvent(
                            sweep_type=SweepType.VARIANT_A,
                            direction=Direction.SELL,
                            candle_index=len(history),
                            sweep_candle=candle,
                            swept_level=prev.high,
                            extreme_price=candle.high,
                        )

            # Check Variant B: Swing-level sweep if Variant A did not trigger
            if sweep_event is None and self.allow_variant_b and len(history) >= (self.swing_strength * 2 + 1):
                max_needed = self.swing_lookback + (self.swing_strength * 2) + 5
                window = history[-max_needed:] + [candle]
                sweep_event = detect_variant_b(
                    window,
                    current_idx=len(window) - 1,
                    lookback=self.swing_lookback,
                    swing_strength=self.swing_strength,
                )

            if sweep_event is not None:
                self.arm(
                    direction=sweep_event.direction,
                    sweep_candle=candle,
                    sweep_timeframe=tf,
                    swept_level=sweep_event.swept_level,
                    extreme_price=sweep_event.extreme_price,
                    sweep_type=sweep_event.sweep_type.value,
                )

        history.append(candle)
        if len(history) > 100:
            del history[:-100]
        return self.armed_state if self.is_armed else None

    def on_m1_candle(
        self,
        raw_candle: Union[Candle, Dict[str, Any]],
    ) -> Optional[TradeSignal]:
        """
        Ingest a closed 1-minute candle.
        If armed:
        - Evaluates consecutive same-direction candles (all bullish for BUY, all bearish for SELL).
        - If 3 consecutive candles complete:
            entry = candle.close
            stop_loss = highest high (Sell) or lowest low (Buy) across all 3 candles (+ spread/buffer)
            take_profit = entry ± (10 * stop_distance)
            disarms and returns TradeSignal.
        - If a candle breaks the required direction before 3 form:
            disarms immediately (or resets streak if disarm_on_break=False).
        - If 15 candles elapse without 3 consecutive candles forming:
            disarms due to expiry.
        """
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        self._m1_history.append(candle)
        if len(self._m1_history) > 100:
            del self._m1_history[:-100]

        if self.armed_state is None:
            return None

        # Ignore 1m candles that closed before or at the sweep candle's close time
        tf_mins = 15 if self.armed_state.sweep_timeframe == "M15" else 5
        sweep_close_time = self.armed_state.sweep_candle.timestamp + timedelta(minutes=tf_mins)
        if candle.timestamp < sweep_close_time:
            return None

        self.armed_state.candles_watched += 1

        is_matching = False
        if self.armed_state.direction == Direction.BUY:
            is_matching = candle.is_bullish
        elif self.armed_state.direction == Direction.SELL:
            is_matching = candle.is_bearish

        if is_matching:
            self.armed_state.confirming_candles.append(candle)
            if len(self.armed_state.confirming_candles) == 3:
                # 3 consecutive confirming candles complete
                signal = evaluate_3_candles(
                    confirming_candles=self.armed_state.confirming_candles,
                    direction=self.armed_state.direction,
                    buffer_pips=self.buffer_pips,
                    pip_size=self.pip_size,
                    spread_pips=self.spread_pips,
                    sweep_type="SWEEP_" + self.armed_state.sweep_timeframe,
                    sweep_timeframe=self.armed_state.sweep_timeframe,
                    reward_risk_ratio=self.reward_risk_ratio,
                )
                self.disarm()
                if signal is not None:
                    min_risk_distance = self.min_risk_pips * self.pip_size
                    if signal.risk_distance < min_risk_distance:
                        return None
                return signal
        else:
            # Direction broke before 3 formed
            if self.disarm_on_break:
                self.disarm()
                return None
            else:
                self.armed_state.confirming_candles.clear()

        # Check expiry
        if self.armed_state and self.armed_state.is_expired:
            self.disarm()
            return None

        return None

    def feed_candle(
        self,
        timeframe: str,
        raw_candle: Union[Candle, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Unified ingress for multi-timeframe candle streams.
        timeframe: "M1", "M5", or "M15".
        Returns None or {direction, entry_price, stop_loss, take_profit, ...} if an M1 candle triggers an order.
        """
        tf = timeframe.upper().strip()
        if tf in ("M5", "5M", "5"):
            self.on_htf_candle(raw_candle, timeframe="M5")
            return None
        elif tf in ("M15", "15M", "15"):
            self.on_htf_candle(raw_candle, timeframe="M15")
            return None
        elif tf in ("M1", "1M", "1"):
            sig = self.on_m1_candle(raw_candle)
            return sig.to_dict() if sig else None
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Expected M1, M5, or M15.")

    def scan_multitimeframe_streams(
        self,
        m1_candles: Sequence[Union[Candle, Dict[str, Any]]],
        m5_candles: Optional[Sequence[Union[Candle, Dict[str, Any]]]] = None,
        m15_candles: Optional[Sequence[Union[Candle, Dict[str, Any]]]] = None,
    ) -> List[TradeSignal]:
        """
        Event-driven chronological replay across multi-timeframe streams.
        If m5_candles or m15_candles are not provided, automatically resamples them from m1_candles.
        Evaluates closed candles strictly in market time order without look-ahead bias.
        """
        self.reset()
        m1 = self._coerce_candles(m1_candles)
        m5 = self._coerce_candles(m5_candles) if m5_candles is not None else (resample_m1_to_htf(m1, 5) if self.check_m5 else [])
        m15 = self._coerce_candles(m15_candles) if m15_candles is not None else (resample_m1_to_htf(m1, 15) if self.check_m15 else [])

        # Priority: HTF closes before M1 when timestamps coincide
        events: List[Tuple[datetime, int, str, Candle]] = []

        if self.check_m15:
            for c in m15:
                close_time = c.timestamp + timedelta(minutes=15)
                events.append((close_time, 0, "M15", c))

        if self.check_m5:
            for c in m5:
                close_time = c.timestamp + timedelta(minutes=5)
                events.append((close_time, 1, "M5", c))

        for c in m1:
            close_time = c.timestamp + timedelta(minutes=1)
            events.append((close_time, 2, "M1", c))

        events.sort(key=lambda x: (x[0], x[1]))

        signals: List[TradeSignal] = []
        for close_time, priority, tf, c in events:
            if tf in ("M5", "M15"):
                self.on_htf_candle(c, timeframe=tf)
            elif tf == "M1":
                sig = self.on_m1_candle(c)
                if sig is not None:
                    signals.append(sig)

        return signals

    # -------------------------------------------------------------------------
    # Backward-Compatible Single-Timeframe Interface
    # -------------------------------------------------------------------------

    def evaluate_at_index(
        self,
        candles: List[Candle],
        sweep_idx: int,
    ) -> Optional[TradeSignal]:
        """
        Check if a sweep occurred at sweep_idx and if subsequent 3 candles form confirmation.
        Retained for single-timeframe backward compatibility.
        """
        if sweep_idx < 1:
            return None

        sweep_event = detect_sweep(
            candles=candles,
            current_idx=sweep_idx,
            allow_variant_a=self.allow_variant_a,
            allow_variant_b=self.allow_variant_b,
            swing_lookback=self.swing_lookback,
            swing_strength=self.swing_strength,
        )
        if sweep_event is None:
            return None

        signal = evaluate_confirmation(
            candles=candles,
            sweep_event=sweep_event,
            buffer_pips=self.buffer_pips,
            pip_size=self.pip_size,
            spread_pips=self.spread_pips,
            reward_risk_ratio=self.reward_risk_ratio,
        )
        if signal is None:
            return None

        min_risk_distance = self.min_risk_pips * self.pip_size
        if signal.risk_distance < min_risk_distance:
            return None

        return signal

    def evaluate_completed_candle(
        self,
        raw_candles: Sequence[Union[Candle, Dict[str, Any]]],
    ) -> Optional[TradeSignal]:
        """
        Evaluates whether the MOST RECENT closed candle (index len - 1) is Candle 3
        completing a valid 3-candle confirmation sequence from a sweep at (len - 4).
        """
        candles = self._coerce_candles(raw_candles)
        if len(candles) < 5:
            return None

        last_idx = len(candles) - 1
        sweep_idx = last_idx - 3

        return self.evaluate_at_index(candles, sweep_idx)

    def scan_historical_signals(
        self,
        raw_candles: Sequence[Union[Candle, Dict[str, Any]]],
    ) -> List[TradeSignal]:
        """
        Walks chronologically through a series of single-timeframe closed candles.
        """
        candles = self._coerce_candles(raw_candles)
        signals: List[TradeSignal] = []
        n = len(candles)

        if n < 5:
            return signals

        i = 1
        while i <= n - 4:
            signal = self.evaluate_at_index(candles, sweep_idx=i)
            if signal is not None:
                signals.append(signal)
                i += 4
            else:
                i += 1

        return signals


# Alias for explicit multi-timeframe references
MultiTimeframeRuleEngine = RuleEngine


def evaluate_candles(
    candles: Sequence[Union[Candle, Dict[str, Any]]],
    allow_variant_a: bool = True,
    allow_variant_b: bool = True,
    swing_lookback: int = 20,
    swing_strength: int = 2,
    buffer_pips: float = 0.0,
    spread_pips: float = 0.0,
    pip_size: float = 0.0001,
    reward_risk_ratio: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """
    Top-level specification interface.
    Takes an array of closed OHLC candles and returns either None or
    {direction, entry_price, stop_loss, take_profit, ...}.
    """
    engine = RuleEngine(
        allow_variant_a=allow_variant_a,
        allow_variant_b=allow_variant_b,
        swing_lookback=swing_lookback,
        swing_strength=swing_strength,
        buffer_pips=buffer_pips,
        spread_pips=spread_pips,
        pip_size=pip_size,
        reward_risk_ratio=reward_risk_ratio,
    )
    signal = engine.evaluate_completed_candle(candles)
    if signal is None:
        return None
    return signal.to_dict()
