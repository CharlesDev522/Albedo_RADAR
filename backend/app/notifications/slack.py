"""Slack incoming webhook delivery."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings
from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.messages import format_alert_body

logger = logging.getLogger(__name__)


def _slack_channel(channel: str | None) -> str | None:
    if not channel:
        return None
    c = channel.strip()
    if c.startswith("#") or c.startswith("C"):
        return c
    return f"#{c}"


async def send_slack_alert(
    *,
    settings: Settings,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    webhook = (settings.slack_webhook_url or "").strip()
    if not webhook:
        return False

    emoji = SLACK_EMOJI.get(kind, ":bell:")
    header = f"{emoji} {title}"
    body = format_alert_body(kind, message, detail)
    if subnet is not None:
        body = f"{body}\n*Subnet:* SN{subnet}"

    payload: dict[str, Any] = {
        "text": f"{header}\n{message}",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body[:3000]},
            },
        ],
    }
    channel = _slack_channel(settings.slack_channel)
    if channel:
        payload["channel"] = channel
    if settings.slack_app_name:
        payload["username"] = settings.slack_app_name

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=settings.market_http_timeout_seconds)
    try:
        resp = await http.post(webhook, json=payload)
        if resp.status_code >= 400:
            logger.error(
                "slack webhook HTTP %s kind=%s body=%s",
                resp.status_code,
                kind,
                resp.text[:500],
            )
            return False
        return True
    except Exception:
        logger.exception("slack webhook failed kind=%s", kind)
        return False
    finally:
        if owns_client:
            await http.aclose()
