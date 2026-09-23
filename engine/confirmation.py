"""
Confirmation and Risk-Reward (10:1) Calculator for AK Forex Trading System.

Evaluates the 3 closed candles following a qualifying liquidity sweep:
- Confirms 3 consecutive candles in trade direction (all green for BUY, all red for SELL).
- Entry: Close of candle 3.
- Stop-Loss: Beyond the extreme of candle 1 (below low for BUY, above high + spread for SELL).
- Take-Profit: Fixed 10x stop-loss distance (10:1 R:R).
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from .models import Candle, Direction, SweepEvent, TradeSignal


def evaluate_confirmation(
    candles: List[Candle],
    sweep_event: SweepEvent,
    buffer_pips: float = 0.0,
    pip_size: float = 0.0001,
    spread_pips: float = 0.0,
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

    c1 = candles[c1_idx]
    c2 = candles[c2_idx]
    c3 = candles[c3_idx]

    buffer_price = buffer_pips * pip_size
    spread_price = spread_pips * pip_size

    if sweep_event.direction == Direction.BUY:
        # Long confirmation: All 3 candles must close green/bullish
        if not (c1.is_bullish and c2.is_bullish and c3.is_bullish):
            return None

        entry_price = c3.close
        # Stop-loss sits just below candle 1's low
        stop_loss = c1.low - buffer_price
        risk_distance = entry_price - stop_loss

        if risk_distance <= 0:
            return None

        # Take-profit is strictly 10x the stop distance
        reward_distance = 10.0 * risk_distance
        take_profit = entry_price + reward_distance

        return TradeSignal(
            direction="BUY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=10.0,
            sweep_type=sweep_event.sweep_type.value,
            sweep_candle_index=s_idx,
            confirmation_indices=(c1_idx, c2_idx, c3_idx),
            timestamp=c3.timestamp,
        )

    elif sweep_event.direction == Direction.SELL:
        # Short confirmation: All 3 candles must close red/bearish
        if not (c1.is_bearish and c2.is_bearish and c3.is_bearish):
            return None

        entry_price = c3.close
        # Stop-loss sits just above candle 1's high (+ spread buffer)
        stop_loss = c1.high + spread_price + buffer_price
        risk_distance = stop_loss - entry_price

        if risk_distance <= 0:
            return None

        # Take-profit is strictly 10x the stop distance
        reward_distance = 10.0 * risk_distance
        take_profit = entry_price - reward_distance

        return TradeSignal(
            direction="SELL",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=10.0,
            sweep_type=sweep_event.sweep_type.value,
            sweep_candle_index=s_idx,
            confirmation_indices=(c1_idx, c2_idx, c3_idx),
            timestamp=c3.timestamp,
        )

    return None
