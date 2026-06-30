"""Persist alerts and fan out to Slack."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import AlertNotification
from app.notifications.kinds import SEVERITY, AlertKind
from app.notifications.messages import AlertContent
from app.notifications.slack import send_slack_alert

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Deduplicated alert dispatch (DB + optional Slack) with startup grace window."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._seen_keys: set[str] = set()
        self._http: httpx.AsyncClient | None = None
        self._live_after: datetime = datetime.now(timezone.utc)
        self._startup_finalized: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.settings.notifications_enabled)

    @property
    def is_live(self) -> bool:
        """True when grace elapsed and startup seed completed."""
        return self._startup_finalized

    @property
    def live_after(self) -> datetime:
        return self._live_after

    @property
    def armed(self) -> bool:
        """Backward-compatible alias for is_live."""
        return self.is_live

    def begin_startup_grace(self, seconds: int) -> datetime:
        """Silence Slack until N seconds after collector start (fresh docker up)."""
        self._live_after = datetime.now(timezone.utc) + timedelta(seconds=max(seconds, 0))
        self._startup_finalized = False
        return self._live_after

    def enable_resume_mode(self) -> None:
        """Skip grace + sync gates (only when NOTIFICATION_SKIP_STARTUP_GRACE=true)."""
        self._live_after = datetime.now(timezone.utc)
        self._startup_finalized = True

    def grace_elapsed(self) -> bool:
        return datetime.now(timezone.utc) >= self._live_after

    def should_finalize_startup(self) -> bool:
        return not self._startup_finalized and self.grace_elapsed()

    def mark_startup_finalized(self) -> None:
        self._startup_finalized = True

    def is_seen(self, source_key: str) -> bool:
        return source_key in self._seen_keys

    def mark_seen(self, source_key: str) -> None:
        self._seen_keys.add(source_key)

    @property
    def seen_key_count(self) -> int:
        return len(self._seen_keys)

    async def hydrate(self, session: AsyncSession) -> int:
        """Load existing source keys — avoids DB lookup on every notify."""
        result = await session.execute(select(AlertNotification.source_key))
        keys = set(result.scalars().all())
        self._seen_keys.update(keys)
        return len(keys)

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.market_http_timeout_seconds)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def notify_content(self, session: AsyncSession, content: AlertContent) -> bool:
        return await self.notify(
            session,
            kind=content.kind,
            title=content.title,
            message=content.message,
            source_key=content.source_key,
            detail=content.detail,
            subnet=content.subnet,
            severity=content.severity,
        )

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

        if not self._startup_finalized:
            return False

        if source_key in self._seen_keys:
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
        self._seen_keys.add(source_key)

        if self.settings.slack_webhook_url:
            sent = await send_slack_alert(
                settings=self.settings,
                kind=kind,
                title=title,
                message=message,
                detail=payload,
                subnet=subnet,
                client=self._http_client(),
            )
            row.slack_sent = sent
            if not sent:
                logger.error("ALERT %s saved to DB but Slack delivery FAILED", kind)
        else:
            logger.error(
                "ALERT %s saved to DB but SLACK_WEBHOOK_URL not set — message not sent",
                kind,
            )

        logger.info("ALERT %s %s — %s (slack=%s)", kind, source_key, title, row.slack_sent)
        return True
