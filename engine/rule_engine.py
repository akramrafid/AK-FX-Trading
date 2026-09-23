"""
Core Rule Engine for AK Forex Trading System.

Pure Python, zero-dependency algorithmic execution engine.
Evaluates closed OHLC candles sequentially without intrabar tick data or future look-ahead.
Directly implements:
- Variant A (Candle-to-Candle) & Variant B (Swing-Level) liquidity sweeps.
- 3-consecutive-candle directional confirmation.
- 10:1 Reward-to-Risk mathematical pricing (Entry = C3.close, SL = beyond C1, TP = Entry ± 10x SL).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union
from .models import Candle, Direction, SweepEvent, SweepType, TradeSignal
from .sweep_detector import detect_sweep, detect_variant_a, detect_variant_b
from .confirmation import evaluate_confirmation


class RuleEngine:
    """
    Deterministic trading rule engine. Operates exclusively on closed bars.
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
    ) -> None:
        self.allow_variant_a = allow_variant_a
        self.allow_variant_b = allow_variant_b
        self.swing_lookback = swing_lookback
        self.swing_strength = swing_strength
        self.buffer_pips = buffer_pips
        self.spread_pips = spread_pips
        self.pip_size = pip_size
        self.min_risk_pips = min_risk_pips

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

    def evaluate_at_index(
        self,
        candles: List[Candle],
        sweep_idx: int,
    ) -> Optional[TradeSignal]:
        """
        Check if a sweep occurred at sweep_idx and if the subsequent 3 candles (sweep_idx+1, +2, +3)
        form a completed, valid confirmation sequence.
        """
        if sweep_idx < 1:
            return None

        # Check for sweep on candle sweep_idx
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

        # Check for 3-candle confirmation starting at sweep_idx + 1
        signal = evaluate_confirmation(
            candles=candles,
            sweep_event=sweep_event,
            buffer_pips=self.buffer_pips,
            pip_size=self.pip_size,
            spread_pips=self.spread_pips,
        )
        if signal is None:
            return None

        # Check min risk distance sanity
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

        This is the primary function invoked live on every new-bar event.
        """
        candles = self._coerce_candles(raw_candles)
        # At least 4 candles needed: 1 sweep candle + 3 confirmation candles
        # plus at least 1 prior candle for Variant A check (total >= 5 candles)
        if len(candles) < 5:
            return None

        last_idx = len(candles) - 1
        sweep_idx = last_idx - 3  # The sweep candle must be exactly 3 bars before current

        return self.evaluate_at_index(candles, sweep_idx)

    def scan_historical_signals(
        self,
        raw_candles: Sequence[Union[Candle, Dict[str, Any]]],
    ) -> List[TradeSignal]:
        """
        Walks chronologically through a series of closed candles and extracts all
        confirmed signals. Used in backtesting and performance analytics.
        Ensures strict chronological bar walk without look-ahead bias.
        """
        candles = self._coerce_candles(raw_candles)
        signals: List[TradeSignal] = []
        n = len(candles)

        if n < 5:
            return signals

        # A sweep candle can occur from index 1 up to n - 4
        # (allowing 3 confirmation candles up to n - 1)
        i = 1
        while i <= n - 4:
            signal = self.evaluate_at_index(candles, sweep_idx=i)
            if signal is not None:
                signals.append(signal)
                # Advance beyond the 3 confirmation candles to prevent duplicate overlapping signals
                i += 4
            else:
                i += 1

        return signals


def evaluate_candles(
    candles: Sequence[Union[Candle, Dict[str, Any]]],
    allow_variant_a: bool = True,
    allow_variant_b: bool = True,
    swing_lookback: int = 20,
    swing_strength: int = 2,
    buffer_pips: float = 0.0,
    spread_pips: float = 0.0,
    pip_size: float = 0.0001,
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
    )
    signal = engine.evaluate_completed_candle(candles)
    if signal is None:
        return None
    return signal.to_dict()
