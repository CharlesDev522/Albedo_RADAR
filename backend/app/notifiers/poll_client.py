"""Desktop / container notifier — polls API and shows kind-specific alerts."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

import httpx

from app.notifications.messages import KIND_LABELS, format_alert_body

logger = logging.getLogger(__name__)

API_URL = os.environ.get("MINERWATCH_API_URL", "http://localhost:8000/api/v1").rstrip("/")
POLL_SECONDS = float(os.environ.get("NOTIFIER_POLL_SECONDS", "10"))
ACK = os.environ.get("NOTIFIER_ACK", "true").lower() in ("1", "true", "yes")
KINDS = os.environ.get("NOTIFIER_KINDS", "").strip()

SEVERITY_DURATION: dict[str, str] = {
    "critical": "long",
    "high": "long",
    "medium": "short",
    "low": "short",
}


def _display_title(alert: dict[str, Any]) -> str:
    kind = alert.get("kind", "alert")
    label = KIND_LABELS.get(kind, kind)  # type: ignore[arg-type]
    title = alert.get("title", "")
    if title.startswith(f"[{kind}]"):
        return title.replace(f"[{kind}]", label, 1).strip()
    return f"{label}: {title}"


def show_alert(alert: dict[str, Any]) -> None:
    kind = alert.get("kind", "alert")
    title = _display_title(alert)
    body = format_alert_body(kind, alert.get("message", ""), alert.get("detail") or {})
    severity = alert.get("severity", "medium")
    duration = SEVERITY_DURATION.get(severity, "short")

    if sys.platform == "win32":
        try:
            from winotify import Notification, audio

            toast = Notification(
                app_id="MinerWatch",
                title=title[:64],
                msg=body[:500],
                duration=duration,
            )
            if severity in ("critical", "high"):
                toast.set_audio(audio.Default, loop=False)
            toast.show()
            return
        except ImportError:
            logger.warning("winotify not installed — console fallback")
        except Exception:
            logger.exception("winotify failed id=%s", alert.get("id"))

    logger.info("ALERT [%s] %s\n%s", kind, title, body)


async def _fetch(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resp = await client.get(path, params=params or {})
    resp.raise_for_status()
    return resp.json()


async def _ack(client: httpx.AsyncClient, notification_id: int) -> None:
    resp = await client.post(f"/notifications/{notification_id}/ack")
    resp.raise_for_status()


async def poll_once(client: httpx.AsyncClient, since_id: int) -> int:
    params: dict[str, Any] = {"since_id": since_id, "limit": 50}
    if KINDS:
        params["kinds"] = KINDS

    try:
        data = await _fetch(client, "/notifications", params)
    except Exception as exc:
        logger.warning("poll failed: %s", exc)
        return since_id

    items = data.get("items") or []
    latest = since_id
    for alert in items:
        alert_id = int(alert["id"])
        latest = max(latest, alert_id)
        show_alert(alert)
        if ACK:
            try:
                await _ack(client, alert_id)
            except Exception:
                logger.warning("ack failed id=%d", alert_id)

    if items:
        logger.info("delivered %d alert(s), latest_id=%d", len(items), latest)
    return latest


async def run() -> None:
    logger.info(
        "MinerWatch notifier — api=%s poll=%ss platform=%s",
        API_URL,
        POLL_SECONDS,
        sys.platform,
    )

    async with httpx.AsyncClient(
        base_url=API_URL,
        timeout=15.0,
        headers={"Accept": "application/json"},
    ) as client:
        since_id = 0
        try:
            bootstrap = await _fetch(client, "/notifications", {"limit": 1})
            if bootstrap.get("latest_id"):
                since_id = int(bootstrap["latest_id"])
                logger.info("bootstrap since_id=%d (skip backlog)", since_id)
        except Exception:
            logger.info("bootstrap failed — starting from id 0")

        while True:
            since_id = await poll_once(client, since_id)
            await asyncio.sleep(POLL_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("stopped")


if __name__ == "__main__":
    main()
