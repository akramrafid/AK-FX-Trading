"""tests/test_live_rollout.py
Unit tests for Phase 7 Live Rollout Safeguards & Divergence Monitoring (bridge/live_rollout.py).

Verifies:
1. Micro-lot initial deployment (0.01 lot minimum broker size).
2. Phased scaling ladder gating based on live trade sample size.
3. Multi-environment divergence detection (Win Rate, Slippage, Drawdown).
4. Automatic lockdown to Tier 1 Micro-lot upon divergence trip.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from bridge.live_rollout import (
    DivergenceMonitor,
    DivergenceReport,
    EnvironmentMetrics,
    LiveRolloutManager,
    ScalingTier,
)


class TestLiveRolloutManager(unittest.TestCase):
    """Tests for phased scaling ladder and lot size clamping."""

    def setUp(self) -> None:
        self.monitor = DivergenceMonitor(
            max_win_rate_divergence_pct=5.0,
            max_median_slippage_pips=1.5,
            max_drawdown_divergence_pct=10.0,
            min_sample_size_for_check=20,
        )
        self.manager = LiveRolloutManager(divergence_monitor=self.monitor)

    def test_tier_1_micro_initial_deployment(self) -> None:
        """Trades 0 to 49 must be strictly confined to Tier 1 (micro-lots)."""
        self.assertEqual(self.manager.determine_tier(0), ScalingTier.TIER_1_MICRO)
        self.assertEqual(self.manager.determine_tier(49), ScalingTier.TIER_1_MICRO)

        # Clamping check: even if sizer suggests 2.50 lots, Tier 1 clamps to 0.01 lot
        clamped = self.manager.clamp_lot_size(Decimal("2.50"), ScalingTier.TIER_1_MICRO)
        self.assertEqual(clamped, Decimal("0.01"))

    def test_tier_progression_with_trade_count(self) -> None:
        """Trade count unlocks higher risk tiers progressively."""
        self.assertEqual(self.manager.determine_tier(50), ScalingTier.TIER_2_CONSERVATIVE)
        self.assertEqual(self.manager.determine_tier(99), ScalingTier.TIER_2_CONSERVATIVE)
        self.assertEqual(self.manager.determine_tier(100), ScalingTier.TIER_3_MODERATE)
        self.assertEqual(self.manager.determine_tier(199), ScalingTier.TIER_3_MODERATE)
        self.assertEqual(self.manager.determine_tier(200), ScalingTier.TIER_4_FULL)

        # In Tier 2-4, proposed lots are not forced to 0.01
        clamped = self.manager.clamp_lot_size(Decimal("0.85"), ScalingTier.TIER_2_CONSERVATIVE)
        self.assertEqual(clamped, Decimal("0.85"))

    def test_force_tier_1_override(self) -> None:
        """When force_tier_1_micro flag is True, always return Tier 1."""
        strict_manager = LiveRolloutManager(force_tier_1_micro=True)
        self.assertEqual(strict_manager.determine_tier(500), ScalingTier.TIER_1_MICRO)

    def test_divergence_forces_tier_1_lockdown(self) -> None:
        """If a divergence report indicates is_diverged=True, demote to Tier 1 Micro-lot."""
        backtest = EnvironmentMetrics("BACKTEST", 4839, 6.74, -0.26, 0.5, 0.42, 12.5)
        demo = EnvironmentMetrics("DEMO", 150, 7.33, -0.18, 0.5, 0.65, 8.0)
        # Live win rate collapsed to 1.0% (divergence > 5%)
        live = EnvironmentMetrics("LIVE", 60, 1.00, -0.90, 0.6, 0.10, 15.0)

        report = self.monitor.evaluate_divergence(backtest, demo, live)
        self.assertTrue(report.is_diverged)

        # Even with 150 live trades, manager must lock to Tier 1 Micro
        tier = self.manager.determine_tier(150, divergence_report=report)
        self.assertEqual(tier, ScalingTier.TIER_1_MICRO)


class TestDivergenceMonitor(unittest.TestCase):
    """Tests for multi-environment divergence detection."""

    def setUp(self) -> None:
        self.monitor = DivergenceMonitor(
            max_win_rate_divergence_pct=5.0,
            max_median_slippage_pips=1.5,
            max_drawdown_divergence_pct=10.0,
            min_sample_size_for_check=20,
        )
        self.bt = EnvironmentMetrics("BACKTEST", 4839, 6.74, -0.26, 0.5, 0.42, 12.5)
        self.demo = EnvironmentMetrics("DEMO", 150, 7.00, -0.20, 0.5, 0.55, 8.5)

    def test_healthy_convergence_allows_trading(self) -> None:
        """When Live closely tracks Demo and Backtest, no divergence is tripped."""
        live_healthy = EnvironmentMetrics("LIVE", 45, 6.80, -0.22, 0.55, 0.50, 9.0)
        report = self.monitor.evaluate_divergence(self.bt, self.demo, live_healthy)

        self.assertFalse(report.is_diverged)
        self.assertEqual(report.action, "ALLOW_TRADING")
        self.assertEqual(len(report.reasons), 0)

    def test_win_rate_divergence_triggers_halt(self) -> None:
        """Live win rate departing by >5% from demo trips DIVERGENCE_HALT."""
        live_diverged = EnvironmentMetrics("LIVE", 35, 1.20, -0.85, 0.55, 0.12, 11.0)
        report = self.monitor.evaluate_divergence(self.bt, self.demo, live_diverged)

        self.assertTrue(report.is_diverged)
        self.assertEqual(report.action, "DIVERGENCE_HALT")
        self.assertTrue(any("Win rate diverged" in r for r in report.reasons))

    def test_excessive_slippage_triggers_halt(self) -> None:
        """Median slippage > 1.5 pips indicates broker execution failure."""
        live_slipping = EnvironmentMetrics("LIVE", 25, 6.50, -0.30, 2.10, 0.40, 10.0)
        report = self.monitor.evaluate_divergence(self.bt, self.demo, live_slipping)

        self.assertTrue(report.is_diverged)
        self.assertEqual(report.action, "DIVERGENCE_HALT")
        self.assertTrue(any("slippage" in r.lower() for r in report.reasons))

    def test_drawdown_divergence_triggers_halt(self) -> None:
        """Drawdown exceeding demo by >10% triggers halt."""
        live_drawdown = EnvironmentMetrics("LIVE", 30, 5.50, -0.40, 0.60, 0.35, 22.0)
        report = self.monitor.evaluate_divergence(self.bt, self.demo, live_drawdown)

        self.assertTrue(report.is_diverged)
        self.assertEqual(report.action, "DIVERGENCE_HALT")
        self.assertTrue(any("drawdown" in r.lower() for r in report.reasons))

    def test_sample_size_gating(self) -> None:
        """Sample size < min_sample_size_for_check ignores premature variance."""
        live_small_sample = EnvironmentMetrics("LIVE", 8, 0.0, -1.0, 0.5, 0.0, 5.0)
        report = self.monitor.evaluate_divergence(self.bt, self.demo, live_small_sample)

        self.assertFalse(report.is_diverged)
        self.assertEqual(report.action, "ALLOW_TRADING")


if __name__ == "__main__":
    unittest.main()
