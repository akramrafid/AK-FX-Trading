"""tests/test_bridge.py
Unit and integration tests for MT4 DWX Connect bridge, position sizing,
and automated execution pipeline.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from bridge.dwx_client import (
    CommandAction,
    DWXClient,
    ExecutionReport,
    OrderType,
    TradeCommand,
)
from bridge.executor import ActiveBridgeTrade, BridgeExecutor, generate_mt4_magic_number
from bridge.sizing import PositionSizer, SizingResult
from engine.models import Candle, Direction


class TestDWXClient(unittest.TestCase):
    """Tests for DWX file protocol, commands, reports, and atomic IO."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="test_dwx_")
        self.client = DWXClient(mt4_files_dir=self.test_dir, initial_backoff_ms=10, max_backoff_ms=100)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_write_and_read(self) -> None:
        file_path = Path(self.test_dir) / "test_file.txt"
        test_content = "Hello MT4 Bridge!\nLine 2"
        self.client.atomic_write(file_path, test_content)
        read_back = self.client.atomic_read(file_path)
        self.assertEqual(read_back, test_content)

    def test_send_order_writes_json_command(self) -> None:
        cmd = self.client.send_order(
            symbol="EURUSD",
            order_type=OrderType.BUY,
            lots=Decimal("0.15"),
            sl=Decimal("1.08200"),
            tp=Decimal("1.09200"),
            magic=123456,
            comment="test_order",
        )
        self.assertEqual(cmd.action, CommandAction.OPEN)
        self.assertEqual(cmd.magic, 123456)
        self.assertTrue(self.client.commands_file.exists())

        content = self.client.atomic_read(self.client.commands_file)
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)

        data = json.loads(lines[0])
        self.assertEqual(data["action"], "OPEN")
        self.assertEqual(data["symbol"], "EURUSD")
        self.assertEqual(data["type"], "BUY")
        self.assertEqual(data["lots"], 0.15)
        self.assertEqual(data["magic"], 123456)

    def test_duplicate_magic_prevention(self) -> None:
        self.client.send_order(
            symbol="EURUSD",
            order_type=OrderType.BUY,
            lots=Decimal("0.10"),
            sl=Decimal("1.08000"),
            tp=Decimal("1.09000"),
            magic=999888,
        )
        with self.assertRaises(ValueError):
            self.client.send_order(
                symbol="EURUSD",
                order_type=OrderType.BUY,
                lots=Decimal("0.10"),
                sl=Decimal("1.08000"),
                tp=Decimal("1.09000"),
                magic=999888,
            )

    def test_poll_order_confirmation_success(self) -> None:
        magic = 555123
        self.client.send_order(
            symbol="GBPUSD",
            order_type=OrderType.SELL,
            lots=Decimal("0.50"),
            sl=Decimal("1.28500"),
            tp=Decimal("1.27500"),
            magic=magic,
        )

        # Simulate MT4 EA writing filled report
        mock_report = ExecutionReport(
            ticket=7654321,
            magic=magic,
            symbol="GBPUSD",
            order_type=OrderType.SELL,
            lots=Decimal("0.50"),
            open_price=Decimal("1.28400"),
            sl=Decimal("1.28500"),
            tp=Decimal("1.27500"),
            status="FILLED",
        )
        self.client.write_mock_report(mock_report)

        report = self.client.poll_order_confirmation(magic=magic, timeout_sec=1.0)
        self.assertIsNotNone(report)
        self.assertEqual(report.ticket, 7654321)
        self.assertEqual(report.status, "FILLED")

    def test_poll_order_confirmation_timeout_alerts(self) -> None:
        alerts = []
        self.client.alert_callback = lambda msg: alerts.append(msg)
        magic = 777000

        self.client.send_order(
            symbol="USDJPY",
            order_type=OrderType.BUY,
            lots=Decimal("0.20"),
            sl=Decimal("149.50"),
            tp=Decimal("152.00"),
            magic=magic,
        )

        report = self.client.poll_order_confirmation(magic=magic, timeout_sec=0.4, poll_interval_sec=0.1)
        self.assertIsNone(report)
        self.assertEqual(len(alerts), 1)
        self.assertIn("UNCONFIRMED", alerts[0])

    def test_read_closed_bars(self) -> None:
        t0 = datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc)
        candles = [
            Candle(timestamp=t0, open=1.0800, high=1.0810, low=1.0795, close=1.0805, volume=100.0),
            Candle(timestamp=t0 + timedelta(minutes=5), open=1.0805, high=1.0820, low=1.0800, close=1.0815, volume=120.0),
        ]
        self.client.write_mock_bars("EURUSD", "M5", candles)

        loaded = self.client.read_closed_bars("EURUSD", "M5")
        self.assertEqual(len(loaded), 2)
        self.assertAlmostEqual(loaded[0].close, 1.0805, places=4)
        self.assertAlmostEqual(loaded[1].high, 1.0820, places=4)


