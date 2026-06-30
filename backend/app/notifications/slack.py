"""Slack incoming webhook delivery."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings
from app.notifications.kinds import SLACK_EMOJI, AlertKind

logger = logging.getLogger(__name__)


def _detail_lines(detail: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in detail.items():
        if value is None or value == "":
            continue
        label = key.replace("_", " ").title()
        if isinstance(value, (dict, list)):
            lines.append(f"*{label}:* `{value}`")
        else:
            lines.append(f"*{label}:* {value}")
    return lines


async def send_slack_alert(
    *,
    settings: Settings,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
) -> bool:
    webhook = (settings.slack_webhook_url or "").strip()
    if not webhook:
        return False

    emoji = SLACK_EMOJI.get(kind, ":bell:")
    header = f"{emoji} {title}"
    body_lines = [message]
    body_lines.extend(_detail_lines(detail))
    if subnet is not None:
        body_lines.append(f"*Subnet:* SN{subnet}")

    payload: dict[str, Any] = {
        "text": f"{header}\n{message}",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(body_lines)[:3000]},
            },
        ],
    }
    if settings.slack_channel:
        payload["channel"] = settings.slack_channel

    try:
        async with httpx.AsyncClient(timeout=settings.market_http_timeout_seconds) as client:
            resp = await client.post(webhook, json=payload)
            resp.raise_for_status()
        return True
    except Exception:
        logger.exception("slack webhook failed kind=%s", kind)
        return False
