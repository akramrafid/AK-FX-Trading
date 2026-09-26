"""tests/test_database.py
Exhaustive tests for SQLite persistence manager (database/sqlite_manager.py).

Verifies:
1. Database schema initialization, table creation, and indexes.
2. Candle batch insertion, deduplication (INSERT OR IGNORE), and retrieval.
3. Trade signal storage and retrieval.
4. Order lifecycle tracking (submission, fill updates, closures).
5. Closed trade journaling with realized PnL.
6. Daily metrics upsert and history.
7. Audit log append and retrieval.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from bridge.dwx_client import DWXClient, ExecutionReport, OrderType
from bridge.executor import BridgeExecutor, generate_mt4_magic_number
from bridge.sizing import PositionSizer
from database.sqlite_manager import TradingDatabase
from engine.models import Candle, Direction, TradeSignal


class TestTradingDatabase(unittest.TestCase):
    """Unit tests for SQLite database manager."""

    def setUp(self) -> None:
        # Use in-memory SQLite database for deterministic, fast testing
        self.db = TradingDatabase(":memory:")

    def test_init_schema(self) -> None:
        """Verify that all core tables are created successfully."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cur.fetchall()}

        expected_tables = {
            "candles",
            "trade_signals",
            "orders",
            "trade_journal",
            "daily_metrics",
            "audit_logs",
        }
        self.assertTrue(expected_tables.issubset(tables))

    def test_save_and_retrieve_candles(self) -> None:
        """Verify batch candle saving, deduplication, and ascending chronological ordering."""
        t0 = datetime(2026, 9, 24, 8, 0, 0, tzinfo=timezone.utc)
        candles = [
            Candle(
                timestamp=t0 + timedelta(minutes=5 * i),
                open=1.1370 + (i * 0.0001),
                high=1.1375 + (i * 0.0001),
                low=1.1365 + (i * 0.0001),
                close=1.1372 + (i * 0.0001),
                volume=100.0 + i,
            )
            for i in range(5)
        ]

        inserted = self.db.save_candles(candles, symbol="EURUSDm", timeframe="M5")
        self.assertEqual(inserted, 5)

        # Deduplication: Re-inserting existing candles should ignore duplicates
        reinserted = self.db.save_candles(candles, symbol="EURUSDm", timeframe="M5")
        self.assertEqual(reinserted, 0)

        # Retrieve candles
        retrieved = self.db.get_recent_candles(symbol="EURUSDm", timeframe="M5", limit=10)
        self.assertEqual(len(retrieved), 5)
        # Should be chronologically ascending
        self.assertEqual(retrieved[0].timestamp, t0)
        self.assertAlmostEqual(retrieved[0].open, 1.1370, places=4)
        self.assertEqual(retrieved[-1].timestamp, t0 + timedelta(minutes=20))

    def test_save_and_retrieve_signals(self) -> None:
        """Verify trade signal storage with 5:1 R:R parameters."""
        sig_time = datetime(2026, 9, 24, 8, 30, 0, tzinfo=timezone.utc)
        signal = TradeSignal(
            direction="BUY",
            entry_price=1.13750,
            stop_loss=1.13650,
            take_profit=1.14250,
            risk_distance=0.00100,
            reward_distance=0.00500,
            reward_risk_ratio=5.0,
            sweep_type="VARIANT_A",
            sweep_candle_index=1,
            confirmation_indices=(2, 3, 4),
            timestamp=sig_time,
        )

        sig_id = self.db.save_signal(
            signal=signal,
            symbol="EURUSDm",
            timeframe="M5",
            executed=True,
            rejection_reason="",
        )
        self.assertGreater(sig_id, 0)

        signals = self.db.get_signals(symbol="EURUSDm", limit=10)
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s["direction"], "BUY")
        self.assertAlmostEqual(s["entry_price"], 1.13750)
        self.assertAlmostEqual(s["stop_loss"], 1.13650)
        self.assertAlmostEqual(s["take_profit"], 1.14250)
        self.assertAlmostEqual(s["rr_ratio"], 5.0)
        self.assertEqual(s["executed"], 1)

    def test_order_lifecycle_tracking(self) -> None:
        """Verify order insertion and subsequent fill updates."""
        order_id = self.db.save_order(
            command_id="cmd_1001",
            magic_number=92408301,
            symbol="EURUSDm",
            direction="BUY",
            lots=0.15,
            target_entry=1.13750,
            stop_loss=1.13650,
            take_profit=1.14750,
            status="SUBMITTED",
        )
        self.assertGreater(order_id, 0)

        # Update order on MT4 fill confirmation
        updated = self.db.update_order_fill(
            magic_number=92408301,
            ticket=7891234,
            fill_price=1.13752,
            slippage_pips=0.2,
            status="FILLED",
        )
        self.assertTrue(updated)

        orders = self.db.get_orders(limit=10)
        self.assertEqual(len(orders), 1)
        o = orders[0]
        self.assertEqual(o["magic_number"], 92408301)
        self.assertEqual(o["ticket"], 7891234)
        self.assertEqual(o["status"], "FILLED")
        self.assertAlmostEqual(o["fill_price"], 1.13752)
        self.assertAlmostEqual(o["slippage_pips"], 0.2)

    def test_trade_journal_recording(self) -> None:
        """Verify journaling of closed trades."""
        journal_id = self.db.record_closed_trade(
            ticket=7891234,
            magic_number=92408301,
            symbol="EURUSDm",
            direction="BUY",
            open_time="2026-09-24 08:30:00",
            close_time="2026-09-24 09:15:00",
            open_price=1.13750,
            close_price=1.14750,
            stop_loss=1.13650,
            take_profit=1.14750,
            lots=0.15,
            realized_pnl=150.00,
            exit_reason="TP",
            environment="LIVE",
        )
        self.assertGreater(journal_id, 0)

        entries = self.db.get_journal_entries(limit=10)
        self.assertEqual(len(entries), 1)
        j = entries[0]
        self.assertEqual(j["ticket"], 7891234)
        self.assertEqual(j["exit_reason"], "TP")
        self.assertAlmostEqual(j["realized_pnl"], 150.00)

    def test_daily_metrics_upsert(self) -> None:
        """Verify daily performance recording and update on subsequent trades."""
        self.db.save_daily_metrics(
            trade_date="2026-09-24",
            starting_balance=500.00,
            closing_equity=575.00,
            realized_pnl=75.00,
            trade_count=1,
            win_count=1,
            loss_count=0,
            max_drawdown_pct=0.5,
            circuit_breaker_tripped=False,
        )

        metrics = self.db.get_daily_metrics(limit=1)
        self.assertEqual(len(metrics), 1)
        m = metrics[0]
        self.assertEqual(m["trade_date"], "2026-09-24")
        self.assertAlmostEqual(m["starting_balance"], 500.00)
        self.assertAlmostEqual(m["realized_pnl"], 75.00)
        self.assertEqual(m["trade_count"], 1)

        # Update metrics for the same day
        self.db.save_daily_metrics(
            trade_date="2026-09-24",
            starting_balance=500.00,
            closing_equity=650.00,
            realized_pnl=150.00,
            trade_count=2,
            win_count=2,
            loss_count=0,
            max_drawdown_pct=0.5,
            circuit_breaker_tripped=False,
        )

        metrics_after = self.db.get_daily_metrics(limit=1)
        self.assertEqual(len(metrics_after), 1)
        self.assertAlmostEqual(metrics_after[0]["realized_pnl"], 150.00)
        self.assertEqual(metrics_after[0]["trade_count"], 2)

    def test_audit_logs(self) -> None:
        """Verify operational audit logging."""
        log_id = self.db.log_audit_event(
            event_type="CIRCUIT_BREAKER_TRIPPED",
            source="RiskGuardrails",
            details={"daily_loss_pct": 0.035, "threshold": 0.03},
        )
        self.assertGreater(log_id, 0)

        logs = self.db.get_audit_logs(limit=10)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["event_type"], "CIRCUIT_BREAKER_TRIPPED")
        self.assertIn("0.035", logs[0]["details"])

    def test_file_persistence(self) -> None:
        """Verify on-disk SQLite database file creation and directory resolution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "sub" / "test_trading.db"
            disk_db = TradingDatabase(db_file)
            self.assertTrue(db_file.is_file())

            disk_db.log_audit_event("BOOT", "Test", {"status": "ok"})
            logs = disk_db.get_audit_logs(limit=5)
            self.assertEqual(len(logs), 1)


class TestBridgeDatabaseIntegration(unittest.TestCase):
    """End-to-end tests verifying BridgeExecutor persists candles, signals, and orders to TradingDatabase."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="test_bridge_db_")
        self.dwx = DWXClient(mt4_files_dir=self.test_dir, initial_backoff_ms=10, max_backoff_ms=100)
        self.db = TradingDatabase(":memory:")
        self.sizer = PositionSizer(default_risk_pct=Decimal("0.015"))
        self.executor = BridgeExecutor(
            symbol="EURUSDm",
            dwx_client=self.dwx,
            position_sizer=self.sizer,
            db=self.db,
            timeframe="M5",
            initial_balance=Decimal("500.00"),
            risk_pct=Decimal("0.015"),
            confirmation_timeout_sec=0.8,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_step_persists_candles_and_executes_signal_to_db(self) -> None:
        """Verify that BridgeExecutor automatically writes ingested candles, signal, and filled order to SQLite."""
        t0 = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
        candles: list[Candle] = []

        # 20 base candles
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
        # Candle 0 (preceding bearish candle)
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

        # Sweep Candle cS (Variant A BUY)
        cS = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0830,
            high=1.0845,
            low=1.0800,
            close=1.0835,
            volume=200.0,
        )
        candles.append(cS)
        idx += 1

        # 3 confirmation candles
        c1 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0835,
            high=1.0855,
            low=1.0830,
            close=1.0850,
            volume=180.0,
        )
        candles.append(c1)
        idx += 1

        c2 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0850,
            high=1.0870,
            low=1.0845,
            close=1.0865,
            volume=190.0,
        )
        candles.append(c2)
        idx += 1

        c3 = Candle(
            timestamp=t0 + timedelta(minutes=5 * idx),
            open=1.0865,
            high=1.0890,
            low=1.0860,
            close=1.0885,
            volume=220.0,
        )
        candles.append(c3)

        # Write candles to MT4 mock bars file
        self.dwx.write_mock_bars("EURUSDm", "M5", candles)

        # Pre-populate mock MT4 EA response for order confirmation
        expected_magic = generate_mt4_magic_number(c3.timestamp, sequence=1)
        mock_report = ExecutionReport(
            ticket=555888,
            magic=expected_magic,
            symbol="EURUSDm",
            order_type=OrderType.BUY,
            lots=Decimal("0.02"),
            open_price=Decimal("1.08850"),
            sl=Decimal("1.08300"),
            tp=Decimal("1.14350"),
            status="FILLED",
        )
        self.dwx.write_mock_report(mock_report)

        # Run bridge execution cycle
        record = self.executor.step()

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "FILLED")
        self.assertEqual(record.ticket, 555888)

        # 1. Verify Candles persisted in SQLite
        db_candles = self.db.get_recent_candles(symbol="EURUSDm", timeframe="M5", limit=50)
        self.assertEqual(len(db_candles), len(candles))
        self.assertEqual(db_candles[0].timestamp, candles[0].timestamp)
        self.assertEqual(db_candles[-1].timestamp, candles[-1].timestamp)

        # 2. Verify Trade Signal persisted in SQLite
        signals = self.db.get_signals(symbol="EURUSDm", limit=10)
        self.assertEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig["direction"], "BUY")
        self.assertEqual(sig["executed"], 1)
        self.assertAlmostEqual(sig["entry_price"], 1.0885)
        self.assertAlmostEqual(sig["stop_loss"], 1.0830)
        self.assertAlmostEqual(sig["rr_ratio"], 5.0)

        # 3. Verify Order persisted in SQLite with FILLED state
        orders = self.db.get_orders(limit=10)
        self.assertEqual(len(orders), 1)
        ord_rec = orders[0]
        self.assertEqual(ord_rec["magic_number"], expected_magic)
        self.assertEqual(ord_rec["ticket"], 555888)
        self.assertEqual(ord_rec["status"], "FILLED")
        self.assertAlmostEqual(ord_rec["fill_price"], 1.08850)

        # 4. Verify Audit Log recorded order fill
        logs = self.db.get_audit_logs(limit=10)
        event_types = [entry["event_type"] for entry in logs]
        self.assertIn("ORDER_FILLED", event_types)


if __name__ == "__main__":
    unittest.main()
