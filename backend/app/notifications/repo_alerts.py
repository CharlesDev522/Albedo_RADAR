"""Slack alerts when a new Hippius or Hugging Face repo is discovered."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.messages import build_repo_new_alert

logger = logging.getLogger(__name__)


def hub_repo_new_source_key(*, host: str, repo: str) -> str:
    """One notification per repo per host (ignores manifest digest churn)."""
    return f"repo_new:{host}:{repo}"


def _host_label(host: str) -> str:
    return "Hugging Face" if host == "huggingface" else "Hippius"


async def notify_new_hub_repo(
    session: AsyncSession,
    dispatcher: NotificationDispatcher | None,
    *,
    netuid: int,
    repo: str,
    host: str,
    uid: int | None = None,
    hotkey: str | None = None,
    coldkey: str | None = None,
    model_family: str | None = None,
    hub_digest: str | None = None,
    revision: str | None = None,
    commit_message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> bool:
    """Post Slack when a repo first appears on Hippius or Hugging Face."""
    if dispatcher is None or not dispatcher.enabled:
        return False

    host_key = host if host in ("hippius", "huggingface") else "hippius"
    payload_meta = {"host": host_key, **(meta or {})}
    source_key = hub_repo_new_source_key(host=host_key, repo=repo)
    alert = build_repo_new_alert(
        netuid=netuid,
        repo=repo,
        event_type="hub_repo_added",
        source_key=source_key,
        uid=uid,
        hotkey=hotkey,
        coldkey=coldkey,
        model_family=model_family,
        hub_digest=hub_digest,
        revision=revision,
        commit_message=commit_message,
        meta=payload_meta,
        host_label=_host_label(host_key),
    )
    try:
        sent = await dispatcher.notify_content(session, alert)
        if sent:
            logger.info("ALERT repo_new %s %s on %s", repo, host_key, source_key)
        return sent
    except Exception:
        logger.exception("repo_new notification failed repo=%s host=%s", repo, host_key)
        return False
