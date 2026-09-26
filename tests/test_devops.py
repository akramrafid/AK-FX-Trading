"""tests/test_devops.py
DevOps, Watchdog, Alerting, and Production Configuration Test Suite.

Verifies:
1. BridgeWatchdog heartbeat monitoring, file freshness inspection, state transitions,
   and automatic emergency halt tripping on communication loss.
2. AlertDispatcher multi-channel alerting (Telegram, Webhooks, logging), formatting,
   and risk guardrail / watchdog callback integration.
3. AppConfig / load_config validation, environment variable parsing, and safety bounds.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from bridge.dwx_client import DWXClient
from bridge.watchdog import BridgeWatchdog, HealthState, WatchdogStatus
from config import AppConfig, load_config, parse_simple_env_file
from engine.models import Candle
from integrations.alerts import AlertDispatcher, AlertMessage, AlertSeverity
from risk.guardrails import RiskGuardrails
from risk.models import AccountState, RiskLimits, TradeRejectionReason


class TestBridgeWatchdog(unittest.TestCase):
    """Exhaustive tests for process supervision and MT4 heartbeat watchdog."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.dwx = DWXClient(self.temp_dir)
        self.limits = RiskLimits(
            max_daily_loss_pct=Decimal("0.03"),
            max_open_trades=1,
            max_daily_trades=3,
            max_spread_pips=Decimal("2.5"),
            session_start_hour_utc=7,
            session_end_hour_utc=17,
        )
        self.guardrails = RiskGuardrails(self.limits)
        self.alert_mock = MagicMock()
        self.watchdog = BridgeWatchdog(
            dwx_client=self.dwx,
            risk_guardrails=self.guardrails,
            max_heartbeat_age_sec=300.0,  # 5 minutes
            alert_callback=self.alert_mock,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initial_state_starting(self) -> None:
        status = self.watchdog.check_health()
        self.assertEqual(status.state, HealthState.STARTING)
        self.assertIsNone(status.last_heartbeat_utc)
        self.assertEqual(status.bars_processed, 0)
        self.assertEqual(status.orders_dispatched, 0)
        self.assertFalse(status.emergency_halt_active)

    def test_record_bar_received_and_order_dispatched(self) -> None:
        now = datetime.now(timezone.utc)
        self.watchdog.record_bar_received(now)
        self.watchdog.record_order_dispatched()

        status = self.watchdog.check_health(current_time=now + timedelta(seconds=10))
        self.assertEqual(status.state, HealthState.HEALTHY)
        self.assertEqual(status.bars_processed, 1)
        self.assertEqual(status.orders_dispatched, 1)
        self.assertAlmostEqual(status.heartbeat_age_sec, 10.0, places=1)

    def test_inspect_file_freshness(self) -> None:
        bars_file = self.dwx.get_bars_file("EURUSD", "M5")
        # Non-existent file
        freshness = self.watchdog.inspect_file_freshness("EURUSD", "M5")
        self.assertIsNone(freshness)

        # Create file
        with open(bars_file, "w", encoding="utf-8") as f:
            f.write("2026.09.24 07:00,1.1000,1.1010,1.0990,1.1005,100\n")

        freshness = self.watchdog.inspect_file_freshness("EURUSD", "M5")
        self.assertIsNotNone(freshness)
        self.assertIsInstance(freshness, datetime)

    def test_health_degraded_state(self) -> None:
        # Set heartbeat 200s ago (half age is 150s, limit is 300s)
        now = datetime.now(timezone.utc)
        t_prev = now - timedelta(seconds=200)
        self.watchdog.record_bar_received(t_prev)

        status = self.watchdog.check_health(current_time=now)
        self.assertEqual(status.state, HealthState.DEGRADED)
        self.assertIn("WARNING: Delayed bar feed", status.status_message)

    def test_health_stale_heartbeat_triggers_emergency_halt(self) -> None:
        # Set heartbeat 350s ago (exceeds 300s limit)
        now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        t_prev = now - timedelta(seconds=350)
        self.watchdog.record_bar_received(t_prev)

        status = self.watchdog.check_health(current_time=now)
        self.assertEqual(status.state, HealthState.STALE_HEARTBEAT)
        self.assertIn("CRITICAL: MT4 heartbeat stale", status.status_message)

        # Verify alert was triggered
        self.alert_mock.assert_called_once()
        self.assertIn("WATCHDOG ALERT: CRITICAL: MT4 heartbeat stale", self.alert_mock.call_args[0][0])

        # Verify emergency halt was tripped on risk guardrails
        self.assertTrue(self.guardrails.limits.emergency_halt)
        eval_result = self.guardrails.validate_trade(
            AccountState(
                starting_daily_balance=Decimal("10000.00"),
                current_balance=Decimal("10000.00"),
                current_equity=Decimal("10000.00"),
                realized_daily_pnl=Decimal("0.00"),
                unrealized_daily_pnl=Decimal("0.00"),
                open_trade_count=0,
                daily_trades_count=0,
                current_spread_pips=Decimal("1.2"),
                timestamp=now,
            ),
            proposed_lots=Decimal("0.10"),
            trade_time=now,
        )
        self.assertFalse(eval_result.is_allowed)
        self.assertEqual(eval_result.reason, TradeRejectionReason.EMERGENCY_STOP)

    def test_status_to_dict_serialization(self) -> None:
        now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        self.watchdog.record_bar_received(now)
        status = self.watchdog.check_health(current_time=now)
        data = status.to_dict()

        self.assertIn("state", data)
        self.assertIn("uptime_sec", data)
        self.assertIn("heartbeat_age_sec", data)
        self.assertIn("bars_processed", data)
        self.assertIn("orders_dispatched", data)
        self.assertIn("emergency_halt_active", data)
        self.assertIn("status_message", data)
        self.assertIn("timestamp", data)


class TestAlertDispatcher(unittest.TestCase):
    """Exhaustive tests for multi-channel alert dispatching and callbacks."""

    def test_alert_message_formatting(self) -> None:
        msg = AlertMessage(
            title="Trade Executed",
            body="BUY 0.15 lots @ 1.08500",
            severity=AlertSeverity.INFO,
            timestamp=datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc),
        )
        formatted = msg.format_text()
        self.assertIn("ℹ️ [INFO] Trade Executed", formatted)
        self.assertIn("2026-09-24 10:00:00 UTC", formatted)
        self.assertIn("BUY 0.15 lots @ 1.08500", formatted)

        crit_msg = AlertMessage(
            title="Circuit Breaker Tripped",
            body="Max daily loss reached",
            severity=AlertSeverity.CRITICAL,
        )
        self.assertIn("🚨 [CRITICAL]", crit_msg.format_text())

        warn_msg = AlertMessage(
            title="High Spread",
            body="Spread is 3.1 pips",
            severity=AlertSeverity.WARNING,
        )
        self.assertIn("⚠️ [WARNING]", warn_msg.format_text())

    def test_dispatch_records_history(self) -> None:
        dispatcher = AlertDispatcher()
        self.assertFalse(dispatcher.has_telegram)
        self.assertFalse(dispatcher.has_webhook)

        res = dispatcher.dispatch(
            title="System Starting",
            body="Initializing trading bridge",
            severity=AlertSeverity.INFO,
            metadata={"version": "1.0.0"},
        )
        self.assertEqual(len(dispatcher.history), 1)
        self.assertEqual(dispatcher.history[0].title, "System Starting")
        self.assertEqual(dispatcher.history[0].metadata["version"], "1.0.0")

    @patch("urllib.request.urlopen")
    def test_telegram_dispatch(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        dispatcher = AlertDispatcher(
            telegram_token="test_token_123",
            telegram_chat_id="chat_456",
        )
        self.assertTrue(dispatcher.has_telegram)

        dispatcher.dispatch("Test Alert", "Alert body", AlertSeverity.WARNING)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertIn("api.telegram.org/bottest_token_123/sendMessage", req.full_url)
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["chat_id"], "chat_456")
        self.assertIn("Test Alert", payload["text"])

    @patch("urllib.request.urlopen")
    def test_webhook_dispatch(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        dispatcher = AlertDispatcher(
            webhook_url="https://hooks.example.com/alerts",
        )
        self.assertTrue(dispatcher.has_webhook)

        dispatcher.dispatch(
            title="Risk Event",
            body="Max spread exceeded",
            severity=AlertSeverity.CRITICAL,
            metadata={"spread": 3.2},
        )

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "https://hooks.example.com/alerts")
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["title"], "Risk Event")
        self.assertEqual(payload["severity"], "CRITICAL")
        self.assertEqual(payload["metadata"]["spread"], 3.2)

    def test_guardrail_and_watchdog_callbacks(self) -> None:
        dispatcher = AlertDispatcher()
        guard_cb = dispatcher.create_guardrail_callback()
        watchdog_cb = dispatcher.create_watchdog_callback()

        # Circuit breaker alert -> CRITICAL
        guard_cb("CIRCUIT BREAKER: Daily loss exceeded 3.0%")
        self.assertEqual(len(dispatcher.history), 1)
        self.assertEqual(dispatcher.history[-1].severity, AlertSeverity.CRITICAL)

        # Minor warning alert -> WARNING
        guard_cb("Spread 2.8 exceeds limit 2.5")
        self.assertEqual(len(dispatcher.history), 2)
        self.assertEqual(dispatcher.history[-1].severity, AlertSeverity.WARNING)

        # Watchdog alert -> CRITICAL
        watchdog_cb("Heartbeat missing for 650s")
        self.assertEqual(len(dispatcher.history), 3)
        self.assertEqual(dispatcher.history[-1].severity, AlertSeverity.CRITICAL)


