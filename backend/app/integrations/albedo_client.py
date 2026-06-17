"""Fetch Albedo SN97 status from Hippius dashboard APIs (v2 primary, v1 fallback)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.integrations.albedo_normalize import normalize_dashboard

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"fetched_at": 0.0, "normalized": None, "state": None, "raw": None}
_CACHE_TTL_SECONDS = 4.0

_DATA_ENDPOINTS = [
    "/albedo/data/dashboard.json",
    "/albedo/dashboard.json",
]

_STATE_ENDPOINTS = [
    "/albedo/data/state.json",
]


def _base_urls() -> list[str]:
    settings = get_settings()
    configured = settings.albedo_dashboard_url.rstrip("/")
    if configured.endswith("/dashboard.json"):
        root = configured[: -len("/dashboard.json")]
    elif configured.endswith("/data/dashboard.json"):
        root = configured[: -len("/data/dashboard.json")]
    else:
        root = configured.rsplit("/", 1)[0]
    hosts = [root]
    if "us-east-1.hippius.com" not in root:
        hosts.append("https://us-east-1.hippius.com")
    return list(dict.fromkeys(hosts))


async def _fetch_first_json(paths: list[str]) -> dict[str, Any] | None:
    buster = int(time.time() * 1000)
    headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
    async with httpx.AsyncClient(timeout=25.0, headers=headers) as client:
        for base in _base_urls():
            for path in paths:
                url = f"{base}{path}?t={buster}"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    if isinstance(data, dict) and data:
                        logger.debug("albedo fetch ok %s", url)
                        return data
                except Exception:
                    logger.debug("albedo fetch failed %s", url, exc_info=True)
    return None


async def fetch_albedo_dashboard(*, force: bool = False) -> dict[str, Any] | None:
    """Return normalized dashboard (v2 schema)."""
    now = time.monotonic()
    if (
        not force
        and _CACHE["normalized"] is not None
        and now - float(_CACHE["fetched_at"]) < _CACHE_TTL_SECONDS
    ):
        return _CACHE["normalized"]

    raw = await _fetch_first_json(_DATA_ENDPOINTS)
    if raw is None:
        return _CACHE["normalized"]

    if "eval_runs" in raw:
        normalized = normalize_dashboard(raw)
    else:
        normalized = _legacy_to_v2(raw)

    _CACHE["fetched_at"] = now
    _CACHE["raw"] = raw
    _CACHE["normalized"] = normalized
    return normalized


async def fetch_albedo_state(*, force: bool = False) -> dict[str, Any] | None:
    now = time.monotonic()
    if not force and _CACHE["state"] is not None and now - float(_CACHE["fetched_at"]) < _CACHE_TTL_SECONDS:
        return _CACHE["state"]
    state = await _fetch_first_json(_STATE_ENDPOINTS)
    if state is not None:
        _CACHE["state"] = state
    return state or _CACHE["state"]


def king_hotkey(dashboard: dict[str, Any] | None) -> str | None:
    if not dashboard:
        return None
    from app.integrations.albedo_normalize import current_king

    king = current_king(dashboard.get("reign") or {})
    if king and king.get("hotkey"):
        return str(king["hotkey"])
    legacy = dashboard.get("king") or {}
    hotkey = legacy.get("hotkey")
    return str(hotkey) if hotkey else None


def king_uid(dashboard: dict[str, Any] | None) -> int | None:
    if not dashboard:
        return None
    from app.integrations.albedo_normalize import current_king

    king = current_king(dashboard.get("reign") or {})
    if king and king.get("uid") is not None:
        return int(king["uid"])
    legacy = dashboard.get("king") or {}
    uid = legacy.get("uid")
    return int(uid) if uid is not None else None


def _legacy_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """Best-effort adapter for deprecated dashboard.json."""
    eval_runs: list[dict[str, Any]] = []
    fails: list[dict[str, Any]] = []
    for item in raw.get("history") or []:
        kind = item.get("type")
        if kind == "verdict":
            verdict = item.get("verdict") or {}
            eval_runs.append(
                {
                    "eval_run_id": item.get("eval_id"),
                    "hotkey": item.get("hotkey"),
                    "uid": item.get("uid"),
                    "model_uri": _legacy_model_uri(item.get("model_repo"), item.get("model_digest")),
                    "coronated": item.get("accepted") is True,
                    "challenger_won": item.get("winner") == "challenger",
                    "score_challenger": item.get("chal_mean"),
                    "score_king": item.get("king_mean"),
                    "win_margin": verdict.get("mean_delta"),
                    "finished_at": item.get("completed_at"),
                    "king_version": item.get("king_reign_number"),
                    "king": {
                        "hotkey": item.get("king_hotkey"),
                        "model_uri": _legacy_model_uri(
                            item.get("king_model_repo"), item.get("king_model_digest")
                        ),
                        "king_version": item.get("king_reign_number"),
                    },
                }
            )
        elif kind == "failure":
            fails.append(item)

    members: list[dict[str, Any]] = []
    king = raw.get("king")
    if king:
        members.append(
            {
                "king_version": king.get("reign_number"),
                "uid": king.get("uid"),
                "hotkey": king.get("hotkey"),
                "coldkey": king.get("coldkey"),
                "model_uri": _legacy_model_uri(king.get("model_repo"), king.get("model_digest")),
                "weight_bps": int(float(king.get("weight_share") or 0) * 10000) if king.get("weight_share") else None,
            }
        )
    for entry in raw.get("king_chain") or []:
        members.append(
            {
                "king_version": entry.get("reign_number"),
                "uid": entry.get("uid"),
                "hotkey": entry.get("hotkey"),
                "coldkey": entry.get("coldkey"),
                "model_uri": _legacy_model_uri(entry.get("model_repo"), entry.get("model_digest")),
                "weight_bps": int(float(entry.get("weight_share") or 0) * 10000)
                if entry.get("weight_share")
                else None,
            }
        )

    adapted = {
        "updated_at": raw.get("updated_at"),
        "chain": raw.get("chain") or {},
        "stats": {"evaluated": raw.get("stats", {}).get("accepted")},
        "reign": {"members": members},
        "current_eval": raw.get("current_eval"),
        "queue": raw.get("queue") or [],
        "eval_runs": eval_runs,
        "fails": fails,
    }
    return normalize_dashboard(adapted)


def _legacy_model_uri(repo: str | None, digest: str | None) -> str | None:
    if not repo:
        return None
    if digest:
        return f"{repo}@{digest}"
    return repo
