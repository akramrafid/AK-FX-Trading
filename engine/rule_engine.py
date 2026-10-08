"""
Core Rule Engine for AK Forex Trading System.

Pure Python, zero-dependency algorithmic execution engine.
Evaluates closed OHLC candles sequentially without intrabar tick data or future look-ahead.
Directly implements:
- Multi-timeframe liquidity sweep detection (5-minute and 15-minute bars).
- 1-minute 3-consecutive-candle directional confirmation.
- 15-candle armed-state watch window with disarm on direction break or expiry.
- Asymmetrical Stop-Loss (highest high for Sell, lowest low for Buy across the 3 confirming candles).
- 5:1 Reward-to-Risk mathematical pricing (Entry = C3.close, TP = Entry ± 5x SL).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .models import ArmedState, Candle, Direction, SweepEvent, SweepType, TradeSignal
from .sweep_detector import detect_sweep, detect_variant_a, detect_variant_b, detect_key_liquidity_sweep
from .confirmation import evaluate_confirmation, evaluate_3_candles

TIMEFRAME_DELTAS = {
    "M1": timedelta(minutes=1),
    "M5": timedelta(minutes=5),
    "M15": timedelta(minutes=15),
    "H1": timedelta(hours=1),
}


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
        # Institutional Enhancements (Pillars 1 - 5)
        anchor_to_key_liquidity: bool = False,
        min_sweep_pips: float = 0.0,
        use_sweep_wick_sl: bool = False,
        use_c1_only_sl: bool = False,
        min_displacement_ratio: float = 0.0,
        h1_trend_filter: bool = False,
        session_filter: bool = False,
        session_start_hour: int = 7,
        session_end_hour: int = 21,
        symbol: str = "EURUSD",
        partial_bank_r: Optional[float] = None,
        partial_bank_pct: Optional[float] = None,
        breakeven_trigger_r: Optional[float] = None,
        enable_intrabar_sweep: bool = False,
    ) -> None:
        self.symbol = symbol
        self.allow_variant_a = allow_variant_a
        self.allow_variant_b = allow_variant_b
        self.swing_lookback = swing_lookback
        self.swing_strength = swing_strength
        self.buffer_pips = buffer_pips
        self.spread_pips = spread_pips
        if "JPY" in symbol.upper():
            self.pip_size = 0.01
        else:
            self.pip_size = pip_size
        self.min_risk_pips = min_risk_pips
        self.check_m5 = check_m5
        self.check_m15 = check_m15
        self.max_watch_candles = max_watch_candles
        self.disarm_on_break = disarm_on_break
        self.reward_risk_ratio = reward_risk_ratio

        # Institutional & Strategy configuration
        self.anchor_to_key_liquidity = anchor_to_key_liquidity
        self.min_sweep_pips = min_sweep_pips
        self.use_sweep_wick_sl = use_sweep_wick_sl
        self.use_c1_only_sl = use_c1_only_sl
        self.min_displacement_ratio = min_displacement_ratio
        self.h1_trend_filter = h1_trend_filter
        self.session_filter = session_filter
        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.partial_bank_r = partial_bank_r
        self.partial_bank_pct = partial_bank_pct
        self.breakeven_trigger_r = breakeven_trigger_r
        self.enable_intrabar_sweep = enable_intrabar_sweep

        # State tracking for multi-timeframe streaming
        self.armed_state: Optional[ArmedState] = None
        self._htf_history: Dict[str, List[Candle]] = {"M5": [], "M15": []}
        self._m1_history: List[Candle] = []

        # Session & Key Levels (Asian Session 00:00-07:00 UTC & Previous Day High/Low)
        self.asia_high: Optional[float] = None
        self.asia_low: Optional[float] = None
        self.pdh: Optional[float] = None
        self.pdl: Optional[float] = None
        self._current_day = None
        self._day_high: Optional[float] = None
        self._day_low: Optional[float] = None

        # Rolling M1 body metrics for displacement confirmation
        self._m1_body_sum: float = 0.0
        self._m1_body_count: int = 0

        # Rolling M5 and M15 aggregation from M1 closed bars
        self._curr_m5_key: Optional[datetime] = None
        self._curr_m5_buf: List[Candle] = []
        self._curr_m15_key: Optional[datetime] = None
        self._curr_m15_buf: List[Candle] = []

        # H1 aggregation & running 50 EMA
        self._curr_h1_key: Optional[datetime] = None
        self._curr_h1_buf: List[Candle] = []
        self._h1_candles: List[Candle] = []
        self._h1_closes: List[float] = []
        self.latest_h1_ema: Optional[float] = None
        self._traded_m15_keys: set[datetime] = set()
        self._traded_m5_keys: set[datetime] = set()
        self._last_htf_sweep_direction: Optional[Direction] = None
        self._last_htf_sweep_tf: Optional[str] = None
        self._last_htf_sweep_time: Optional[datetime] = None

    @classmethod
    def institutional_preset(
        cls,
        symbol: str = "EURUSD",
        anchor_to_key_liquidity: bool = True,
        use_sweep_wick_sl: bool = True,
        min_sweep_pips: float = 2.0,
        min_risk_pips: float = 6.0,
        min_displacement_ratio: float = 1.2,
        h1_trend_filter: bool = True,
        reward_risk_ratio: float = 5.0,
        partial_bank_r: float = 2.0,
        partial_bank_pct: float = 0.70,
        breakeven_trigger_r: float = 2.0,
        session_filter: bool = True,
        session_start_hour: int = 7,
        session_end_hour: int = 21,
        check_m5: bool = True,
        check_m15: bool = True,
        **kwargs,
    ) -> RuleEngine:
        """
        Factory constructor implementing the 5 institutional pillars:
        1. Key liquidity pool sweeps (Asian Range & PDH/PDL with >= 2.0 pip penetration).
        2. True invalidation Stop-Loss anchored at HTF sweep extreme wick (+ spread/buffer).
        3. M1 displacement confirmation (at least one candle body >= 1.2x average M1 body).
        4. Higher timeframe trend alignment (H1 50 EMA filter).
        5. Dynamic trade management (bank 70% at +2.0R, move SL to breakeven, runner to +5.0R).
        """
        return cls(
            symbol=symbol,
            anchor_to_key_liquidity=anchor_to_key_liquidity,
            use_sweep_wick_sl=use_sweep_wick_sl,
            min_sweep_pips=min_sweep_pips,
            min_risk_pips=min_risk_pips,
            min_displacement_ratio=min_displacement_ratio,
            h1_trend_filter=h1_trend_filter,
            reward_risk_ratio=reward_risk_ratio,
            partial_bank_r=partial_bank_r,
            partial_bank_pct=partial_bank_pct,
            breakeven_trigger_r=breakeven_trigger_r,
            session_filter=session_filter,
            session_start_hour=session_start_hour,
            session_end_hour=session_end_hour,
            check_m5=check_m5,
            check_m15=check_m15,
            enable_intrabar_sweep=False,
            **kwargs,
        )

    @classmethod
    def c1_wickswap_preset(
        cls,
        symbol: str = "EURUSD",
        allow_variant_a: bool = True,
        allow_variant_b: bool = False,
        anchor_to_key_liquidity: bool = False,
        use_sweep_wick_sl: bool = False,
        use_c1_only_sl: bool = True,
        min_sweep_pips: float = 0.0,
        min_risk_pips: float = 0.0,
        min_displacement_ratio: float = 0.0,
        h1_trend_filter: bool = False,
        disarm_on_break: bool = False,
        reward_risk_ratio: float = 5.0,
        partial_bank_r: Optional[float] = None,
        partial_bank_pct: Optional[float] = 0.0,
        breakeven_trigger_r: float = 2.0,
        session_filter: bool = True,
        session_start_hour: int = 7,
        session_end_hour: int = 21,
        buffer_pips: float = 0.0,
        spread_pips: float = 0.0,
        check_m5: bool = True,
        check_m15: bool = True,
        enable_intrabar_sweep: bool = True,
        **kwargs,
    ) -> RuleEngine:
        """
        Factory constructor for C1 Wick-Swap strategy:
        - M5/M15 candle-to-candle wick sweep (Variant A, both BUY and SELL).
        - 1-minute 3-consecutive directional candle confirmation.
        - Stop-Loss anchored strictly to the top (SELL) or bottom (BUY) of the 3 consecutive 1-minute candles.
        - Fixed 1:5 Reward-to-Risk ratio.
        - Breakeven: At 1:2 RR (+2.0R), move SL strictly to entry price.
        """
        return cls(
            symbol=symbol,
            allow_variant_a=allow_variant_a,
            allow_variant_b=allow_variant_b,
            anchor_to_key_liquidity=anchor_to_key_liquidity,
            use_sweep_wick_sl=use_sweep_wick_sl,
            use_c1_only_sl=use_c1_only_sl,
            min_sweep_pips=min_sweep_pips,
            min_risk_pips=min_risk_pips,
            min_displacement_ratio=min_displacement_ratio,
            h1_trend_filter=h1_trend_filter,
            disarm_on_break=disarm_on_break,
            reward_risk_ratio=reward_risk_ratio,
            partial_bank_r=partial_bank_r,
            partial_bank_pct=partial_bank_pct,
            breakeven_trigger_r=breakeven_trigger_r,
            session_filter=session_filter,
            session_start_hour=session_start_hour,
            session_end_hour=session_end_hour,
            buffer_pips=buffer_pips,
            spread_pips=spread_pips,
            check_m5=check_m5,
            check_m15=check_m15,
            enable_intrabar_sweep=enable_intrabar_sweep,
            **kwargs,
        )

    def _update_daily_and_session_levels(self, candle: Candle) -> None:
        """Update daily running high/low, PDH/PDL, and Asian Session high/low."""
        dt = candle.timestamp
        date = dt.date()
        if self._current_day != date:
            if self._current_day is not None:
                self.pdh = self._day_high
                self.pdl = self._day_low
            self._current_day = date
            self._day_high = candle.high
            self._day_low = candle.low
            self.asia_high = None
            self.asia_low = None
        else:
            self._day_high = max(self._day_high, candle.high) if self._day_high is not None else candle.high
            self._day_low = min(self._day_low, candle.low) if self._day_low is not None else candle.low

        if 0 <= dt.hour < 7:
            self.asia_high = candle.high if self.asia_high is None else max(self.asia_high, candle.high)
            self.asia_low = candle.low if self.asia_low is None else min(self.asia_low, candle.low)

    def on_h1_candle(self, raw_candle: Union[Candle, Dict[str, Any]]) -> None:
        """Ingest closed H1 candle and update running 50 EMA."""
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        self._h1_candles.append(candle)
        self._h1_closes.append(candle.close)
        if len(self._h1_closes) == 1:
            self.latest_h1_ema = candle.close
        else:
            mult = 2.0 / (50 + 1)
            self.latest_h1_ema = (candle.close - self.latest_h1_ema) * mult + self.latest_h1_ema

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
        is_intrabar: bool = False,
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
            is_intrabar=is_intrabar,
        )
        return self.armed_state

    def disarm(self) -> None:
        """Disarm and resume waiting for a higher-timeframe sweep."""
        self.armed_state = None

    def reset(self) -> None:
        """Reset all active state and candle histories."""
        self.disarm()
        self._htf_history = {"M5": [], "M15": []}
        self._traded_m15_keys = set()
        self._traded_m5_keys = set()
        self._m1_history = []
        self.asia_high = None
        self.asia_low = None
        self.pdh = None
        self.pdl = None
        self._current_day = None
        self._day_high = None
        self._day_low = None
        self._m1_body_sum = 0.0
        self._m1_body_count = 0
        self._curr_m5_key = None
        self._curr_m5_buf = []
        self._curr_m15_key = None
        self._curr_m15_buf = []
        self._curr_h1_key = None
        self._curr_h1_buf = []
        self._h1_candles = []
        self._h1_closes = []
        self.latest_h1_ema = None
        self._last_htf_sweep_direction = None
        self._last_htf_sweep_tf = None
        self._last_htf_sweep_time = None

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
        Ingest a closed higher-timeframe candle (5-min, 15-min, or 1-hour).
        Evaluates whether a liquidity sweep occurred:
        - Bullish sweep (seeking BUY): current candle is bullish, prior was bearish (or key low swept).
        - Bearish sweep (seeking SELL): current candle is bearish, prior was bullish (or key high swept).
        If yes, arms the 1-minute confirmation watch state.
        """
        tf = timeframe.upper().strip()
        candle = raw_candle if isinstance(raw_candle, Candle) else Candle.from_dict(raw_candle)
        self._update_daily_and_session_levels(candle)

        # Auto-disarm if existing armed state is stale from a previous day or > 2 hours old
        if self.armed_state is not None:
            time_diff = candle.timestamp - self.armed_state.armed_at_timestamp
            if candle.timestamp.date() != self.armed_state.armed_at_timestamp.date() or time_diff > timedelta(hours=2):
                self.disarm()

        if tf in ("H1", "1H", "60"):
            self.on_h1_candle(candle)
            return None

        if tf in ("M5", "5M", "5"):
            tf = "M5"
        elif tf in ("M15", "15M", "15"):
            tf = "M15"

        if tf == "M5" and not self.check_m5:
            return None
        if tf == "M15" and not self.check_m15:
            return None

        history = self._htf_history.setdefault(tf, [])
        if (tf == "M15" and candle.timestamp in self._traded_m15_keys) or (tf == "M5" and candle.timestamp in self._traded_m5_keys):
            if not history or candle.timestamp > history[-1].timestamp:
                history.append(candle)
            elif history and history[-1].timestamp == candle.timestamp:
                history[-1] = candle
            return None

        if history and candle.timestamp <= history[-1].timestamp:
            if history[-1].timestamp == candle.timestamp:
                history[-1] = candle
            return self.armed_state if self.is_armed else None

        in_session = True
        if self.session_filter:
            in_session = (self.session_start_hour <= candle.timestamp.hour < self.session_end_hour)

        if len(history) >= 1 and in_session:
            prev = history[-1]
            sweep_event: Optional[SweepEvent] = None

            # Institutional Pillar 1: Key Liquidity Pools (Asian High/Low & PDH/PDL)
            if self.anchor_to_key_liquidity:
                min_dist = self.min_sweep_pips * self.pip_size
                sweep_event = detect_key_liquidity_sweep(
                    candle=candle,
                    asia_high=self.asia_high,
                    asia_low=self.asia_low,
                    pdh=self.pdh,
                    pdl=self.pdl,
                    min_sweep_dist=min_dist,
                    candle_index=len(history),
                )
            else:
                # Standard Variant A: Candle-to-Candle liquidity sweep of prior opposite candle
                if self.allow_variant_a:
                    if prev.is_bearish and (candle.is_bullish or candle.close >= candle.open):
                        if candle.low < prev.low and candle.close >= prev.low:
                            sweep_event = SweepEvent(
                                sweep_type=SweepType.VARIANT_A,
                                direction=Direction.BUY,
                                candle_index=len(history),
                                sweep_candle=candle,
                                swept_level=prev.low,
                                extreme_price=candle.low,
                            )
                    elif prev.is_bullish and (candle.is_bearish or candle.close <= candle.open):
                        if candle.high > prev.high and candle.close <= prev.high:
                            sweep_event = SweepEvent(
                                sweep_type=SweepType.VARIANT_A,
                                direction=Direction.SELL,
                                candle_index=len(history),
                                sweep_candle=candle,
                                swept_level=prev.high,
                                extreme_price=candle.high,
                            )

                # Standard Variant B: Swing-level sweep if Variant A did not trigger
                if sweep_event is None and self.allow_variant_b and len(history) >= (self.swing_strength * 2 + 1):
                    max_needed = self.swing_lookback + (self.swing_strength * 2) + 5
                    window = history[-max_needed:] + [candle]
                    sweep_event = detect_variant_b(
                        window,
                        current_idx=len(window) - 1,
                        lookback=self.swing_lookback,
                        swing_strength=self.swing_strength,
                    )

            # Institutional Pillar 4: Higher-Timeframe Trend Filter (H1 50 EMA)
            if sweep_event is not None and self.h1_trend_filter and self.latest_h1_ema is not None:
                if sweep_event.direction == Direction.BUY and candle.close < self.latest_h1_ema:
                    sweep_event = None
                elif sweep_event.direction == Direction.SELL and candle.close > self.latest_h1_ema:
                    sweep_event = None

            if sweep_event is not None:
                if tf == "M15":
                    self._last_htf_sweep_direction = sweep_event.direction
                    self._last_htf_sweep_tf = "M15"
                    self._last_htf_sweep_time = candle.timestamp
                elif tf == "M5":
                    # Timeframe hierarchy: Do not allow counter-trend M5 sweep if an M15 sweep is active within the last 15 minutes
                    if (
                        self._last_htf_sweep_direction is not None
                        and self._last_htf_sweep_tf == "M15"
                        and self._last_htf_sweep_time is not None
                        and candle.timestamp < self._last_htf_sweep_time + timedelta(minutes=15)
                        and sweep_event.direction != self._last_htf_sweep_direction
                    ):
                        sweep_event = None

            if sweep_event is not None:
                # Priority protection: Do not overwrite an active M15 armed setup with a lower timeframe (M5) sweep
                if not (self.is_armed and self.armed_state.sweep_timeframe == "M15" and tf == "M5"):
                    # Preserve in-progress confirmation streak if already armed in same direction
                    if (
                        self.is_armed
                        and self.armed_state.direction == sweep_event.direction
                        and len(self.armed_state.confirming_candles) > 0
                    ):
                        if sweep_event.direction == Direction.SELL:
                            self.armed_state.extreme_price = max(self.armed_state.extreme_price, sweep_event.extreme_price)
                        else:
                            self.armed_state.extreme_price = min(self.armed_state.extreme_price, sweep_event.extreme_price)
                    else:
                        self.arm(
                            direction=sweep_event.direction,
                            sweep_candle=candle,
                            sweep_timeframe=tf,
                            swept_level=sweep_event.swept_level,
                            extreme_price=sweep_event.extreme_price,
                            sweep_type=sweep_event.sweep_type.value if hasattr(sweep_event.sweep_type, "value") else str(sweep_event.sweep_type),
                        )

        if not history or candle.timestamp > history[-1].timestamp:
            history.append(candle)
        elif history and history[-1].timestamp == candle.timestamp:
            history[-1] = candle
        if len(history) > 100:
            del history[:-100]
        return self.armed_state if self.is_armed else None

    def _check_intrabar_htf_sweep(self, candle: Candle) -> bool:
        """
        Check if an incoming closed M1 candle pierces/sweeps higher-timeframe levels
        while the higher-timeframe candle is actively forming (intrabar wick sweep).
        """
        if not self.enable_intrabar_sweep:
            return False

        in_session = True
        if self.session_filter:
            in_session = (self.session_start_hour <= candle.timestamp.hour < self.session_end_hour)
        if not in_session:
            return False

        # 1. Key Liquidity Sweep Check
        if self.anchor_to_key_liquidity:
            min_dist = self.min_sweep_pips * self.pip_size
            if (self.asia_high is not None and candle.high > (self.asia_high + min_dist)) or \
               (self.pdh is not None and candle.high > (self.pdh + min_dist)):
                swept_lvl = self.asia_high if (self.asia_high is not None and candle.high > self.asia_high) else self.pdh
                self._last_htf_sweep_direction = Direction.SELL
                self._last_htf_sweep_tf = "M15"
                self._last_htf_sweep_time = candle.timestamp
                self.arm(
                    direction=Direction.SELL,
                    sweep_candle=candle,
                    sweep_timeframe="M15",
                    swept_level=swept_lvl,
                    extreme_price=candle.high,
                    sweep_type="KEY_LIQUIDITY",
                    is_intrabar=True,
                )
                return True
            elif (self.asia_low is not None and candle.low < (self.asia_low - min_dist)) or \
                 (self.pdl is not None and candle.low < (self.pdl - min_dist)):
                swept_lvl = self.asia_low if (self.asia_low is not None and candle.low < self.asia_low) else self.pdl
                self._last_htf_sweep_direction = Direction.BUY
                self._last_htf_sweep_tf = "M15"
                self._last_htf_sweep_time = candle.timestamp
                self.arm(
                    direction=Direction.BUY,
                    sweep_candle=candle,
                    sweep_timeframe="M15",
                    swept_level=swept_lvl,
                    extreme_price=candle.low,
                    sweep_type="KEY_LIQUIDITY",
                    is_intrabar=True,
                )
                return True

        # 2. Check M15 Intrabar Sweep
        if self.check_m15 and len(self._htf_history["M15"]) >= 1:
            m15_minute = (candle.timestamp.minute // 15) * 15
            m15_key = candle.timestamp.replace(minute=m15_minute, second=0, microsecond=0)
            if m15_key in self._traded_m15_keys:
                return False

            last_m15 = self._htf_history["M15"][-1]
            if candle.timestamp >= last_m15.timestamp:
                # SELL setup: Prior M15 was bullish (or opposite), M1 sweeps above prior high
                if self.allow_variant_a and (last_m15.is_bullish or last_m15.close >= last_m15.open):
                    if candle.high > last_m15.high:
                        if not (self.h1_trend_filter and self.latest_h1_ema is not None and candle.close > self.latest_h1_ema):
                            self._last_htf_sweep_direction = Direction.SELL
                            self._last_htf_sweep_tf = "M15"
                            self._last_htf_sweep_time = candle.timestamp
                            self.arm(
                                direction=Direction.SELL,
                                sweep_candle=candle,
                                sweep_timeframe="M15",
                                swept_level=last_m15.high,
                                extreme_price=candle.high,
                                sweep_type=SweepType.VARIANT_A.value,
                                is_intrabar=True,
                            )
                            return True
                # BUY setup: Prior M15 was bearish (or opposite), M1 sweeps below prior low
                if self.allow_variant_a and (last_m15.is_bearish or last_m15.close <= last_m15.open):
                    if candle.low < last_m15.low:
                        if not (self.h1_trend_filter and self.latest_h1_ema is not None and candle.close < self.latest_h1_ema):
                            self._last_htf_sweep_direction = Direction.BUY
                            self._last_htf_sweep_tf = "M15"
                            self._last_htf_sweep_time = candle.timestamp
                            self.arm(
                                direction=Direction.BUY,
                                sweep_candle=candle,
                                sweep_timeframe="M15",
                                swept_level=last_m15.low,
                                extreme_price=candle.low,
                                sweep_type=SweepType.VARIANT_A.value,
                                is_intrabar=True,
                            )
                            return True

        # 3. Check M5 Intrabar Sweep
        if self.check_m5 and len(self._htf_history["M5"]) >= 1:
            m5_minute = (candle.timestamp.minute // 5) * 5
            m5_key = candle.timestamp.replace(minute=m5_minute, second=0, microsecond=0)
            if m5_key not in self._traded_m5_keys:
                last_m5 = self._htf_history["M5"][-1]
                if candle.timestamp >= last_m5.timestamp:
                    # SELL setup: Prior M5 was bullish (or opposite), M1 sweeps above prior high
                    if self.allow_variant_a and (last_m5.is_bullish or last_m5.close >= last_m5.open):
                        if candle.high > last_m5.high:
                            # Timeframe hierarchy: Do not allow counter-trend M5 sweep if an M15 sweep is active within 15 minutes
                            if not (
                                self._last_htf_sweep_direction is not None
                                and self._last_htf_sweep_tf == "M15"
                                and self._last_htf_sweep_time is not None
                                and candle.timestamp < self._last_htf_sweep_time + timedelta(minutes=15)
                                and Direction.SELL != self._last_htf_sweep_direction
                            ):
                                if not (self.h1_trend_filter and self.latest_h1_ema is not None and candle.close > self.latest_h1_ema):
                                    self._last_htf_sweep_direction = Direction.SELL
                                    self._last_htf_sweep_tf = "M5"
                                    self._last_htf_sweep_time = candle.timestamp
                                    self.arm(
                                        direction=Direction.SELL,
                                        sweep_candle=candle,
                                        sweep_timeframe="M5",
                                        swept_level=last_m5.high,
                                        extreme_price=candle.high,
                                        sweep_type=SweepType.VARIANT_A.value,
                                        is_intrabar=True,
                                    )
                                    return True
                    # BUY setup: Prior M5 was bearish (or opposite), M1 sweeps below prior low
                    if self.allow_variant_a and (last_m5.is_bearish or last_m5.close <= last_m5.open):
                        if candle.low < last_m5.low:
                            # Timeframe hierarchy: Do not allow counter-trend M5 sweep if an M15 sweep is active within 15 minutes
                            if not (
                                self._last_htf_sweep_direction is not None
                                and self._last_htf_sweep_tf == "M15"
                                and self._last_htf_sweep_time is not None
                                and candle.timestamp < self._last_htf_sweep_time + timedelta(minutes=15)
                                and Direction.BUY != self._last_htf_sweep_direction
                            ):
                                if not (self.h1_trend_filter and self.latest_h1_ema is not None and candle.close < self.latest_h1_ema):
                                    self._last_htf_sweep_direction = Direction.BUY
                                    self._last_htf_sweep_tf = "M5"
                                    self._last_htf_sweep_time = candle.timestamp
                                    self.arm(
                                        direction=Direction.BUY,
                                        sweep_candle=candle,
                                        sweep_timeframe="M5",
                                        swept_level=last_m5.low,
                                        extreme_price=candle.low,
                                        sweep_type=SweepType.VARIANT_A.value,
                                        is_intrabar=True,
                                    )
                                    return True

        return False

    def on_m1_candle(
        self,
        raw_candle: Union[Candle, Dict[str, Any]],
    ) -> Optional[TradeSignal]:
        """
        Ingest a closed 1-minute candle.
        If armed:
        - Evaluates consecutive same-direction candles (all bullish for BUY, all bearish for SELL).
        - If 3 consecutive candles complete:
            evaluates confirmation (with displacement check if configured).
            sets stop-loss (at sweep wick extreme if use_sweep_wick_sl=True).
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

        # Auto-disarm if existing armed state is stale from a previous day or > 2 hours old
        if self.armed_state is not None:
            time_diff = candle.timestamp - self.armed_state.armed_at_timestamp
            if candle.timestamp.date() != self.armed_state.armed_at_timestamp.date() or time_diff > timedelta(hours=2):
                self.disarm()

        # Update M1 body metrics for displacement
        self._m1_body_sum += candle.body
        self._m1_body_count += 1

        # Keep daily & session levels updated
        self._update_daily_and_session_levels(candle)

        # Update M5 aggregation
        m5_minute = (candle.timestamp.minute // 5) * 5
        m5_t = candle.timestamp.replace(minute=m5_minute, second=0, microsecond=0)
        if self._curr_m5_key is None:
            self._curr_m5_key = m5_t
            self._curr_m5_buf = [candle]
        elif m5_t == self._curr_m5_key:
            self._curr_m5_buf.append(candle)
        else:
            if self._curr_m5_buf:
                m5_bar = Candle(
                    timestamp=self._curr_m5_key,
                    open=self._curr_m5_buf[0].open,
                    high=max(b.high for b in self._curr_m5_buf),
                    low=min(b.low for b in self._curr_m5_buf),
                    close=self._curr_m5_buf[-1].close,
                    volume=sum(b.volume for b in self._curr_m5_buf),
                )
                self.on_htf_candle(m5_bar, timeframe="M5")
            self._curr_m5_key = m5_t
            self._curr_m5_buf = [candle]

        # Update M15 aggregation
        m15_minute = (candle.timestamp.minute // 15) * 15
        m15_t = candle.timestamp.replace(minute=m15_minute, second=0, microsecond=0)
        if self._curr_m15_key is None:
            self._curr_m15_key = m15_t
            self._curr_m15_buf = [candle]
        elif m15_t == self._curr_m15_key:
            self._curr_m15_buf.append(candle)
        else:
            if self._curr_m15_buf:
                m15_bar = Candle(
                    timestamp=self._curr_m15_key,
                    open=self._curr_m15_buf[0].open,
                    high=max(b.high for b in self._curr_m15_buf),
                    low=min(b.low for b in self._curr_m15_buf),
                    close=self._curr_m15_buf[-1].close,
                    volume=sum(b.volume for b in self._curr_m15_buf),
                )
                self.on_htf_candle(m15_bar, timeframe="M15")
            self._curr_m15_key = m15_t
            self._curr_m15_buf = [candle]

        # Update H1 aggregation
        h1_t = candle.timestamp.replace(minute=0, second=0, microsecond=0)
        if self._curr_h1_key is None:
            self._curr_h1_key = h1_t
            self._curr_h1_buf = [candle]
        elif h1_t == self._curr_h1_key:
            self._curr_h1_buf.append(candle)
        else:
            if self._curr_h1_buf:
                h1_bar = Candle(
                    timestamp=self._curr_h1_key,
                    open=self._curr_h1_buf[0].open,
                    high=max(b.high for b in self._curr_h1_buf),
                    low=min(b.low for b in self._curr_h1_buf),
                    close=self._curr_h1_buf[-1].close,
                    volume=sum(b.volume for b in self._curr_h1_buf),
                )
                self.on_h1_candle(h1_bar)
            self._curr_h1_key = h1_t
            self._curr_h1_buf = [candle]

        just_armed = False
        if self.armed_state is None:
            just_armed = self._check_intrabar_htf_sweep(candle)

        if self.armed_state is None:
            return None

        # Ignore 1m candles that closed before or during the sweep candle
        if self.armed_state.is_intrabar:
            if candle.timestamp < self.armed_state.sweep_candle.timestamp:
                return None
            elif candle.timestamp == self.armed_state.sweep_candle.timestamp:
                is_dir_match = (
                    (self.armed_state.direction == Direction.BUY and candle.close >= candle.open) or
                    (self.armed_state.direction == Direction.SELL and candle.close <= candle.open)
                )
                if not is_dir_match:
                    return None
        else:
            sweep_delta = TIMEFRAME_DELTAS.get(self.armed_state.sweep_timeframe, timedelta(minutes=5))
            sweep_close_time = self.armed_state.sweep_candle.timestamp + sweep_delta
            if candle.timestamp + timedelta(minutes=1) <= sweep_close_time:
                return None

        # If price reaches a new extreme beyond the current sweep extreme, update it
        if self.armed_state.direction == Direction.SELL and candle.high > self.armed_state.extreme_price:
            self.armed_state.extreme_price = candle.high
            self.armed_state.confirming_candles.clear()
            self.armed_state.candles_watched = 0
        elif self.armed_state.direction == Direction.BUY and candle.low < self.armed_state.extreme_price:
            self.armed_state.extreme_price = candle.low
            self.armed_state.confirming_candles.clear()
            self.armed_state.candles_watched = 0

        self.armed_state.candles_watched += 1

        is_matching = False
        if self.armed_state.direction == Direction.BUY:
            is_matching = (candle.close >= candle.open)  # Bullish or neutral doji (not bearish)
        elif self.armed_state.direction == Direction.SELL:
            is_matching = (candle.close <= candle.open)  # Bearish or neutral doji (not bullish)

        if is_matching:
            self.armed_state.confirming_candles.append(candle)
            if len(self.armed_state.confirming_candles) == 3:
                # 3 consecutive confirming candles complete
                avg_m1_body = (self._m1_body_sum / self._m1_body_count) if self._m1_body_count > 0 else None
                signal = evaluate_3_candles(
                    confirming_candles=self.armed_state.confirming_candles,
                    direction=self.armed_state.direction,
                    buffer_pips=self.buffer_pips,
                    pip_size=self.pip_size,
                    spread_pips=self.spread_pips,
                    sweep_type="SWEEP_" + self.armed_state.sweep_timeframe,
                    sweep_timeframe=self.armed_state.sweep_timeframe,
                    reward_risk_ratio=self.reward_risk_ratio,
                    sweep_extreme_price=self.armed_state.extreme_price,
                    use_sweep_wick_sl=self.use_sweep_wick_sl,
                    use_c1_only_sl=self.use_c1_only_sl,
                    min_displacement_ratio=self.min_displacement_ratio,
                    avg_candle_body=avg_m1_body,
                    min_risk_pips=self.min_risk_pips,
                    partial_bank_r=self.partial_bank_r,
                    partial_bank_pct=self.partial_bank_pct,
                    breakeven_trigger_r=self.breakeven_trigger_r,
                )
                if signal is not None:
                    if self.armed_state.sweep_timeframe == "M15" and self.armed_state.sweep_candle is not None:
                        m15_minute = (self.armed_state.sweep_candle.timestamp.minute // 15) * 15
                        m15_key = self.armed_state.sweep_candle.timestamp.replace(minute=m15_minute, second=0, microsecond=0)
                        self._traded_m15_keys.add(m15_key)
                    elif self.armed_state.sweep_timeframe == "M5" and self.armed_state.sweep_candle is not None:
                        m5_minute = (self.armed_state.sweep_candle.timestamp.minute // 5) * 5
                        m5_key = self.armed_state.sweep_candle.timestamp.replace(minute=m5_minute, second=0, microsecond=0)
                        self._traded_m5_keys.add(m5_key)
                self.disarm()
                if signal is not None:
                    min_risk_distance = self.min_risk_pips * self.pip_size
                    if signal.risk_distance < min_risk_distance:
                        return None
                return signal
        else:
            # If this candle is the exact candle that just triggered the arming, do not disarm
            if just_armed or candle.timestamp == self.armed_state.armed_at_timestamp:
                pass
            elif self.disarm_on_break:
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
        timeframe: "M1", "M5", "M15", or "H1".
        Returns None or {direction, entry_price, stop_loss, take_profit, ...} if an M1 candle triggers an order.
        """
        tf = timeframe.upper().strip()
        if tf in ("H1", "1H", "60"):
            self.on_htf_candle(raw_candle, timeframe="H1")
            return None
        elif tf in ("M5", "5M", "5"):
            self.on_htf_candle(raw_candle, timeframe="M5")
            return None
        elif tf in ("M15", "15M", "15"):
            self.on_htf_candle(raw_candle, timeframe="M15")
            return None
        elif tf in ("M1", "1M", "1"):
            sig = self.on_m1_candle(raw_candle)
            return sig.to_dict() if sig else None
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Expected M1, M5, M15, or H1.")

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
        h1 = resample_m1_to_htf(m1, 60) if self.h1_trend_filter else []

        # Priority: H1 (0) -> M15 (1) -> M5 (2) -> M1 (3)
        events: List[Tuple[datetime, int, str, Candle]] = []

        if self.h1_trend_filter:
            for c in h1:
                close_time = c.timestamp + timedelta(hours=1)
                events.append((close_time, 0, "H1", c))

        if self.check_m15:
            for c in m15:
                close_time = c.timestamp + timedelta(minutes=15)
                events.append((close_time, 1, "M15", c))

        if self.check_m5:
            for c in m5:
                close_time = c.timestamp + timedelta(minutes=5)
                events.append((close_time, 2, "M5", c))

        for c in m1:
            close_time = c.timestamp + timedelta(minutes=1)
            events.append((close_time, 3, "M1", c))

        events.sort(key=lambda x: (x[0], x[1]))

        signals: List[TradeSignal] = []
        for close_time, priority, tf, c in events:
            if tf in ("H1", "M5", "M15"):
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
            use_c1_only_sl=self.use_c1_only_sl,
            reward_risk_ratio=self.reward_risk_ratio,
            use_sweep_wick_sl=self.use_sweep_wick_sl,
            min_displacement_ratio=self.min_displacement_ratio,
            min_risk_pips=self.min_risk_pips,
            partial_bank_r=self.partial_bank_r,
            partial_bank_pct=self.partial_bank_pct,
            breakeven_trigger_r=self.breakeven_trigger_r,
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
