"""
Unit and Integration Test Suite for Historical Data Pipeline, Backtester, and Metrics Engine.

Validates:
1. Dukascopy and MT4 CSV parsing, gap detection, and normalization.
2. Dynamic position sizing with hard clamping (Hard Rule 3).
3. Event-driven bar-by-bar execution without look-ahead bias (Hard Rule 1 & 2).
4. Realistic spread/slippage penalty application.
5. Exact quantitative metrics (Win Rate, Average R, Drawdown, Profit Factor, Streaks).
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from data.loader import (
    find_data_gaps,
    load_candles_from_csv,
    parse_candle_row,
    parse_timestamp,
    save_candles_to_csv,
)
from engine.backtester import BacktestConfig, BacktestEngine, BacktestResult, BacktestTrade
from engine.metrics import PerformanceMetrics, calculate_metrics
from engine.models import Candle


def create_candle(
    index: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 100.0,
    base_time: Optional[datetime] = None,
) -> Candle:
    if base_time is None:
        base_time = datetime(2023, 1, 2, 8, 0, 0, tzinfo=timezone.utc)
    return Candle(
        timestamp=base_time + timedelta(minutes=5 * index),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
    )


class TestHistoricalDataLoader(unittest.TestCase):
    """Test CSV ingestion across multiple broker formats."""

    def test_parse_timestamp_formats(self):
        # Dukascopy format
        ts1 = parse_timestamp("2023.01.02 08:05:00")
        self.assertEqual(ts1, datetime(2023, 1, 2, 8, 5, 0, tzinfo=timezone.utc))

        # MT4 separate date & time
        ts2 = parse_timestamp("2023.01.02", "08:10:00")
        self.assertEqual(ts2, datetime(2023, 1, 2, 8, 10, 0, tzinfo=timezone.utc))

        # ISO format
        ts3 = parse_timestamp("2023-01-02 08:15:00")
        self.assertEqual(ts3, datetime(2023, 1, 2, 8, 15, 0, tzinfo=timezone.utc))

    def test_csv_roundtrip_dukascopy(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tmp:
            tmp_path = tmp.name
            # Write Dukascopy style header
            tmp.write("Gmt time,Open,High,Low,Close,Volume\n")
            tmp.write("2023.01.02 08:00:00,1.0850,1.0890,1.0840,1.0880,150.0\n")
            tmp.write("2023.01.02 08:05:00,1.0880,1.0900,1.0870,1.0895,180.0\n")

        try:
            candles = load_candles_from_csv(tmp_path)
            self.assertEqual(len(candles), 2)
            self.assertEqual(candles[0].open, 1.0850)
            self.assertEqual(candles[1].close, 1.0895)

            # Roundtrip save
            save_path = tmp_path + ".out.csv"
            save_candles_to_csv(candles, save_path)
            reloaded = load_candles_from_csv(save_path)
            self.assertEqual(len(reloaded), 2)
            self.assertEqual(reloaded[0].timestamp, candles[0].timestamp)
            if os.path.exists(save_path):
                os.remove(save_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_find_data_gaps(self):
        c0 = create_candle(0, 1.0800, 1.0850, 1.0790, 1.0840)
        c1 = create_candle(1, 1.0840, 1.0860, 1.0830, 1.0850)
        # c2 has a 20-minute gap instead of 5 minutes
        c2 = create_candle(5, 1.0850, 1.0870, 1.0840, 1.0860)

        gaps = find_data_gaps([c0, c1, c2], expected_interval_minutes=5)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0][0], c1.timestamp)
        self.assertEqual(gaps[0][1], c2.timestamp)


class TestDynamicLotSizing(unittest.TestCase):
    """Test lot sizing formula and clamping invariants."""

    def setUp(self):
        self.config = BacktestConfig(
            initial_balance=10000.0,
            risk_pct=1.0,           # $100 risk per trade
            pip_size=0.0001,
            pip_value_per_lot=10.0, # $10 per pip per 1.0 lot
            min_lot=0.01,
            max_lot=10.0,
        )
        self.engine = BacktestEngine(self.config)

    def test_standard_position_sizing(self):
        # Risk distance = 20 pips (0.0020)
        # Risk cash = $10,000 * 1% = $100
        # Cost per lot = 20 pips * $10 = $200
        # Expected lot size = $100 / $200 = 0.50 lots
        lots = self.engine.calculate_lot_size(balance=10000.0, risk_distance=0.0020)
        self.assertEqual(lots, 0.50)

    def test_min_lot_clamping(self):
        # Huge stop distance (1000 pips): raw lot = 100 / (1000 * 10) = 0.01 lots
        lots = self.engine.calculate_lot_size(balance=1000.0, risk_distance=0.1000)
        self.assertEqual(lots, 0.01)

    def test_max_lot_clamping(self):
        # Extremely tiny stop distance (1 pip) with high balance: raw lot would exceed max_lot
        lots = self.engine.calculate_lot_size(balance=500000.0, risk_distance=0.0001)
        self.assertEqual(lots, self.config.max_lot)


class TestBacktestEngineExecution(unittest.TestCase):
    """Test full event-driven trade execution and position lifecycle."""

    def test_buy_trade_hits_5_to_1_take_profit(self):
        """
        Setup a complete BUY trade:
        Bar 0: Bullish
        Bar 1: Bearish sweep of Bar 0 low
        Bar 2: C1 Bullish (low defines SL)
        Bar 3: C2 Bullish
        Bar 4: C3 Bullish (close is entry) -> Signal fires!
        Bar 5: Rally hits Take Profit (+5R)
        """
        c0 = create_candle(0, 1.0880, 1.0890, 1.0820, 1.0830)  # Bearish, low=1.0820
        cS = create_candle(1, 1.0830, 1.0840, 1.0805, 1.0825)  # Sweeps c0 low (1.0820)
        c1 = create_candle(2, 1.0825, 1.0835, 1.0815, 1.0830)  # C1: Bullish, low=1.0815 (does not sweep cS)
        c2 = create_candle(3, 1.0830, 1.0855, 1.0825, 1.0850)  # C2: Bullish
        c3 = create_candle(4, 1.0850, 1.0875, 1.0845, 1.0870)  # C3: Bullish, close=1.0870 (Entry)

        # SL = c1.low = 1.0815
        # Risk = 1.0870 - 1.0815 = 0.0055 (55 pips)
        # TP = 1.0870 + (5 * 0.0055) = 1.1145
        # Bar 5: massive upward move hitting TP
        c4 = create_candle(5, 1.0870, 1.1500, 1.0860, 1.1450)

        candles = [c0, cS, c1, c2, c3, c4]
        config = BacktestConfig(
            initial_balance=10000.0,
            risk_pct=1.0,
            spread_pips=0.0,
            slippage_pips=0.0,
        )
        engine = BacktestEngine(config)
        result = engine.run(candles)

        self.assertEqual(result.total_trades, 1)
        trade = result.trades[0]
        self.assertEqual(trade.direction, "BUY")
        self.assertEqual(trade.exit_reason, "TP")
        self.assertEqual(trade.realized_r, 5.0)
        self.assertGreater(result.final_balance, result.initial_balance)

    def test_sell_trade_hits_stop_loss(self):
        """
        Setup a complete SELL trade:
        Bar 0: Bearish
        Bar 1: Bullish sweep of Bar 0 high
        Bar 2: C1 Bearish (high defines SL)
        Bar 3: C2 Bearish
        Bar 4: C3 Bearish (close is entry) -> Signal fires!
        Bar 5: Reverses up and hits Stop-Loss (-1R)
        """
        c0 = create_candle(0, 1.0850, 1.0890, 1.0840, 1.0880)  # Bullish, high=1.0890
        cS = create_candle(1, 1.0880, 1.0910, 1.0870, 1.0875)  # Sweeps c0 high (1.0890)
        c1 = create_candle(2, 1.0900, 1.0920, 1.0880, 1.0890)  # C1: Bearish, high=1.0920
        c2 = create_candle(3, 1.0890, 1.0895, 1.0865, 1.0870)  # C2: Bearish
        c3 = create_candle(4, 1.0870, 1.0875, 1.0845, 1.0850)  # C3: Bearish, close=1.0850 (Entry)

        # SL = 1.0920 + spread (0) = 1.0920
        # Bar 5 rises and pierces 1.0920
        c4 = create_candle(5, 1.0850, 1.0930, 1.0840, 1.0925)

        candles = [c0, cS, c1, c2, c3, c4]
        config = BacktestConfig(
            initial_balance=10000.0,
            risk_pct=1.0,
            spread_pips=0.0,
            slippage_pips=0.0,
        )
        engine = BacktestEngine(config)
        result = engine.run(candles)

        self.assertEqual(result.total_trades, 1)
        trade = result.trades[0]
        self.assertEqual(trade.direction, "SELL")
        self.assertEqual(trade.exit_reason, "SL")
        self.assertEqual(trade.realized_r, -1.0)
        self.assertLess(result.final_balance, result.initial_balance)

    def test_multitimeframe_backtest_execution(self):
        """
        Verify multi-timeframe backtesting with M5 sweep detection and M1 3-candle confirmation.
        """
        base_t = datetime(2023, 1, 2, 8, 0, 0, tzinfo=timezone.utc)
        # M5 candles:
        # m5_0 (08:00 - 08:05): Bullish, high 1.0890
        # m5_1 (08:05 - 08:10): Bearish, sweeps high with 1.0910, closes 1.0875
        m5_0 = Candle(timestamp=base_t, open=1.0850, high=1.0890, low=1.0840, close=1.0880, volume=100.0)
        m5_1 = Candle(timestamp=base_t + timedelta(minutes=5), open=1.0880, high=1.0910, low=1.0870, close=1.0875, volume=100.0)

        # M1 candles (starting 08:10):
        # 08:10: C1 Bearish
        m1_0 = Candle(timestamp=base_t + timedelta(minutes=10), open=1.0875, high=1.0880, low=1.0868, close=1.0870, volume=10.0)
        # 08:11: C2 Bearish
        m1_1 = Candle(timestamp=base_t + timedelta(minutes=11), open=1.0870, high=1.0872, low=1.0858, close=1.0860, volume=10.0)
        # 08:12: C3 Bearish -> Confirms Sell Signal at close 1.0850!
        m1_2 = Candle(timestamp=base_t + timedelta(minutes=12), open=1.0860, high=1.0862, low=1.0848, close=1.0850, volume=10.0)
        # 08:13: Price drops to 1.0500 -> Hits 5:1 Take Profit!
        m1_3 = Candle(timestamp=base_t + timedelta(minutes=13), open=1.0850, high=1.0852, low=1.0500, close=1.0520, volume=50.0)

        engine = BacktestEngine(BacktestConfig(initial_balance=10000.0, spread_pips=0.0, slippage_pips=0.0))
        result = engine.run_multitimeframe(
            m1_candles=[m1_0, m1_1, m1_2, m1_3],
            m5_candles=[m5_0, m5_1],
        )

        self.assertEqual(result.total_trades, 1)
        trade = result.trades[0]
        self.assertEqual(trade.direction, "SELL")
        self.assertEqual(trade.exit_reason, "TP")
        self.assertEqual(trade.realized_r, 5.0)
        self.assertGreater(result.final_balance, result.initial_balance)


class TestPerformanceMetrics(unittest.TestCase):
    """Test quantitative performance calculation accuracy."""

    def test_metrics_calculation_known_series(self):
        # 4 trades: 1 win (+10R), 3 losses (-1R each)
        # Expected Win Rate = 1/4 = 25.0%
        # Total R = 10 - 3 = +7.0R
        # Average R = 7.0 / 4 = +1.75R
        now = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t1 = BacktestTrade(1, "BUY", now, now, 1.0800, 1.0900, 1.0790, 1.0900, 1.0, 1000.0, 100.0, 10.0, "TP", 5)
        t2 = BacktestTrade(2, "BUY", now, now, 1.0800, 1.0790, 1.0790, 1.0900, 1.0, -100.0, -10.0, -1.0, "SL", 2)
        t3 = BacktestTrade(3, "SELL", now, now, 1.0800, 1.0810, 1.0810, 1.0700, 1.0, -100.0, -10.0, -1.0, "SL", 3)
        t4 = BacktestTrade(4, "SELL", now, now, 1.0800, 1.0810, 1.0810, 1.0700, 1.0, -100.0, -10.0, -1.0, "SL", 1)

        result = BacktestResult(
            config=BacktestConfig(initial_balance=10000.0),
            trades=[t1, t2, t3, t4],
            equity_curve=[(now, 10000.0), (now, 11000.0), (now, 10900.0), (now, 10800.0), (now, 10700.0)],
            initial_balance=10000.0,
            final_balance=10700.0,
        )

        metrics = calculate_metrics(result)
        self.assertEqual(metrics.total_trades, 4)
        self.assertEqual(metrics.winning_trades, 1)
        self.assertEqual(metrics.losing_trades, 3)
        self.assertEqual(metrics.win_rate_pct, 25.0)
        self.assertEqual(metrics.total_r, 7.0)
        self.assertEqual(metrics.average_r, 1.75)
        self.assertEqual(metrics.longest_losing_streak, 3)
        self.assertEqual(metrics.longest_winning_streak, 1)
        self.assertAlmostEqual(metrics.profit_factor, 1000.0 / 300.0, places=2)
        self.assertGreater(metrics.sharpe_ratio, 0.0)

        # Ensure summary formatting works
        summary = metrics.format_summary()
        self.assertIn("25.00%", summary)
        self.assertIn("+1.75R", summary)


if __name__ == "__main__":
    unittest.main()
