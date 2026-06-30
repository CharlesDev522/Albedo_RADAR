"""Notification config diagnostics."""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def log_notification_config(settings: Settings, *, live: bool | None = None) -> bool:
    """Log Slack notification config; return True if webhook is configured."""
    enabled = bool(settings.notifications_enabled)
    webhook = (settings.slack_webhook_url or "").strip()
    ok = bool(webhook)

    if not enabled:
        logger.info("notifications: DISABLED (NOTIFICATIONS_ENABLED=false)")
        return False

    if not ok:
        logger.error(
            "notifications: ENABLED but SLACK_WEBHOOK_URL is missing — "
            "copy .env.example to .env and set your webhook URL, then restart collector"
        )
        return False

    live_s = "unknown" if live is None else ("yes" if live else f"no (grace {settings.notification_grace_seconds}s)")
    logger.info(
        "notifications: enabled webhook=set channel=%s app=%s live=%s",
        settings.slack_channel or "(webhook default)",
        settings.slack_app_name,
        live_s,
    )
    return True