class TestPositionSizer(unittest.TestCase):
    """Tests for dynamic lot sizing and currency pip value calculation (Hard Rule 3)."""

    def setUp(self) -> None:
        self.sizer = PositionSizer(
            account_currency="USD",
            default_risk_pct=Decimal("0.015"),  # 1.5%
            min_lot=Decimal("0.01"),
            max_lot=Decimal("50.00"),
        )

    def test_pip_size(self) -> None:
        self.assertEqual(PositionSizer.get_pip_size("EURUSD"), Decimal("0.0001"))
        self.assertEqual(PositionSizer.get_pip_size("USDJPY"), Decimal("0.01"))
        self.assertEqual(PositionSizer.get_pip_size("EURJPY"), Decimal("0.01"))

    def test_pip_value_usd(self) -> None:
        # Quote currency USD: always $10.00 / lot (including broker suffixes like EURUSDm)
        self.assertEqual(self.sizer.get_pip_value_usd("EURUSD"), Decimal("10.00"))
        self.assertEqual(self.sizer.get_pip_value_usd("EURUSDm"), Decimal("10.00"))
        self.assertEqual(self.sizer.get_pip_value_usd("GBPUSD"), Decimal("10.00"))

        # Base currency USD: (100,000 * 0.01) / 150.00 = 6.67
        rates = {"USDJPY": Decimal("150.00")}
        pip_val_jpy = self.sizer.get_pip_value_usd("USDJPY", rates=rates)
        self.assertEqual(pip_val_jpy, Decimal("6.67"))
        pip_val_jpym = self.sizer.get_pip_value_usd("USDJPYm", rates=rates)
        self.assertEqual(pip_val_jpym, Decimal("6.67"))

    def test_calculate_lots_eurusd(self) -> None:
        # Balance = $10,000, Risk = 1.5% ($150)
        # Stop loss = 15 pips
        # Pip value = $10.00 / lot
        # Raw lots = 150 / (15 * 10) = 1.00 lot
        res = self.sizer.calculate_lots(
            account_balance=Decimal("10000.00"),
            stop_pips=Decimal("15.0"),
            symbol="EURUSD",
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.lots, Decimal("1.00"))
        self.assertEqual(res.risk_amount, Decimal("150.00"))

    def test_calculate_lots_round_down(self) -> None:
        # Balance = $10,000, Risk = 1.5% ($150)
        # Stop loss = 17 pips
        # Raw lots = 150 / (17 * 10) = 0.88235... -> rounds down to 0.88
        res = self.sizer.calculate_lots(
            account_balance=Decimal("10000.00"),
            stop_pips=Decimal("17.0"),
            symbol="EURUSD",
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.lots, Decimal("0.88"))

    def test_min_lot_rejection(self) -> None:
        # Tiny account: $100 balance, 1.5% risk = $1.50
        # Stop loss = 25 pips -> 25 * 10 = $250 / lot
        # Raw lots = 1.50 / 250 = 0.006 -> rounds down to 0.00 < 0.01 min
        res = self.sizer.calculate_lots(
            account_balance=Decimal("100.00"),
            stop_pips=Decimal("25.0"),
            symbol="EURUSD",
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.lots, Decimal("0.00"))
        self.assertIsNotNone(res.rejection_reason)

    def test_max_lot_cap(self) -> None:
        # Giant account: $10,000,000 balance, 1.5% risk = $150,000
        # Stop loss = 5 pips -> raw lots = 150000 / 50 = 3000 lots
        # Must be capped at max_lot 50.00
        res = self.sizer.calculate_lots(
            account_balance=Decimal("10000000.00"),
            stop_pips=Decimal("5.0"),
            symbol="EURUSD",
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.lots, Decimal("50.00"))

    def test_pip_value_usd_usdcad(self) -> None:
        # Base USD, Quote CAD at current price 1.42649 (as in Myfxbook calculator):
        # 100,000 * 0.0001 / 1.42649 = $7.01021 USD/pip
        pip_val = self.sizer.get_pip_value_usd("USDCAD", current_price=Decimal("1.42649"))
        self.assertEqual(pip_val, Decimal("7.01"))
        pip_val_m = self.sizer.get_pip_value_usd("USDCADm", current_price=Decimal("1.42649"))
        self.assertEqual(pip_val_m, Decimal("7.01"))

    def test_calculate_lots_usdcad_1pct_risk(self) -> None:
        # Account balance = $150.65, 1% risk = $1.51 USD
        # Rate: 1.42649 -> Pip value = $7.0102 USD/lot
        # 1.5 pip stop loss -> Raw lots = 1.51 / (1.5 * 7.01) = 0.1436 -> 0.14 lots
        # 0.14 lots * $7.01/pip = $0.9814/pip (approx $1/pip!)
        # Total risk = 0.14 * 1.5 * 7.01 = $1.47 <= $1.51 (1% risk)
        res = self.sizer.calculate_lots(
            account_balance=Decimal("150.65"),
            stop_pips=Decimal("1.5"),
            symbol="USDCADm",
            risk_pct=Decimal("0.01"),
            current_price=Decimal("1.42649"),
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.lots, Decimal("0.14"))
        self.assertEqual(res.risk_amount, Decimal("1.51"))

    def test_calculate_lots_usdcad_micro_stop_clamped(self) -> None:
        # If stop loss is micro (e.g. 0.2 pips), it clamps to 1.5 pips
        # Prevents error 134 margin rejections while capping lots at 0.14
        res = self.sizer.calculate_lots(
            account_balance=Decimal("150.65"),
            stop_pips=Decimal("0.2"),
            symbol="USDCADm",
            risk_pct=Decimal("0.01"),
            current_price=Decimal("1.42649"),
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.lots, Decimal("0.14"))

    def test_calculate_lots_usdcad_larger_stop_scales_down(self) -> None:
        # With a 3.0 pip stop loss, lots scale down to maintain 1% risk:
        # 1.51 / (3.0 * 7.01) = 0.0718 -> 0.07 lots
        res = self.sizer.calculate_lots(
            account_balance=Decimal("150.65"),
            stop_pips=Decimal("3.0"),
            symbol="USDCADm",
            risk_pct=Decimal("0.01"),
            current_price=Decimal("1.42649"),
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.lots, Decimal("0.07"))


