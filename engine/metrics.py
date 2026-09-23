"""
Performance and Risk Metrics Calculator.

Computes hedge-fund grade quantitative metrics from backtest results:
Win Rate, Average R, Profit Factor, Maximum Drawdown (% and $),
Consecutive Loss Streaks, Sharpe and Sortino Ratios.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from engine.backtester import BacktestResult, BacktestTrade


@dataclass(frozen=True)
class PerformanceMetrics:
    """Quantitative performance and risk profile of a trading run."""
    initial_balance: float
    final_balance: float
    net_profit: float
    return_on_capital_pct: float

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float

    total_r: float
    average_r: float
    average_win_r: float
    average_loss_r: float

    gross_profit: float
    gross_loss: float
    profit_factor: float

    max_drawdown_currency: float
    max_drawdown_pct: float

    longest_losing_streak: int
    longest_winning_streak: int

    sharpe_ratio: float
    sortino_ratio: float
    average_bars_held: float

    def format_summary(self) -> str:
        """Return formatted markdown performance table."""
        return f"""### Backtest Performance Summary
| Metric | Value |
|---|---|
| **Initial Capital** | ${self.initial_balance:,.2f} |
| **Final Capital** | ${self.final_balance:,.2f} |
| **Net Profit ($)** | ${self.net_profit:+,.2f} ({self.return_on_capital_pct:+.2f}%) |
| **Total Trades** | {self.total_trades} |
| **Win Rate** | {self.win_rate_pct:.2f}% ({self.winning_trades}W / {self.losing_trades}L) |
| **Average R (Expectancy)** | {self.average_r:+.2f}R |
| **Total Realized R** | {self.total_r:+.1f}R |
| **Profit Factor** | {self.profit_factor:.2f} |
| **Max Drawdown ($)** | ${self.max_drawdown_currency:,.2f} |
| **Max Drawdown (%)** | {self.max_drawdown_pct:.2f}% |
| **Longest Losing Streak** | {self.longest_losing_streak} trades |
| **Longest Winning Streak** | {self.longest_winning_streak} trades |
| **Sharpe Ratio (Trade)** | {self.sharpe_ratio:.2f} |
| **Sortino Ratio (Trade)** | {self.sortino_ratio:.2f} |
| **Avg Hold Duration** | {self.average_bars_held:.1f} bars |
"""


def calculate_metrics(result: BacktestResult) -> PerformanceMetrics:
    """
    Compute full quantitative performance metrics from a BacktestResult.
    """
    trades = result.trades
    initial_balance = result.initial_balance
    final_balance = result.final_balance
    net_profit = final_balance - initial_balance
    return_pct = (net_profit / initial_balance * 100.0) if initial_balance > 0 else 0.0

    total_trades = len(trades)
    if total_trades == 0:
        return PerformanceMetrics(
            initial_balance=initial_balance,
            final_balance=final_balance,
            net_profit=0.0,
            return_on_capital_pct=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            total_r=0.0,
            average_r=0.0,
            average_win_r=0.0,
            average_loss_r=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            profit_factor=0.0,
            max_drawdown_currency=0.0,
            max_drawdown_pct=0.0,
            longest_losing_streak=0,
            longest_winning_streak=0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            average_bars_held=0.0,
        )

    winning = [t for t in trades if t.realized_r > 0]
    losing = [t for t in trades if t.realized_r <= 0]

    win_count = len(winning)
    loss_count = len(losing)
    win_rate = (win_count / total_trades) * 100.0

    r_multiples = [t.realized_r for t in trades]
    total_r = sum(r_multiples)
    average_r = total_r / total_trades

    avg_win_r = (sum(t.realized_r for t in winning) / win_count) if win_count > 0 else 0.0
    avg_loss_r = (sum(t.realized_r for t in losing) / loss_count) if loss_count > 0 else 0.0

    gross_profit = sum(t.pnl_currency for t in winning)
    gross_loss = abs(sum(t.pnl_currency for t in losing))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    # Calculate Drawdown from equity curve
    equity_points = [pt[1] for pt in result.equity_curve]
    if not equity_points:
        equity_points = [initial_balance, final_balance]

    peak = equity_points[0]
    max_dd_curr = 0.0
    max_dd_pct = 0.0

    for eq in equity_points:
        if eq > peak:
            peak = eq
        dd_curr = peak - eq
        dd_pct = (dd_curr / peak * 100.0) if peak > 0 else 0.0

        if dd_curr > max_dd_curr:
            max_dd_curr = dd_curr
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    # Streaks
    curr_win_streak = 0
    max_win_streak = 0
    curr_loss_streak = 0
    max_loss_streak = 0

    for t in trades:
        if t.realized_r > 0:
            curr_win_streak += 1
            curr_loss_streak = 0
            if curr_win_streak > max_win_streak:
                max_win_streak = curr_win_streak
        else:
            curr_loss_streak += 1
            curr_win_streak = 0
            if curr_loss_streak > max_loss_streak:
                max_loss_streak = curr_loss_streak

    # Sharpe & Sortino (per trade)
    pnl_returns = [t.pnl_currency / initial_balance for t in trades]
    mean_ret = sum(pnl_returns) / total_trades

    variance = sum((r - mean_ret) ** 2 for r in pnl_returns) / (total_trades - 1) if total_trades > 1 else 0.0
    stdev = math.sqrt(variance)
    sharpe = (mean_ret / stdev * math.sqrt(total_trades)) if stdev > 0 else 0.0

    downside_variance = sum((min(0.0, r) ** 2) for r in pnl_returns) / total_trades
    downside_stdev = math.sqrt(downside_variance)
    sortino = (mean_ret / downside_stdev * math.sqrt(total_trades)) if downside_stdev > 0 else 0.0

    avg_bars = sum(t.bars_held for t in trades) / total_trades

    return PerformanceMetrics(
        initial_balance=initial_balance,
        final_balance=final_balance,
        net_profit=round(net_profit, 2),
        return_on_capital_pct=round(return_pct, 2),
        total_trades=total_trades,
        winning_trades=win_count,
        losing_trades=loss_count,
        win_rate_pct=round(win_rate, 2),
        total_r=round(total_r, 2),
        average_r=round(average_r, 2),
        average_win_r=round(avg_win_r, 2),
        average_loss_r=round(avg_loss_r, 2),
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        profit_factor=round(profit_factor, 2),
        max_drawdown_currency=round(max_dd_curr, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        longest_losing_streak=max_loss_streak,
        longest_winning_streak=max_win_streak,
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        average_bars_held=round(avg_bars, 1),
    )
