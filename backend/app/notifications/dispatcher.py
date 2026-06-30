"""Persist alerts and fan out to Slack."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import AlertNotification
from app.notifications.kinds import SEVERITY, AlertKind
from app.notifications.slack import send_slack_alert

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Deduplicated alert dispatch (DB + optional Slack)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.notifications_enabled)

    async def notify(
        self,
        session: AsyncSession,
        *,
        kind: AlertKind,
        title: str,
        message: str,
        source_key: str,
        detail: dict[str, Any] | None = None,
        subnet: int | None = None,
        severity: str | None = None,
    ) -> bool:
        if not self.enabled:
            return False

        existing = await session.execute(
            select(AlertNotification.id).where(AlertNotification.source_key == source_key)
        )
        if existing.scalar_one_or_none() is not None:
            return False

        payload = detail or {}
        sev = severity or SEVERITY.get(kind, "medium")
        row = AlertNotification(
            kind=kind,
            severity=sev,
            title=title,
            message=message,
            detail=payload,
            source_key=source_key,
            subnet=subnet,
            slack_sent=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.flush()

        if self.settings.slack_webhook_url:
            sent = await send_slack_alert(
                settings=self.settings,
                kind=kind,
                title=title,
                message=message,
                detail=payload,
                subnet=subnet,
            )
            row.slack_sent = sent

        logger.info("ALERT %s %s — %s", kind, source_key, title)
        return True
