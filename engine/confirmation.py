"""
Confirmation and Risk-Reward (10:1) Calculator for AK Forex Trading System.

Evaluates the 3 closed candles following a qualifying liquidity sweep:
- Confirms 3 consecutive candles in trade direction (all green for BUY, all red for SELL).
- Entry: Close of candle 3.
- Stop-Loss: Beyond the extreme of candle 1 (below low for BUY, above high + spread for SELL).
- Take-Profit: Fixed 10x stop-loss distance (10:1 R:R).
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple
from .models import Candle, Direction, SweepEvent, TradeSignal


def evaluate_3_candles(
    confirming_candles: Sequence[Candle],
    direction: Direction,
    buffer_pips: float = 0.0,
    pip_size: float = 0.0001,
    spread_pips: float = 0.0,
    sweep_type: str = "VARIANT_A",
    sweep_candle_index: int = -1,
    sweep_timeframe: str = "M5",
    confirmation_indices: Tuple[int, int, int] = (0, 1, 2),
    use_c1_only_sl: bool = False,
    reward_risk_ratio: float = 5.0,
    sweep_extreme_price: Optional[float] = None,
    use_sweep_wick_sl: bool = False,
    min_displacement_ratio: float = 0.0,
    avg_candle_body: Optional[float] = None,
    min_risk_pips: float = 0.0,
    partial_bank_r: Optional[float] = None,
    partial_bank_pct: Optional[float] = None,
    breakeven_trigger_r: Optional[float] = None,
) -> Optional[TradeSignal]:
    """
    Evaluates 3 closed candles for directional confirmation and calculates R:R (default 5:1).
    - Long (BUY): All 3 candles must be bullish.
    - Short (SELL): All 3 candles must be bearish.
    - Entry: Close of 3rd candle.
    - Stop-Loss:
      - If use_sweep_wick_sl=True: Placed beyond the sweep extreme wick (High_sweep + spread for short, Low_sweep for long).
      - Else: lowest low / highest high across confirming candles (default).
    - Displacement: If min_displacement_ratio > 0, requires at least one candle body >= ratio * avg_candle_body.
    - Take-Profit: Entry ± (reward_risk_ratio * Stop Distance).
    """
    if len(confirming_candles) != 3:
        return None

    c1, c2, c3 = confirming_candles[0], confirming_candles[1], confirming_candles[2]
    buffer_price = buffer_pips * pip_size
    spread_price = spread_pips * pip_size

    # Check institutional displacement requirement if configured
    if min_displacement_ratio > 0.0 and avg_candle_body is not None and avg_candle_body > 0.0:
        max_body = max(c1.body, c2.body, c3.body)
        if max_body < (min_displacement_ratio * avg_candle_body):
            return None

    if direction == Direction.BUY:
        # All 3 candles must be directional (bullish or neutral doji; none can close bearish)
        if not (c1.close >= c1.open and c2.close >= c2.open and c3.close >= c3.open):
            return None
        entry_price = c3.close
        if use_sweep_wick_sl and sweep_extreme_price is not None:
            stop_loss = sweep_extreme_price - buffer_price
        else:
            lowest_low = c1.low if use_c1_only_sl else min(c1.low, c2.low, c3.low)
            stop_loss = lowest_low - buffer_price

        risk_distance = entry_price - stop_loss
        if min_risk_pips > 0.0:
            min_dist = min_risk_pips * pip_size
            if risk_distance < min_dist:
                risk_distance = min_dist
                stop_loss = entry_price - risk_distance

        if risk_distance <= 0:
            return None
        reward_distance = reward_risk_ratio * risk_distance
        take_profit = entry_price + reward_distance

        return TradeSignal(
            direction="BUY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=reward_risk_ratio,
            sweep_type=sweep_type,
            sweep_candle_index=sweep_candle_index,
            confirmation_indices=confirmation_indices,
            timestamp=c3.timestamp,
            sweep_timeframe=sweep_timeframe,
            timeframe="M1",
            extreme_price=sweep_extreme_price,
            partial_bank_r=partial_bank_r,
            partial_bank_pct=partial_bank_pct,
            breakeven_trigger_r=breakeven_trigger_r,
        )

    elif direction == Direction.SELL:
        # All 3 candles must be directional (bearish or neutral doji; none can close bullish)
        if not (c1.close <= c1.open and c2.close <= c2.open and c3.close <= c3.open):
            return None
        entry_price = c3.close
        if use_sweep_wick_sl and sweep_extreme_price is not None:
            stop_loss = sweep_extreme_price + spread_price + buffer_price
        else:
            highest_high = c1.high if use_c1_only_sl else max(c1.high, c2.high, c3.high)
            stop_loss = highest_high + spread_price + buffer_price

        risk_distance = stop_loss - entry_price
        if min_risk_pips > 0.0:
            min_dist = min_risk_pips * pip_size
            if risk_distance < min_dist:
                risk_distance = min_dist
                stop_loss = entry_price + risk_distance

        if risk_distance <= 0:
            return None
        reward_distance = reward_risk_ratio * risk_distance
        take_profit = entry_price - reward_distance

        return TradeSignal(
            direction="SELL",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=reward_risk_ratio,
            sweep_type=sweep_type,
            sweep_candle_index=sweep_candle_index,
            confirmation_indices=confirmation_indices,
            timestamp=c3.timestamp,
            sweep_timeframe=sweep_timeframe,
            timeframe="M1",
            extreme_price=sweep_extreme_price,
            partial_bank_r=partial_bank_r,
            partial_bank_pct=partial_bank_pct,
            breakeven_trigger_r=breakeven_trigger_r,
        )

    return None


def evaluate_confirmation(
    candles: List[Candle],
    sweep_event: SweepEvent,
    buffer_pips: float = 0.0,
    pip_size: float = 0.0001,
    spread_pips: float = 0.0,
    use_c1_only_sl: bool = False,
    reward_risk_ratio: float = 5.0,
    use_sweep_wick_sl: bool = False,
    min_displacement_ratio: float = 0.0,
    avg_candle_body: Optional[float] = None,
    min_risk_pips: float = 0.0,
    partial_bank_r: Optional[float] = None,
    partial_bank_pct: Optional[float] = None,
    breakeven_trigger_r: Optional[float] = None,
) -> Optional[TradeSignal]:
    """
    Evaluate the 3 candles immediately following the sweep candle.

    sweep_event.candle_index: index of the sweep candle (S)
    Confirmation candles must be at:
    - Candle 1: S + 1
    - Candle 2: S + 2
    - Candle 3: S + 3

    Returns TradeSignal if all 3 candles confirm; None if incomplete or broken.
    """
    s_idx = sweep_event.candle_index
    c1_idx = s_idx + 1
    c2_idx = s_idx + 2
    c3_idx = s_idx + 3

    # Check if all 3 confirmation candles are available and closed
    if c3_idx >= len(candles):
        return None

    confirming = [candles[c1_idx], candles[c2_idx], candles[c3_idx]]

    return evaluate_3_candles(
        confirming_candles=confirming,
        direction=sweep_event.direction,
        buffer_pips=buffer_pips,
        pip_size=pip_size,
        spread_pips=spread_pips,
        sweep_type=sweep_event.sweep_type.value,
        sweep_candle_index=s_idx,
        confirmation_indices=(c1_idx, c2_idx, c3_idx),
        use_c1_only_sl=use_c1_only_sl,
        reward_risk_ratio=reward_risk_ratio,
        sweep_extreme_price=sweep_event.extreme_price,
        use_sweep_wick_sl=use_sweep_wick_sl,
        min_displacement_ratio=min_displacement_ratio,
        avg_candle_body=avg_candle_body,
        min_risk_pips=min_risk_pips,
        partial_bank_r=partial_bank_r,
        partial_bank_pct=partial_bank_pct,
        breakeven_trigger_r=breakeven_trigger_r,
    )

