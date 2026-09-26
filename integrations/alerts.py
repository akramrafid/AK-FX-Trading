"""integrations/alerts.py
Production multi-channel notification and alert dispatcher for AK Forex Trading.

Supported channels:
- Telegram Bot API (direct HTTPS request via standard library urllib)
- Generic HTTP Webhook (Discord / Slack / PagerDuty / Custom Webhook)
- Structured logging fallback

Zero third-party dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("alerts")


class AlertSeverity(str, Enum):
    """Urgency level of the alert."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class AlertMessage:
    """Standardized representation of an operational notification."""
    title: str
    body: str
    severity: AlertSeverity = AlertSeverity.INFO
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def format_text(self) -> str:
        icon = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
        }.get(self.severity, "📢")
        ts_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"{icon} [{self.severity.value}] {self.title}\n{ts_str}\n\n{self.body}"


class AlertDispatcher:
    """Dispatches notifications to configured destinations (Telegram, Webhook, Logger)."""

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self.telegram_token = telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.webhook_url = webhook_url or os.environ.get("ALERT_WEBHOOK_URL")
        self.timeout_sec = timeout_sec

        self.history: List[AlertMessage] = []

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def has_webhook(self) -> bool:
        return bool(self.webhook_url)

    def dispatch(
        self,
        title: str,
        body: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AlertMessage:
        """Publishes an alert across all active channels."""
        msg = AlertMessage(
            title=title,
            body=body,
            severity=severity,
            metadata=metadata or {},
        )
        self.history.append(msg)

        # 1. Log locally
        log_text = msg.format_text()
        if severity == AlertSeverity.CRITICAL:
            logger.critical(log_text)
        elif severity == AlertSeverity.WARNING:
            logger.warning(log_text)
        else:
            logger.info(log_text)

        # 2. Dispatch Telegram if configured
        if self.has_telegram:
            self._send_telegram(msg)

        # 3. Dispatch Webhook if configured
        if self.has_webhook:
            self._send_webhook(msg)

        return msg

    def _send_telegram(self, msg: AlertMessage) -> bool:
        """Sends message payload to Telegram Bot API."""
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": msg.format_text(),
            "parse_mode": "HTML",
        }
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.error(f"Failed to deliver Telegram alert: {exc}")
            return False

    def _send_webhook(self, msg: AlertMessage) -> bool:
        """Sends message payload to standard HTTP webhook."""
        if not self.webhook_url:
            return False
        payload = {
            "title": msg.title,
            "severity": msg.severity.value,
            "text": msg.body,
            "timestamp": msg.timestamp.isoformat(),
            "metadata": msg.metadata,
        }
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return 200 <= resp.status < 300
        except Exception as exc:
            logger.error(f"Failed to deliver webhook alert: {exc}")
            return False

    def create_guardrail_callback(self) -> Callable[[str], None]:
        """Creates a callback function compatible with RiskGuardrails.alert_callback."""
        def callback(alert_text: str) -> None:
            severity = AlertSeverity.CRITICAL if "CIRCUIT BREAKER" in alert_text or "EMERGENCY" in alert_text else AlertSeverity.WARNING
            self.dispatch(
                title="Risk Guardrail Event",
                body=alert_text,
                severity=severity,
            )
        return callback

    def create_watchdog_callback(self) -> Callable[[str], None]:
        """Creates a callback function compatible with BridgeWatchdog.alert_callback."""
        def callback(alert_text: str) -> None:
            self.dispatch(
                title="Bridge Watchdog Alert",
                body=alert_text,
                severity=AlertSeverity.CRITICAL,
            )
        return callback
