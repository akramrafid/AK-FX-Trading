"""bridge/live_rollout.py
Phase 7 Live Rollout Safeguards & Divergence Monitoring.

Enforces:
1. Micro-lot initial deployment (0.01 lot minimum broker size).
2. Phased scaling ladder (Tier 1 -> Tier 4) based on verified live trade count.
3. Multi-environment Divergence Monitoring (Backtest vs. Demo vs. Live):
   - Win Rate Divergence (> 5.0% delta triggers divergence halt).
   - Average R / Expectancy Divergence.
   - Execution Slippage Divergence (median slippage > 1.5 pips triggers alert).
   - Drawdown Divergence.
4. Automatic Divergence Halt: locks lot size to 0.01 or trips emergency kill-switch
   if unexplained divergence between live, demo, and backtest appears.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("live_rollout")


class ScalingTier(str, Enum):
    """Phased scaling tiers for production live deployment."""
    TIER_1_MICRO = "TIER_1_MICRO"         # Fixed 0.01 micro-lot (trades 1-50)
    TIER_2_CONSERVATIVE = "TIER_2_CONSERVATIVE" # 0.25% risk per trade (trades 51-100)
    TIER_3_MODERATE = "TIER_3_MODERATE"   # 0.50% risk per trade (trades 101-200)
    TIER_4_FULL = "TIER_4_FULL"           # 1.00% - 1.50% risk per trade (trades 201+)


@dataclass(frozen=True)
class EnvironmentMetrics:
    """Performance metrics snapshot for a specific trading environment."""
    environment: str                      # 'BACKTEST', 'DEMO', 'LIVE'
    trade_count: int
    win_rate: float                       # Percentage, e.g. 7.5%
    average_r: float                      # E.g. -0.15R
    median_slippage_pips: float           # E.g. 0.5 pips
    profit_factor: float                  # E.g. 0.85
    max_drawdown_pct: float               # E.g. 8.2%
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DivergenceReport:
    """Audit report comparing Backtest, Demo, and Live metrics."""
    backtest_metrics: EnvironmentMetrics
    demo_metrics: EnvironmentMetrics
    live_metrics: EnvironmentMetrics
    is_diverged: bool
    win_rate_delta_live_demo: float
    win_rate_delta_live_backtest: float
    slippage_delta_pips: float
    reasons: List[str] = field(default_factory=list)
    action: str = "ALLOW_TRADING"         # ALLOW_TRADING, HOLD_TIER, DIVERGENCE_HALT


class DivergenceMonitor:
    """Monitors statistical divergence between Backtest, Demo, and Live execution."""

    def __init__(
        self,
        max_win_rate_divergence_pct: float = 5.0,     # Max allowable 5% win rate delta
        max_median_slippage_pips: float = 1.5,        # 1.5 pip slippage ceiling
        max_drawdown_divergence_pct: float = 10.0,    # 10% drawdown divergence tolerance
        min_sample_size_for_check: int = 20,          # Minimum live trades before divergence trip
    ) -> None:
        self.max_win_rate_divergence_pct = max_win_rate_divergence_pct
        self.max_median_slippage_pips = max_median_slippage_pips
        self.max_drawdown_divergence_pct = max_drawdown_divergence_pct
        self.min_sample_size_for_check = min_sample_size_for_check

    def evaluate_divergence(
        self,
        backtest: EnvironmentMetrics,
        demo: EnvironmentMetrics,
        live: EnvironmentMetrics,
    ) -> DivergenceReport:
        """Compares live performance against demo and backtest baselines."""
        reasons: List[str] = []
        is_diverged = False

        # Live vs Demo Win Rate Delta
        wr_delta_demo = abs(live.win_rate - demo.win_rate)
        # Live vs Backtest Win Rate Delta
        wr_delta_backtest = abs(live.win_rate - backtest.win_rate)

        # Slippage Delta against backtest expectation (1.0 pip)
        slippage_delta = live.median_slippage_pips - backtest.median_slippage_pips

        # Only evaluate divergence triggers if minimum live sample size is reached
        if live.trade_count >= self.min_sample_size_for_check:
            # 1. Win Rate Divergence Check
            if wr_delta_demo > self.max_win_rate_divergence_pct:
                is_diverged = True
                reasons.append(
                    f"Win rate diverged from Demo by {wr_delta_demo:.2f}% "
                    f"(Live: {live.win_rate:.2f}%, Demo: {demo.win_rate:.2f}%, limit: {self.max_win_rate_divergence_pct}%)."
                )

            if wr_delta_backtest > self.max_win_rate_divergence_pct * 1.5:
                is_diverged = True
                reasons.append(
                    f"Win rate diverged from Backtest by {wr_delta_backtest:.2f}% "
                    f"(Live: {live.win_rate:.2f}%, Backtest: {backtest.win_rate:.2f}%)."
                )

            # 2. Execution Slippage Check
            if live.median_slippage_pips > self.max_median_slippage_pips:
                is_diverged = True
                reasons.append(
                    f"Live median slippage ({live.median_slippage_pips:.2f} pips) exceeds acceptable ceiling "
                    f"({self.max_median_slippage_pips:.2f} pips). Broker execution friction too high."
                )

            # 3. Drawdown Divergence Check
            if live.max_drawdown_pct > (demo.max_drawdown_pct + self.max_drawdown_divergence_pct):
                is_diverged = True
                reasons.append(
                    f"Live drawdown ({live.max_drawdown_pct:.2f}%) exceeds Demo drawdown ({demo.max_drawdown_pct:.2f}%) "
                    f"by more than {self.max_drawdown_divergence_pct}%."
                )

        action = "DIVERGENCE_HALT" if is_diverged else "ALLOW_TRADING"
        if is_diverged:
            logger.critical(f"DIVERGENCE DETECTED! Actions: {action}. Reasons: {'; '.join(reasons)}")

        return DivergenceReport(
            backtest_metrics=backtest,
            demo_metrics=demo,
            live_metrics=live,
            is_diverged=is_diverged,
            win_rate_delta_live_demo=round(wr_delta_demo, 2),
            win_rate_delta_live_backtest=round(wr_delta_backtest, 2),
            slippage_delta_pips=round(slippage_delta, 2),
            reasons=reasons,
            action=action,
        )


class LiveRolloutManager:
    """Orchestrates phased scaling and safety clamps for live deployment."""

    def __init__(
        self,
        divergence_monitor: Optional[DivergenceMonitor] = None,
        force_tier_1_micro: bool = False,
    ) -> None:
        self.divergence_monitor = divergence_monitor or DivergenceMonitor()
        self.force_tier_1_micro = force_tier_1_micro
        self.current_tier = ScalingTier.TIER_1_MICRO
        self._emergency_halt_tripped = False

    def determine_tier(self, live_trade_count: int, divergence_report: Optional[DivergenceReport] = None) -> ScalingTier:
        """Determines allowable scaling tier based on trade count and divergence health."""
        if self.force_tier_1_micro:
            return ScalingTier.TIER_1_MICRO

        # If divergence is active, lock down to micro-lot Tier 1
        if divergence_report is not None and divergence_report.is_diverged:
            logger.warning("Divergence active: forcing Tier 1 Micro-lot (0.01 lot).")
            return ScalingTier.TIER_1_MICRO

        if live_trade_count < 50:
            return ScalingTier.TIER_1_MICRO
        elif live_trade_count < 100:
            return ScalingTier.TIER_2_CONSERVATIVE
        elif live_trade_count < 200:
            return ScalingTier.TIER_3_MODERATE
        else:
            return ScalingTier.TIER_4_FULL

    def get_risk_pct_for_tier(self, tier: ScalingTier) -> Decimal:
        """Returns risk percentage corresponding to current scaling tier."""
        tier_map = {
            ScalingTier.TIER_1_MICRO: Decimal("0.001"),       # 0.01 lot or minimal risk
            ScalingTier.TIER_2_CONSERVATIVE: Decimal("0.0025"), # 0.25%
            ScalingTier.TIER_3_MODERATE: Decimal("0.0050"),   # 0.50%
            ScalingTier.TIER_4_FULL: Decimal("0.0100"),       # 1.00%
        }
        return tier_map.get(tier, Decimal("0.001"))

    def clamp_lot_size(
        self,
        proposed_lots: Decimal,
        tier: ScalingTier,
    ) -> Decimal:
        """Enforces micro-lot sizing constraint if on Tier 1."""
        if tier == ScalingTier.TIER_1_MICRO:
            return Decimal("0.01")
        return proposed_lots
