"""
Liquidity Sweep Detector for AK Forex Trading System.

Implements two sweep triggers on closed OHLC candles:
- Variant A (Candle-to-Candle): Wick sweeps the extreme wick/body of the immediately
  preceding opposite-colored candle, closing back within range (wick rejection).
- Variant B (Swing-Level): Wick sweeps a confirmed prior swing high or swing low
  within a lookback window, closing back inside the level (rejection).
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from .models import Candle, Direction, SweepEvent, SweepType


def detect_variant_a(candles: List[Candle], current_idx: int) -> Optional[SweepEvent]:
    """
    Evaluate Variant A (Candle-to-Candle Sweep) on the candle at current_idx.

    Conditions for Bullish Sweep (seeking Long):
    1. Preceding candle (current_idx - 1) was Bearish (close < open).
    2. Current candle sweeps below preceding candle's low (current.low < prev.low).
    3. Current candle closes at or above preceding candle's low (current.close >= prev.low).
       (Wick swept the liquidity below prev low, but body rejected and closed back up).

    Conditions for Bearish Sweep (seeking Short):
    1. Preceding candle (current_idx - 1) was Bullish (close > open).
    2. Current candle sweeps above preceding candle's high (current.high > prev.high).
    3. Current candle closes at or below preceding candle's high (current.close <= prev.high).
       (Wick swept the liquidity above prev high, but body rejected and closed back down).
    """
    if current_idx < 1 or current_idx >= len(candles):
        return None

    current = candles[current_idx]
    prev = candles[current_idx - 1]

    # Bullish sweep check (preceding candle must be opposite-colored: bearish)
    if prev.is_bearish:
        if current.low < prev.low and current.close >= prev.low:
            return SweepEvent(
                sweep_type=SweepType.VARIANT_A,
                direction=Direction.BUY,
                candle_index=current_idx,
                sweep_candle=current,
                swept_level=prev.low,
                extreme_price=current.low,
            )

    # Bearish sweep check (preceding candle must be opposite-colored: bullish)
    if prev.is_bullish:
        if current.high > prev.high and current.close <= prev.high:
            return SweepEvent(
                sweep_type=SweepType.VARIANT_A,
                direction=Direction.SELL,
                candle_index=current_idx,
                sweep_candle=current,
                swept_level=prev.high,
                extreme_price=current.high,
            )

    return None


def find_swing_levels(
    candles: List[Candle],
    start_idx: int,
    end_idx: int,
    swing_strength: int = 2,
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """
    Identify confirmed swing highs and swing lows strictly before end_idx.
    swing_strength: Number of bars on each side that must be lower (for high) or higher (for low).
    Returns (swing_highs, swing_lows) as lists of (index, price).
    """
    swing_highs: List[Tuple[int, float]] = []
    swing_lows: List[Tuple[int, float]] = []

    # Swing high/low at index i requires swing_strength bars before and after to be confirmed.
    # Therefore, the candidate swing bar must be at least swing_strength bars before end_idx.
    max_candidate_idx = end_idx - swing_strength
    min_candidate_idx = start_idx + swing_strength

    for i in range(min_candidate_idx, max_candidate_idx + 1):
        candidate = candles[i]

        # Check Swing High
        is_swing_high = True
        for offset in range(-swing_strength, swing_strength + 1):
            if offset == 0:
                continue
            if candles[i + offset].high >= candidate.high:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append((i, candidate.high))

        # Check Swing Low
        is_swing_low = True
        for offset in range(-swing_strength, swing_strength + 1):
            if offset == 0:
                continue
            if candles[i + offset].low <= candidate.low:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append((i, candidate.low))

    return swing_highs, swing_lows


def detect_variant_b(
    candles: List[Candle],
    current_idx: int,
    lookback: int = 20,
    swing_strength: int = 2,
) -> Optional[SweepEvent]:
    """
    Evaluate Variant B (Swing-Level Sweep) on the candle at current_idx.

    Checks if current candle sweeps a confirmed prior swing high or swing low
    within the lookback window without closing beyond it.
    """
    min_required_bars = swing_strength * 2 + 1
    if current_idx < min_required_bars or current_idx >= len(candles):
        return None

    current = candles[current_idx]
    window_start = max(0, current_idx - lookback)
    # The swing level must have formed prior to the current candle
    swing_highs, swing_lows = find_swing_levels(
        candles,
        start_idx=window_start,
        end_idx=current_idx - 1,
        swing_strength=swing_strength,
    )

    # Check for Bullish Sweep of Swing Low (swept below swing low, closed above it)
    # Prioritize the most recent or lowest relevant swing low swept
    swept_lows = [
        (idx, level) for idx, level in swing_lows
        if current.low < level and current.close >= level
    ]
    if swept_lows:
        # Choose the most recent swing low swept
        recent_idx, recent_level = swept_lows[-1]
        return SweepEvent(
            sweep_type=SweepType.VARIANT_B,
            direction=Direction.BUY,
            candle_index=current_idx,
            sweep_candle=current,
            swept_level=recent_level,
            extreme_price=current.low,
        )

    # Check for Bearish Sweep of Swing High (swept above swing high, closed below it)
    swept_highs = [
        (idx, level) for idx, level in swing_highs
        if current.high > level and current.close <= level
    ]
    if swept_highs:
        # Choose the most recent swing high swept
        recent_idx, recent_level = swept_highs[-1]
        return SweepEvent(
            sweep_type=SweepType.VARIANT_B,
            direction=Direction.SELL,
            candle_index=current_idx,
            sweep_candle=current,
            swept_level=recent_level,
            extreme_price=current.high,
        )

    return None


def detect_sweep(
    candles: List[Candle],
    current_idx: int,
    allow_variant_a: bool = True,
    allow_variant_b: bool = True,
    swing_lookback: int = 20,
    swing_strength: int = 2,
) -> Optional[SweepEvent]:
    """
    Combined sweep detector. Evaluates Variant A first, then Variant B if enabled.
    """
    if allow_variant_a:
        event = detect_variant_a(candles, current_idx)
        if event is not None:
            return event

    if allow_variant_b:
        event = detect_variant_b(
            candles,
            current_idx,
            lookback=swing_lookback,
            swing_strength=swing_strength,
        )
        if event is not None:
            return event

    return None
