"""Per-kind Slack notification preferences stored in Redis."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, get_args

import redis.asyncio as aioredis

from app.config import Settings
from app.notifications.kinds import AlertKind

logger = logging.getLogger(__name__)

NOTIFICATION_PREFERENCES_KEY = "minerwatch:notification_preferences"
PREFERENCES_CACHE_SECONDS = 5.0

# Extra kinds outside AlertKind (e.g. GitHub watch bypasses the dispatcher).
EXTRA_NOTIFICATION_KINDS = ("github_commit",)

ALL_NOTIFICATION_KINDS: tuple[str, ...] = get_args(AlertKind) + EXTRA_NOTIFICATION_KINDS

DEFAULT_KIND_ENABLED: dict[str, bool] = {
    "crown_won": True,
    "crown_lost": True,
    "duel_new": True,
    "king_defended": True,
    "slot_new": False,
    "slot_changed": False,
    "commit_new": False,
    "commit_updated": False,
    "repo_new": False,
    "repo_updated": False,
    "reg_fee_low": True,
    "eval_dq": True,
    "eval_queue_entered": True,
    "github_commit": True,
}

KIND_LABELS: dict[str, str] = {
    "eval_queue_entered": "Eval validation queue",
    "eval_dq": "Eval disqualified / infra failed",
    "duel_new": "New duel started",
    "crown_won": "New king crowned",
    "king_defended": "King defended",
    "crown_lost": "King dethroned",
    "reg_fee_low": "Registration fee below threshold",
    "repo_new": "New Hippius / Hugging Face repo",
    "repo_updated": "Hub manifest updated",
    "commit_new": "On-chain commitment revealed",
    "commit_updated": "On-chain commitment changed",
    "slot_new": "Slot commitment published",
    "slot_changed": "Slot commitment changed",
    "github_commit": "GitHub watched repo commit",
}

KIND_GROUPS: list[dict[str, Any]] = [
    {
        "id": "eval",
        "label": "Eval & duels",
        "kinds": [
            "eval_queue_entered",
            "eval_dq",
            "duel_new",
            "crown_won",
            "king_defended",
            "crown_lost",
        ],
    },
    {
        "id": "economics",
        "label": "Subnet economics",
        "kinds": ["reg_fee_low"],
    },
    {
        "id": "repos",
        "label": "Repo tracking",
        "kinds": ["repo_new", "repo_updated"],
    },
    {
        "id": "onchain",
        "label": "On-chain commits",
        "kinds": ["commit_new", "commit_updated", "slot_new", "slot_changed"],
    },
    {
        "id": "github",
        "label": "GitHub watch",
        "kinds": ["github_commit"],
    },
]


def _default_payload() -> dict[str, Any]:
    return {
        "notifications_enabled": None,
        "kinds": dict(DEFAULT_KIND_ENABLED),
        "updated_at": None,
    }


def merge_preferences(
    stored: dict[str, Any] | None,
    *,
    notifications_enabled: bool | None = None,
    kinds: dict[str, bool] | None = None,
) -> dict[str, Any]:
    base = _default_payload()
    if stored:
        if stored.get("notifications_enabled") is not None:
            base["notifications_enabled"] = bool(stored["notifications_enabled"])
        stored_kinds = stored.get("kinds")
        if isinstance(stored_kinds, dict):
            for key, value in stored_kinds.items():
                if key in ALL_NOTIFICATION_KINDS:
                    base["kinds"][key] = bool(value)

    if notifications_enabled is not None:
        base["notifications_enabled"] = notifications_enabled

    if kinds:
        for key, value in kinds.items():
            if key in ALL_NOTIFICATION_KINDS:
                base["kinds"][key] = bool(value)

    base["updated_at"] = datetime.now(timezone.utc).isoformat()
    return base


def effective_kind_enabled(payload: dict[str, Any], kind: str) -> bool:
    kinds = payload.get("kinds") or {}
    if kind in kinds:
        return bool(kinds[kind])
    return DEFAULT_KIND_ENABLED.get(kind, True)


def build_settings_response(
    *,
    settings: Settings,
    stored: dict[str, Any] | None,
    webhook_configured: bool,
) -> dict[str, Any]:
    payload = merge_preferences(stored)
    master = (
        bool(payload["notifications_enabled"])
        if payload.get("notifications_enabled") is not None
        else bool(settings.notifications_enabled)
    )
    kinds_out = {
        kind: {
            "enabled": effective_kind_enabled(payload, kind),
            "label": KIND_LABELS.get(kind, kind),
            "default_enabled": DEFAULT_KIND_ENABLED.get(kind, True),
        }
        for kind in ALL_NOTIFICATION_KINDS
    }
    return {
        "notifications_enabled": master,
        "env_notifications_enabled": bool(settings.notifications_enabled),
        "stored_notifications_enabled": payload.get("notifications_enabled"),
        "webhook_configured": webhook_configured,
        "slack_channel": settings.slack_channel,
        "kinds": kinds_out,
        "groups": KIND_GROUPS,
        "updated_at": payload.get("updated_at"),
    }


class NotificationPreferencesStore:
    """In-memory cache over Redis-backed notification toggles."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._payload: dict[str, Any] = _default_payload()
        self._loaded_at: float = 0.0

    @property
    def notifications_enabled(self) -> bool:
        if not self.settings.notifications_enabled:
            return False
        stored = self._payload.get("notifications_enabled")
        if stored is not None:
            return bool(stored)
        return True

    def is_kind_enabled(self, kind: str) -> bool:
        if not self.notifications_enabled:
            return False
        return effective_kind_enabled(self._payload, kind)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._payload)

    async def refresh(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._loaded_at < PREFERENCES_CACHE_SECONDS:
            return
        loaded = await read_notification_preferences(self.settings.redis_url)
        self._payload = merge_preferences(loaded)
        self._loaded_at = now

    async def load(self) -> dict[str, Any]:
        await self.refresh(force=True)
        return self.snapshot()

    async def save(
        self,
        *,
        notifications_enabled: bool | None = None,
        kinds: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        current = await read_notification_preferences(self.settings.redis_url)
        merged = merge_preferences(
            current,
            notifications_enabled=notifications_enabled,
            kinds=kinds,
        )
        await write_notification_preferences(self.settings.redis_url, merged)
        self._payload = merged
        self._loaded_at = time.monotonic()
        return merged


async def read_notification_preferences(redis_url: str) -> dict[str, Any] | None:
    redis: aioredis.Redis | None = None
    try:
        redis = aioredis.from_url(redis_url, decode_responses=True)
        raw = await redis.get(NOTIFICATION_PREFERENCES_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("failed to read notification preferences from redis", exc_info=True)
        return None
    finally:
        if redis is not None:
            await redis.close()


async def write_notification_preferences(redis_url: str, payload: dict[str, Any]) -> None:
    redis: aioredis.Redis | None = None
    try:
        redis = aioredis.from_url(redis_url, decode_responses=True)
        await redis.set(
            NOTIFICATION_PREFERENCES_KEY,
            json.dumps(payload, separators=(",", ":")),
        )
    except Exception:
        logger.exception("failed to write notification preferences to redis")
        raise
    finally:
        if redis is not None:
            await redis.close()
