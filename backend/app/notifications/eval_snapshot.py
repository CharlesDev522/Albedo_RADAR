"""Live eval/validation snapshot for notification diagnostics."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.notifications.watcher import EVAL_DQ_NOTIFY_STATES
from app.services.albedo_eval_queue_service import _parse_pipeline_buckets, parse_dashboard_fails

logger = logging.getLogger(__name__)


async def fetch_eval_notification_snapshot(
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Summarize Hippius eval pipeline for /notifications/status (read-only)."""
    settings = settings or get_settings()
    out: dict[str, Any] = {
        "dashboard_ok": False,
        "state_ok": False,
        "current_eval": False,
        "hippius_validate_queued": 0,
        "hippius_validate_running": 0,
        "eval_fail_count": 0,
        "eval_fail_notify_states": sorted(EVAL_DQ_NOTIFY_STATES),
        "errors": [],
    }
    dashboard: dict[str, Any] | None = None
    try:
        dashboard = await fetch_dashboard(settings=settings, live=True, fresh=True)
        out["dashboard_ok"] = True
        out["current_eval"] = bool(dashboard.get("current_eval"))
        fails = parse_dashboard_fails(dashboard, limit=500)
        out["eval_fail_count"] = sum(1 for f in fails if f.state in EVAL_DQ_NOTIFY_STATES)
    except Exception as exc:
        out["errors"].append(f"dashboard: {exc}")
        logger.debug("eval notification snapshot dashboard failed", exc_info=True)

    try:
        state = await fetch_state(settings=settings, live=True, fresh=True)
        out["state_ok"] = True
        validate = next(
            (b for b in _parse_pipeline_buckets(state, lookup=None) if b.stage == "hippius_validate"),
            None,
        )
        if validate:
            out["hippius_validate_queued"] = validate.queued_count
            out["hippius_validate_running"] = validate.running_count
    except Exception as exc:
        out["errors"].append(f"state: {exc}")
        logger.debug("eval notification snapshot state failed", exc_info=True)

    return out
