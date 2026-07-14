"""Collector notification startup state — published to Redis for API + logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import Settings

logger = logging.getLogger(__name__)

NOTIFICATION_STATUS_KEY = "minerwatch:notification_status"
NOTIFICATION_STARTUP_VERSION = "hub-probe-v3"


def build_notification_status(
    *,
    settings: Settings,
    is_live: bool,
    grace_elapsed: bool,
    live_after: datetime,
    collector_started_at: datetime,
    hub_probes: dict[int, int],
    blockers: list[str],
    seen_keys: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    age_s = int((now - collector_started_at).total_seconds())
    grace_remaining_s = max(int((live_after - now).total_seconds()), 0)
    return {
        "version": NOTIFICATION_STARTUP_VERSION,
        "is_live": is_live,
        "grace_elapsed": grace_elapsed,
        "grace_remaining_seconds": grace_remaining_s if not grace_elapsed else 0,
        "collector_uptime_seconds": age_s,
        "hub_probes": hub_probes,
        "min_hub_index_probes": settings.notification_min_hub_index_probes,
        "startup_max_seconds": settings.notification_startup_max_seconds,
        "grace_seconds": settings.notification_grace_seconds,
        "blockers": blockers,
        "seen_keys": seen_keys,
        "enabled": settings.notifications_enabled,
        "webhook_configured": bool((settings.slack_webhook_url or "").strip()),
        "updated_at": now.isoformat(),
    }


async def publish_notification_status(
    redis: aioredis.Redis | None,
    payload: dict[str, Any],
) -> None:
    if redis is None:
        return
    try:
        await redis.set(
            NOTIFICATION_STATUS_KEY,
            json.dumps(payload, separators=(",", ":")),
            ex=3600,
        )
    except Exception:
        logger.debug("failed to publish notification status to redis", exc_info=True)


async def read_notification_status(
    redis_url: str,
) -> dict[str, Any] | None:
    redis: aioredis.Redis | None = None
    try:
        redis = aioredis.from_url(redis_url, decode_responses=True)
        raw = await redis.get(NOTIFICATION_STATUS_KEY)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None
    finally:
        if redis is not None:
            await redis.close()
