#!/usr/bin/env python3
"""
Windows 11 desktop notifier for MinerWatch alerts.

Polls GET /api/v1/notifications?since_id= and shows native toast notifications.
Run on your Windows PC (not inside Docker):

  pip install -r scripts/requirements-windows.txt
  set MINERWATCH_API_URL=http://localhost:8000/api/v1
  python scripts/windows_notifier.py

Optional env:
  NOTIFIER_POLL_SECONDS=10
  NOTIFIER_ACK=true
  NOTIFIER_KINDS=crown_won,crown_lost,commit_new
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("windows_notifier")

API_URL = os.environ.get("MINERWATCH_API_URL", "http://localhost:8000/api/v1").rstrip("/")
POLL_SECONDS = float(os.environ.get("NOTIFIER_POLL_SECONDS", "10"))
ACK = os.environ.get("NOTIFIER_ACK", "true").lower() in ("1", "true", "yes")
KINDS = os.environ.get("NOTIFIER_KINDS", "").strip()

SEVERITY_DURATION: dict[str, int] = {
    "critical": 0,  # long / persistent
    "high": 12,
    "medium": 8,
    "low": 5,
}

KIND_EMOJI: dict[str, str] = {
    "crown_won": "👑",
    "crown_lost": "💀",
    "slot_new": "🎰",
    "slot_changed": "🔄",
    "commit_new": "🔗",
    "commit_updated": "✏️",
    "repo_new": "📦",
    "repo_updated": "☁️",
    "reg_fee_low": "💸",
}


def _http_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_URL}{path}{query}"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _http_post(path: str) -> None:
    url = f"{API_URL}{path}"
    req = Request(url, method="POST", headers={"Accept": "application/json"})
    with urlopen(req, timeout=10):
        pass


def _format_body(alert: dict[str, Any]) -> str:
    lines = [alert.get("message", "")]
    detail = alert.get("detail") or {}
    for key, value in detail.items():
        if value is None or value == "":
            continue
        label = key.replace("_", " ").title()
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
            if len(text) > 120:
                text = text[:117] + "..."
            lines.append(f"{label}: {text}")
        else:
            lines.append(f"{label}: {value}")
    body = "\n".join(lines)
    return body[:500]


def _show_toast(alert: dict[str, Any]) -> None:
    kind = alert.get("kind", "alert")
    emoji = KIND_EMOJI.get(kind, "🔔")
    title = f"{emoji} {alert.get('title', kind)}"
    body = _format_body(alert)
    severity = alert.get("severity", "medium")
    duration = SEVERITY_DURATION.get(severity, 8)

    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="MinerWatch",
            title=title[:64],
            msg=body,
            duration="long" if duration == 0 else "short",
        )
        if severity in ("critical", "high"):
            toast.set_audio(audio.Default, loop=False)
        toast.show()
    except ImportError:
        logger.warning("winotify not installed — printing alert to console")
        print(f"\n=== {title} ===\n{body}\n")
    except Exception:
        logger.exception("toast failed id=%s", alert.get("id"))
        print(f"\n=== {title} ===\n{body}\n")


def poll_once(since_id: int) -> int:
    params: dict[str, Any] = {"since_id": since_id, "limit": 50}
    if KINDS:
        params["kinds"] = KINDS

    try:
        data = _http_get("/notifications", params)
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("poll failed: %s", exc)
        return since_id

    items = data.get("items") or []
    latest = since_id
    for alert in items:
        alert_id = int(alert["id"])
        latest = max(latest, alert_id)
        _show_toast(alert)
        if ACK:
            try:
                _http_post(f"/notifications/{alert_id}/ack")
            except Exception:
                logger.warning("ack failed id=%d", alert_id)

    if items:
        logger.info("showed %d alert(s), latest_id=%d", len(items), latest)
    return latest


def main() -> int:
    if sys.platform != "win32":
        logger.warning(
            "This script targets Windows 11 toasts; running on %s (console fallback).",
            sys.platform,
        )

    logger.info("MinerWatch notifier — api=%s poll=%ss", API_URL, POLL_SECONDS)
    since_id = 0
    try:
        bootstrap = _http_get("/notifications", {"limit": 1})
        if bootstrap.get("latest_id"):
            since_id = int(bootstrap["latest_id"])
            logger.info("bootstrap since_id=%d (skip backlog)", since_id)
    except Exception:
        logger.info("bootstrap failed — will replay from id 0")

    while True:
        since_id = poll_once(since_id)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.info("stopped")
        raise SystemExit(0)
