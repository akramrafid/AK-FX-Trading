"""
Data models and value objects for the AK Forex Trading rule engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Direction(str, Enum):
    """Trade direction."""
    BUY = "BUY"
    SELL = "SELL"


class SweepType(str, Enum):
    """Liquidity sweep setup variant."""
    VARIANT_A = "VARIANT_A"  # Candle-to-candle immediate preceding candle sweep
    VARIANT_B = "VARIANT_B"  # Swing-level multi-bar swing high/low sweep


@dataclass(frozen=True, slots=True)
class Candle:
    """
    Immutable representation of a fully closed OHLC candle.
    In accordance with Domain Rule 1, this must ONLY represent finished bars.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be lower than Low ({self.low})")
        if self.high < max(self.open, self.close):
            raise ValueError(f"High ({self.high}) cannot be lower than Open ({self.open}) or Close ({self.close})")
        if self.low > min(self.open, self.close):
            raise ValueError(f"Low ({self.low}) cannot be higher than Open ({self.open}) or Close ({self.close})")
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("All OHLC prices must be strictly positive values")

    @property
    def is_bullish(self) -> bool:
        """True if close > open (green candle)."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """True if close < open (red candle)."""
        return self.close < self.open

    @property
    def is_doji(self) -> bool:
        """True if close == open."""
        return self.close == self.open

    @property
    def upper_wick(self) -> float:
        """Distance from highest body edge to high."""
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        """Distance from low to lowest body edge."""
        return min(self.open, self.close) - self.low

    @property
    def body(self) -> float:
        """Absolute distance between open and close."""
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        """Total high-to-low range."""
        return self.high - self.low

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Candle:
        raw_ts = data["timestamp"]
        if isinstance(raw_ts, str):
            ts = datetime.fromisoformat(raw_ts)
        elif isinstance(raw_ts, (int, float)):
            ts = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        else:
            ts = raw_ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return cls(
            timestamp=ts,
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data.get("volume", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class SweepEvent:
    """
    Represents a detected liquidity sweep on a completed candle.
    """
    sweep_type: SweepType
    direction: Direction  # Intended breakout direction: BUY after sweeping lows, SELL after sweeping highs
    candle_index: int
    sweep_candle: Candle
    swept_level: float
    extreme_price: float  # The highest high or lowest low reached during the sweep


@dataclass
class ArmedState:
    """
    Represents the active 'armed' state after a higher-timeframe liquidity sweep.
    While armed, the system watches the 1-minute chart for 3 consecutive confirming candles.
    """
    direction: Direction
    sweep_timeframe: str  # "M5" or "M15"
    sweep_candle: Candle
    swept_level: float
    extreme_price: float
    armed_at_timestamp: datetime
    candles_watched: int = 0
    max_watch_candles: int = 15  # As confirmed by user
    confirming_candles: List[Candle] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return self.candles_watched >= self.max_watch_candles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value if isinstance(self.direction, Direction) else str(self.direction),
            "sweep_timeframe": self.sweep_timeframe,
            "swept_level": self.swept_level,
            "extreme_price": self.extreme_price,
            "armed_at_timestamp": self.armed_at_timestamp.isoformat() if self.armed_at_timestamp else None,
            "candles_watched": self.candles_watched,
            "max_watch_candles": self.max_watch_candles,
            "confirming_count": len(self.confirming_candles),
        }


@dataclass(frozen=True, slots=True)
class TradeSignal:
    """
    Verified trade signal produced by the Rule Engine upon 3-candle confirmation.
    """
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_distance: float
    reward_distance: float
    reward_risk_ratio: float = 5.0
    sweep_type: str = ""
    sweep_candle_index: int = -1
    confirmation_indices: Tuple[int, int, int] = field(default_factory=tuple)  # Indices of the 3 confirmation candles
    timestamp: Optional[datetime] = None
    sweep_timeframe: str = "M5"
    timeframe: str = "M1"

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns the clean output dictionary specified in system requirements.
        """
        return {
            "direction": self.direction,
            "entry_price": round(self.entry_price, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit": round(self.take_profit, 5),
            "risk_distance": round(self.risk_distance, 5),
            "reward_distance": round(self.reward_distance, 5),
            "reward_risk_ratio": round(self.reward_risk_ratio, 2),
            "sweep_type": self.sweep_type,
            "sweep_candle_index": self.sweep_candle_index,
            "confirmation_indices": list(self.confirmation_indices),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "sweep_timeframe": self.sweep_timeframe,
            "timeframe": self.timeframe,
        }