class TestBridgeExecutor(unittest.TestCase):
    """Integration test suite for BridgeExecutor live loop."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="test_executor_")
        self.client = DWXClient(mt4_files_dir=self.test_dir, initial_backoff_ms=10)
        self.executor = BridgeExecutor(
            symbol="EURUSD",
            dwx_client=self.client,
            initial_balance=Decimal("10000.00"),
            risk_pct=Decimal("0.015"),
            confirmation_timeout_sec=0.8,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_magic_number_fits_32bit_signed_int(self) -> None:
        now = datetime(2026, 9, 24, 3, 25, tzinfo=timezone.utc)
        magic = generate_mt4_magic_number(now, sequence=1)
        self.assertGreater(magic, 0)
        self.assertLess(magic, 2_147_483_647)  # Fits in MT4 32-bit signed int

    def test_step_triggers_order_on_strategy_signal(self) -> None:
        t0 = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
        candles: list[Candle] = []

        # 1. 20 base candles
        for i in range(20):
            candles.append(Candle(
                timestamp=t0 + timedelta(minutes=5 * i),
                open=1.0850,
                high=1.0860,
                low=1.0840,
                close=1.0850,
                volume=100.0,
            ))

        idx = 20
        # 2. Candle 0 (preceding bearish candle)
        c0 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0850,
            high=1.0860,
            low=1.0820,
            close=1.0830,
            volume=150.0,
        )
        candles.append(c0)
        idx += 1

        # 3. Sweep Candle cS (Variant A BUY: pierces below 1.0820, closes >= 1.0820)
        cS = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0830,
            high=1.0845,
            low=1.0800,  # Pierces c0.low (1.0820)
            close=1.0835,  # Closes above c0.low
            volume=200.0,
        )
        candles.append(cS)
        idx += 1

        # 4. Confirmation candles (3 consecutive green candles)
        c1 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0835,
            high=1.0855,
            low=1.0830,
            close=1.0850,  # Green
            volume=180.0,
        )
        candles.append(c1)
        idx += 1

        c2 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0850,
            high=1.0870,
            low=1.0845,
            close=1.0865,  # Green
            volume=190.0,
        )
        candles.append(c2)
        idx += 1

        c3 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0865,
            high=1.0890,
            low=1.0860,
            close=1.0885,  # Green & confirms setup!
            volume=220.0,
        )
        candles.append(c3)

        # Write candles to MT4 bars file
        self.client.write_mock_bars("EURUSD", "M5", candles)

        # Step 1: Pre-populate mock MT4 EA response so confirmation succeeds
        # We know magic format:
        expected_magic = generate_mt4_magic_number(c3.timestamp, sequence=1)
        mock_report = ExecutionReport(
            ticket=987654,
            magic=expected_magic,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            lots=Decimal("0.42"),
            open_price=Decimal("1.08850"),
            sl=Decimal("1.08300"),
            tp=Decimal("1.14350"),
            status="FILLED",
        )
        self.client.write_mock_report(mock_report)

        # Run bridge step
        record = self.executor.step()

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "FILLED")
        self.assertEqual(record.ticket, 987654)
        self.assertEqual(record.direction, Direction.BUY)
        self.assertEqual(record.entry_price, Decimal("1.0885"))
        self.assertEqual(record.sl_price, Decimal("1.0830"))  # c1.low

        # 1:5 R:R verification
        risk = record.entry_price - record.sl_price
        reward = record.tp_price - record.entry_price
        self.assertEqual(reward, risk * Decimal("5"))

        # Step again on same data -> verify idempotency (no duplicate order)
        second_record = self.executor.step()
        self.assertIsNone(second_record)

    def test_step_multitimeframe_execution(self) -> None:
        """
        Verify BridgeExecutor.step_multitimeframe with M5 sweep detection and M1 3-candle confirmation.
        """
        t0 = datetime(2023, 9, 24, 8, 0, 0, tzinfo=timezone.utc)
        # M5 candles
        m5_0 = Candle(timestamp=t0, open=1.0850, high=1.0890, low=1.0840, close=1.0880, volume=100.0)
        m5_1 = Candle(timestamp=t0 + timedelta(minutes=5), open=1.0880, high=1.0910, low=1.0870, close=1.0875, volume=100.0)
        self.client.write_mock_bars("EURUSD", "M5", [m5_0, m5_1])

        # Step 1: Initial M1 bar to initialize last_processed_m1_time
        m1_init = Candle(timestamp=t0 + timedelta(minutes=9), open=1.0878, high=1.0882, low=1.0875, close=1.0876, volume=10.0)
        self.client.write_mock_bars("EURUSD", "M1", [m1_init])
        self.executor.step_multitimeframe()

        # Step 2: Feed confirming M1 bars (08:10, 08:11, 08:12)
        m1_0 = Candle(timestamp=t0 + timedelta(minutes=10), open=1.0875, high=1.0880, low=1.0868, close=1.0870, volume=10.0)
        m1_1 = Candle(timestamp=t0 + timedelta(minutes=11), open=1.0870, high=1.0872, low=1.0858, close=1.0860, volume=10.0)
        m1_2 = Candle(timestamp=t0 + timedelta(minutes=12), open=1.0860, high=1.0862, low=1.0848, close=1.0850, volume=10.0)
        self.client.write_mock_bars("EURUSD", "M1", [m1_init, m1_0, m1_1, m1_2])

        # Pre-populate mock execution report
        expected_magic = generate_mt4_magic_number(m1_2.timestamp, sequence=1)
        mock_report = ExecutionReport(
            ticket=554433,
            magic=expected_magic,
            symbol="EURUSD",
            order_type=OrderType.SELL,
            lots=Decimal("0.50"),
            open_price=Decimal("1.08500"),
            sl=Decimal("1.08800"),
            tp=Decimal("1.05500"),
            status="FILLED",
        )
        self.client.write_mock_report(mock_report)

        record = self.executor.step_multitimeframe()
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "FILLED")
        self.assertEqual(record.ticket, 554433)
        self.assertEqual(record.direction, Direction.SELL)
        self.assertEqual(record.entry_price, Decimal("1.0850"))
        self.assertEqual(record.sl_price, Decimal("1.0880"))

        # Verify 1:5 R:R
        risk = record.sl_price - record.entry_price
        reward = record.entry_price - record.tp_price
        self.assertEqual(reward, risk * Decimal("5"))

    def test_manage_active_trades_breakeven_at_1_to_2_rr_moves_sl_strictly_to_entry(self) -> None:
        """
        When profit reaches 1:2 RR (+2.0R), SL must be moved strictly to the exact entry price.
        """
        # Test BUY trade:
        # Entry = 1.08500, SL = 1.08300 (risk = 20 pips = 0.00200)
        # 1:2 RR target = 1.08500 + 2 * 0.00200 = 1.08900
        buy_trade = ActiveBridgeTrade(
            ticket=1001,
            magic=99901,
            symbol="EURUSD",
            direction=Direction.BUY,
            entry_price=Decimal("1.08500"),
            sl_price=Decimal("1.08300"),
            tp_price=Decimal("1.09500"),
            lots=Decimal("0.50"),
            risk_pips=Decimal("20.0"),
            partial_bank_pct=Decimal("0.0"),
            breakeven_trigger_r=Decimal("2.0"),
        )
        self.executor.active_trades[1001] = buy_trade

        # Bar 1: High only reaches 1.08700 (+1.0R) -> BE not triggered
        bar_sub_2r = Candle(
            timestamp=datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
            open=1.0855, high=1.0870, low=1.0850, close=1.0865, volume=50.0
        )
        self.executor._manage_active_trades(bar_sub_2r)
        self.assertFalse(buy_trade.breakeven_set)
        self.assertEqual(buy_trade.sl_price, Decimal("1.08300"))

        # Bar 2: High reaches 1.08910 (+2.05R, > 1:2 RR) -> BE triggered!
        bar_2r = Candle(
            timestamp=datetime(2026, 9, 24, 10, 1, tzinfo=timezone.utc),
            open=1.0865, high=1.0891, low=1.0860, close=1.0885, volume=50.0
        )
        self.executor._manage_active_trades(bar_2r)
        self.assertTrue(buy_trade.breakeven_set)
        # SL must be strictly at the exact entry price!
        self.assertEqual(buy_trade.sl_price, buy_trade.entry_price)
        self.assertEqual(buy_trade.sl_price, Decimal("1.08500"))

        # Verify MODIFY command dispatched to DWX_Commands.txt
        cmds_content = self.client.atomic_read(self.client.commands_file)
        lines = [line for line in cmds_content.splitlines() if line.strip()]
        self.assertGreater(len(lines), 0)
        last_cmd = json.loads(lines[-1])
        self.assertEqual(last_cmd["action"], "MODIFY")
        self.assertEqual(last_cmd["ticket"], 1001)
        self.assertEqual(Decimal(str(last_cmd["sl"])), Decimal("1.08500"))

        # Test SELL trade:
        # Entry = 1.08500, SL = 1.08800 (risk = 30 pips = 0.00300)
        # 1:2 RR target = 1.08500 - 2 * 0.00300 = 1.07900
        sell_trade = ActiveBridgeTrade(
            ticket=1002,
            magic=99902,
            symbol="EURUSD",
            direction=Direction.SELL,
            entry_price=Decimal("1.08500"),
            sl_price=Decimal("1.08800"),
            tp_price=Decimal("1.07000"),
            lots=Decimal("0.50"),
            risk_pips=Decimal("30.0"),
            partial_bank_pct=Decimal("0.0"),
            breakeven_trigger_r=Decimal("2.0"),
        )
        self.executor.active_trades[1002] = sell_trade

        # Bar 3: Low reaches 1.07890 (+2.03R, > 1:2 RR) -> BE triggered!
        bar_sell_2r = Candle(
            timestamp=datetime(2026, 9, 24, 10, 2, tzinfo=timezone.utc),
            open=1.0820, high=1.0825, low=1.0789, close=1.0795, volume=50.0
        )
        self.executor._manage_active_trades(bar_sell_2r)
        self.assertTrue(sell_trade.breakeven_set)
        # SL must be strictly at the exact entry price!
        self.assertEqual(sell_trade.sl_price, sell_trade.entry_price)
        self.assertEqual(sell_trade.sl_price, Decimal("1.08500"))


if __name__ == "__main__":
    unittest.main()