class TestConfig(unittest.TestCase):
    """Exhaustive tests for configuration loader and safety bounds validation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_simple_env_file(self) -> None:
        env_file = Path(self.temp_dir) / "test.env"
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("# Comment line\n")
            f.write("KEY_ONE=val1\n")
            f.write("KEY_TWO = 'quoted_val' \n")
            f.write('KEY_THREE="double_quoted"\n')
            f.write("\n")
            f.write("KEY_FOUR=has=equal=signs\n")

        parsed = parse_simple_env_file(env_file)
        self.assertEqual(parsed["KEY_ONE"], "val1")
        self.assertEqual(parsed["KEY_TWO"], "quoted_val")
        self.assertEqual(parsed["KEY_THREE"], "double_quoted")
        self.assertEqual(parsed["KEY_FOUR"], "has=equal=signs")

    def test_parse_missing_file_returns_empty_dict(self) -> None:
        parsed = parse_simple_env_file(Path(self.temp_dir) / "nonexistent.env")
        self.assertEqual(parsed, {})

    def test_app_config_validation_rules(self) -> None:
        # Valid config
        cfg = AppConfig(
            mt4_files_dir=Path(self.temp_dir),
            risk_pct=Decimal("0.015"),
            max_daily_loss_pct=Decimal("0.03"),
            max_open_trades=1,
            max_daily_trades=3,
            max_spread_pips=Decimal("2.5"),
        )
        self.assertEqual(cfg.symbol, "EURUSD")

        # Invalid risk_pct > 0.05
        with self.assertRaises(ValueError):
            AppConfig(mt4_files_dir=Path(self.temp_dir), risk_pct=Decimal("0.06"))

        # Invalid risk_pct <= 0
        with self.assertRaises(ValueError):
            AppConfig(mt4_files_dir=Path(self.temp_dir), risk_pct=Decimal("0"))

        # Invalid max_daily_loss_pct > 0.10
        with self.assertRaises(ValueError):
            AppConfig(mt4_files_dir=Path(self.temp_dir), max_daily_loss_pct=Decimal("0.15"))

        # Invalid max_open_trades < 1
        with self.assertRaises(ValueError):
            AppConfig(mt4_files_dir=Path(self.temp_dir), max_open_trades=0)

        # Invalid max_daily_trades < 1
        with self.assertRaises(ValueError):
            AppConfig(mt4_files_dir=Path(self.temp_dir), max_daily_trades=0)

        # Invalid max_spread_pips <= 0
        with self.assertRaises(ValueError):
            AppConfig(mt4_files_dir=Path(self.temp_dir), max_spread_pips=Decimal("0"))

    def test_load_config_from_file_and_env(self) -> None:
        env_file = Path(self.temp_dir) / ".env"
        mt4_folder = Path(self.temp_dir) / "my_mt4"
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"MT4_FILES_DIR={mt4_folder}\n")
            f.write("TRADING_SYMBOL=GBPUSD\n")
            f.write("ACCOUNT_INITIAL_BALANCE=25000.00\n")
            f.write("RISK_PER_TRADE_PCT=0.02\n")
            f.write("MAX_DAILY_LOSS_PCT=0.04\n")
            f.write("MAX_OPEN_TRADES=2\n")
            f.write("MAX_DAILY_TRADES=5\n")
            f.write("MAX_SPREAD_PIPS=2.0\n")
            f.write("SESSION_FILTER_ENABLED=false\n")
            f.write("TELEGRAM_BOT_TOKEN=tok_abc\n")
            f.write("TELEGRAM_CHAT_ID=chat_xyz\n")

        cfg = load_config(env_file)
        self.assertEqual(cfg.symbol, "GBPUSD")
        self.assertEqual(cfg.initial_balance, Decimal("25000.00"))
        self.assertEqual(cfg.risk_pct, Decimal("0.02"))
        self.assertEqual(cfg.max_daily_loss_pct, Decimal("0.04"))
        self.assertEqual(cfg.max_open_trades, 2)
        self.assertEqual(cfg.max_daily_trades, 5)
        self.assertEqual(cfg.max_spread_pips, Decimal("2.0"))
        self.assertFalse(cfg.session_filter_enabled)
        self.assertEqual(cfg.telegram_token, "tok_abc")
        self.assertEqual(cfg.telegram_chat_id, "chat_xyz")
        self.assertTrue(mt4_folder.exists())


if __name__ == "__main__":
    unittest.main()
