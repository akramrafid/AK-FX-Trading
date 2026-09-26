"""integrations package - External communication, alerting, and telemetry."""
from integrations.alerts import AlertDispatcher, AlertMessage, AlertSeverity

__all__ = ["AlertDispatcher", "AlertMessage", "AlertSeverity"]
