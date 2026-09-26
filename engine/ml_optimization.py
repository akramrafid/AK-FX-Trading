"""engine/ml_optimization.py
Phase 8: Post-Live ML/RL Trade Optimization & Regime Confidence Layer.

Provides:
1. Feature Extraction: Session, volatility (ATR), sweep depth, momentum.
2. SessionRegimeConfidenceModel: Pure Python logistic classifier trained on
   historical/demo/live database records to score trade probability.
3. DynamicTradeManager: Policy-based trade management (breakeven lock at +3R,
   trailing profit lock at +5R towards 10R target).
4. Non-Bypassable Risk Invariant: The ML/RL layer sits strictly UPSTREAM of
   RiskGuardrails. It can filter signals, but CANNOT bypass or override risk limits.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from engine.models import Candle, Direction, TradeSignal
from risk.guardrails import RiskGuardrails
from risk.models import AccountState, ValidationResult

logger = logging.getLogger("ml_optimization")


@dataclass
class TradeFeatures:
    """Extracted numeric features for confidence scoring."""
    session_hour: float              # 0.0 to 23.0
    is_london_ny_overlap: float      # 1.0 if 12:00-16:00 UTC else 0.0
    is_london_open: float            # 1.0 if 07:00-10:00 UTC else 0.0
    sweep_depth_pips: float          # Distance beyond swept level in pips
    risk_pips: float                 # Stop loss distance in pips
    timeframe_m15: float             # 1.0 if M15 sweep else 0.0 (M5)

    def to_vector(self) -> List[float]:
        """Returns normalized feature vector with bias term."""
        return [
            1.0,  # Bias
            (self.session_hour - 12.0) / 6.0,
            self.is_london_ny_overlap,
            self.is_london_open,
            min(self.sweep_depth_pips / 10.0, 3.0),
            min(self.risk_pips / 20.0, 3.0),
            self.timeframe_m15,
        ]


class TradeFeatureExtractor:
    """Extracts machine learning features from signals and market context."""

    @staticmethod
    def extract_from_signal(
        signal: TradeSignal,
        timeframe: str = "M5",
        sweep_level: Optional[float] = None,
    ) -> TradeFeatures:
        ts = signal.timestamp or datetime.now(timezone.utc)
        hour = float(ts.hour)
        is_overlap = 1.0 if (12 <= ts.hour <= 16) else 0.0
        is_london = 1.0 if (7 <= ts.hour <= 10) else 0.0

        risk_pips = float(signal.risk_distance / 0.0001) if signal.risk_distance > 0 else 10.0
        if sweep_level is not None:
            sweep_depth = float(abs(signal.entry_price - sweep_level) / 0.0001)
        elif getattr(signal, "sweep_level", None) is not None:
            sweep_depth = float(abs(signal.entry_price - signal.sweep_level) / 0.0001)
        else:
            sweep_depth = 5.0

        return TradeFeatures(
            session_hour=hour,
            is_london_ny_overlap=is_overlap,
            is_london_open=is_london,
            sweep_depth_pips=sweep_depth,
            risk_pips=risk_pips,
            timeframe_m15=1.0 if timeframe.upper() == "M15" else 0.0,
        )


class SessionRegimeConfidenceModel:
    """Pure Python logistic regression classifier for trade setup confidence scoring.
    
    Zero third-party dependencies (numpy/scipy/sklearn NOT required).
    """

    FEATURE_NAMES = [
        "bias",
        "session_hour_norm",
        "is_london_ny_overlap",
        "is_london_open",
        "sweep_depth_norm",
        "risk_pips_norm",
        "timeframe_m15",
    ]

    def __init__(self, confidence_threshold: float = 0.50) -> None:
        self.confidence_threshold = confidence_threshold
        # Default prior weights favoring London/NY sessions and moderate stops
        self.weights: List[float] = [
            -0.5,   # Bias (baseline win rate ~9%)
            0.1,    # Afternoon preference
            0.8,    # London/NY overlap strong positive
            0.5,    # London open positive
            0.2,    # Decisive sweep depth positive
            -0.3,   # Excessively wide stops penalized
            0.4,    # M15 sweeps carry higher institutional weight
        ]

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z > 15.0:
            return 1.0
        elif z < -15.0:
            return 0.0
        return 1.0 / (1.0 + math.exp(-z))

    def predict_proba(self, features: TradeFeatures) -> float:
        """Computes probability of trade achieving target win."""
        x = features.to_vector()
        if len(x) != len(self.weights):
            raise ValueError(f"Feature vector length {len(x)} != weights length {len(self.weights)}")

        z = sum(w * xi for w, xi in zip(self.weights, x))
        return self._sigmoid(z)

    def filter_signal(
        self,
        signal: TradeSignal,
        timeframe: str = "M5",
        threshold: Optional[float] = None,
    ) -> Tuple[bool, float]:
        """Evaluates whether trade setup meets confidence threshold."""
        thresh = threshold if threshold is not None else self.confidence_threshold
        feats = TradeFeatureExtractor.extract_from_signal(signal, timeframe=timeframe)
        confidence = self.predict_proba(feats)
        is_approved = confidence >= thresh
        return is_approved, confidence

    def train_on_journal(
        self,
        trades: List[Dict[str, Any]],
        learning_rate: float = 0.05,
        epochs: int = 50,
    ) -> float:
        """Trains model weights using gradient descent on historical/live trade journal data.
        
        Label y = 1 if realized_pnl > 0 (or exit_reason == 'TP'), else 0.
        """
        if not trades:
            return 0.0

        samples: List[Tuple[List[float], float]] = []
        for t in trades:
            pnl = float(t.get("realized_pnl", 0.0))
            y = 1.0 if pnl > 0 else 0.0

            open_time_str = t.get("open_time", "")
            try:
                dt = datetime.fromisoformat(open_time_str)
            except Exception:
                dt = datetime.now(timezone.utc)

            hour = float(dt.hour)
            is_overlap = 1.0 if (12 <= dt.hour <= 16) else 0.0
            is_london = 1.0 if (7 <= dt.hour <= 10) else 0.0
            lots = float(t.get("lots", 0.01))
            open_p = float(t.get("open_price", 1.0))
            sl_p = float(t.get("stop_loss", 1.0))
            risk_pips = abs(open_p - sl_p) / 0.0001 if open_p > 0 else 15.0

            feats = TradeFeatures(
                session_hour=hour,
                is_london_ny_overlap=is_overlap,
                is_london_open=is_london,
                sweep_depth_pips=5.0,
                risk_pips=risk_pips,
                timeframe_m15=1.0 if t.get("timeframe", "M5") == "M15" else 0.0,
            )
            samples.append((feats.to_vector(), y))

        # Mini-batch gradient descent
        n = len(samples)
        final_loss = 0.0
        for _ in range(epochs):
            grad = [0.0] * len(self.weights)
            total_loss = 0.0
            for x, y in samples:
                z = sum(w * xi for w, xi in zip(self.weights, x))
                p = self._sigmoid(z)
                p_clamped = max(1e-7, min(1.0 - 1e-7, p))
                total_loss += -(y * math.log(p_clamped) + (1.0 - y) * math.log(1.0 - p_clamped))
                err = p - y
                for i in range(len(self.weights)):
                    grad[i] += err * x[i]

            for i in range(len(self.weights)):
                self.weights[i] -= (learning_rate / n) * grad[i]
            final_loss = total_loss / n

        return final_loss


class TradeAction(str, Enum):
    """Dynamic trade management actions."""
    HOLD = "HOLD"
    MOVE_TO_BREAKEVEN = "MOVE_TO_BREAKEVEN"
    TRAIL_STOP = "TRAIL_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"


@dataclass
class TradeManagementDecision:
    """Action recommendation emitted by DynamicTradeManager."""
    action: TradeAction
    new_stop_loss: Optional[float]
    rationale: str


class DynamicTradeManager:
    """Policy-based active trade manager.
    
    Protects capital as favorable excursion (MFE) advances:
    - < 3.0R: Maintain original stop loss (give trade room to develop).
    - >= 3.0R: Move stop loss to breakeven (entry price + spread buffer).
    - >= 5.0R: Trail stop loss to lock in +3.0R profit while holding for full +10.0R TP.
    """

    def __init__(
        self,
        breakeven_threshold_r: float = 3.0,
        trailing_threshold_r: float = 5.0,
        trailing_lock_r: float = 3.0,
        spread_buffer_pips: float = 0.5,
    ) -> None:
        self.breakeven_threshold_r = breakeven_threshold_r
        self.trailing_threshold_r = trailing_threshold_r
        self.trailing_lock_r = trailing_lock_r
        self.spread_buffer_pips = spread_buffer_pips

    def evaluate_position(
        self,
        direction: Direction,
        entry_price: float,
        current_price: float,
        initial_stop_loss: float,
        take_profit: float,
        risk_distance: float,
    ) -> TradeManagementDecision:
        """Evaluates active position and recommends SL modifications."""
        if risk_distance <= 0:
            return TradeManagementDecision(TradeAction.HOLD, None, "Invalid risk distance")

        # Compute current favorable excursion in R-multiples
        dir_val = direction.value if isinstance(direction, Direction) else str(direction).upper()
        if dir_val in ("BUY", "DIRECTION.BUY"):
            current_gain = current_price - entry_price
            current_r = current_gain / risk_distance
        else:
            current_gain = entry_price - current_price
            current_r = current_gain / risk_distance

        buffer_offset = self.spread_buffer_pips * 0.0001

        # Check for +5R Trailing Lock
        if current_r >= self.trailing_threshold_r:
            locked_dist = self.trailing_lock_r * risk_distance
            if dir_val in ("BUY", "DIRECTION.BUY"):
                new_sl = round(entry_price + locked_dist, 5)
            else:
                new_sl = round(entry_price - locked_dist, 5)
            return TradeManagementDecision(
                action=TradeAction.TRAIL_STOP,
                new_stop_loss=new_sl,
                rationale=f"Position at {current_r:.1f}R >= {self.trailing_threshold_r}R: trailing stop locked to +{self.trailing_lock_r}R.",
            )

        # Check for +3R Breakeven Move
        if current_r >= self.breakeven_threshold_r:
            if dir_val in ("BUY", "DIRECTION.BUY"):
                new_sl = round(entry_price + buffer_offset, 5)
            else:
                new_sl = round(entry_price - buffer_offset, 5)
            return TradeManagementDecision(
                action=TradeAction.MOVE_TO_BREAKEVEN,
                new_stop_loss=new_sl,
                rationale=f"Position at {current_r:.1f}R >= {self.breakeven_threshold_r}R: stop loss moved to breakeven + buffer.",
            )

        return TradeManagementDecision(
            action=TradeAction.HOLD,
            new_stop_loss=None,
            rationale=f"Position at {current_r:.1f}R: maintain initial stop loss.",
        )


def validate_signal_with_ml_and_risk(
    signal: TradeSignal,
    account_state: AccountState,
    proposed_lots: Decimal,
    guardrails: RiskGuardrails,
    ml_model: Optional[SessionRegimeConfidenceModel] = None,
    timeframe: str = "M5",
) -> Tuple[bool, str, Optional[float]]:
    """Complete validation pipeline enforcing strict architecture hierarchy:
    
    Rule Engine -> ML Confidence Filter -> Non-Bypassable Risk Guardrails -> Bridge
    
    Guarantees:
    - ML can decline setups (filter out low probability trades).
    - ML approval CANNOT bypass Risk Guardrails.
    - If Risk Guardrails reject, the trade is unconditionally REJECTED.
    """
    confidence_score: Optional[float] = None

    # 1. ML Regime / Confidence Pre-Filter
    if ml_model is not None:
        is_approved, conf = ml_model.filter_signal(signal, timeframe=timeframe)
        confidence_score = conf
        if not is_approved:
            return False, f"ML_FILTER_REJECTED: Confidence {conf:.2f} below threshold {ml_model.confidence_threshold:.2f}", confidence_score

    # 2. Non-Bypassable Risk Guardrails (MANDATORY GATE)
    risk_result: ValidationResult = guardrails.validate_trade(
        account_state=account_state,
        proposed_lots=proposed_lots,
        trade_time=signal.timestamp,
    )

    if not risk_result.is_allowed:
        return False, f"RISK_GUARDRAIL_REJECTED: [{risk_result.reason}] {risk_result.message}", confidence_score

    return True, "APPROVED_BY_ML_AND_RISK", confidence_score
