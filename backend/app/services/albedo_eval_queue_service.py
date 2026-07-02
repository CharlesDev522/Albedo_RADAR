"""Eval wait queue, pipeline stages, and DQ failures from Hippius dashboard + state."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.schemas.albedo_eval_queue import (
    AlbedoEvalFail,
    AlbedoEvalParticipant,
    AlbedoEvalQueueOverview,
    AlbedoPipelineBucket,
)
from app.services.albedo_analysis_service import _current_eval, parse_model_uri
from app.services.albedo_miner_lookup import MinerLookup

STAGE_ORDER = ("hippius_validate", "pre_eval", "eval")

STAGE_LABELS: dict[str, str] = {
    "hippius_validate": "Hippius validate",
    "pre_eval": "Pre-eval",
    "eval": "Eval",
}


def _resolve_repo(
    raw: dict[str, Any],
    *,
    lookup: MinerLookup | None,
) -> tuple[str | None, str | None, str | None, int | None]:
    model_uri = raw.get("model_uri")
    hotkey = raw.get("hotkey")
    uid = raw.get("uid")
    uid_i = int(uid) if uid is not None else None
    ns, name, uri = parse_model_uri(model_uri if isinstance(model_uri, str) else None)
    repo = None
    commit_block = None
    if lookup and hotkey:
        ident = lookup.resolve(hotkey=str(hotkey), uid=uid_i, model_uri=model_uri if isinstance(model_uri, str) else None)
        if ident:
            repo = ident.repo
            commit_block = ident.commit_block
    if not repo and ns:
        repo = f"{ns}/{name}" if name else ns
    return repo, ns or None, name or None, commit_block


def _participant_from_raw(
    raw: dict[str, Any],
    *,
    lookup: MinerLookup | None,
    position: int | None = None,
) -> AlbedoEvalParticipant:
    repo, ns, name, commit_block = _resolve_repo(raw, lookup=lookup)
    model_uri = raw.get("model_uri")
    return AlbedoEvalParticipant(
        position=position,
        uid=int(raw["uid"]) if raw.get("uid") is not None else None,
        hotkey=raw.get("hotkey"),
        repo=repo,
        model_uri=str(model_uri) if model_uri else None,
        model_name=name,
        namespace=ns,
        state=raw.get("state") or raw.get("status"),
        submission_id=raw.get("submission_id"),
        eval_run_id=raw.get("eval_run_id"),
        started_at=raw.get("started_at"),
        updated_at=raw.get("updated_at"),
        commit_block=commit_block,
    )


def _parse_queue(
    dashboard: dict[str, Any],
    *,
    lookup: MinerLookup | None,
) -> list[AlbedoEvalParticipant]:
    items: list[AlbedoEvalParticipant] = []
    for idx, raw in enumerate(dashboard.get("queue") or []):
        if not isinstance(raw, dict):
            continue
        items.append(_participant_from_raw(raw, lookup=lookup, position=idx + 1))
    return items


def _parse_pipeline_buckets(
    state: dict[str, Any] | None,
    *,
    lookup: MinerLookup | None,
) -> list[AlbedoPipelineBucket]:
    if not state:
        return []
    stages = state.get("stages") or {}
    counts = state.get("counts") or {}
    buckets: list[AlbedoPipelineBucket] = []
    for stage in STAGE_ORDER:
        bucket = stages.get(stage) or {}
        count_row = counts.get(stage) or {}
        running_raw = [r for r in (bucket.get("running") or []) if isinstance(r, dict)]
        queued_raw = [r for r in (bucket.get("queued") or []) if isinstance(r, dict)]
        buckets.append(
            AlbedoPipelineBucket(
                stage=stage,
                label=STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                running_count=int(count_row.get("running") or len(running_raw)),
                queued_count=int(count_row.get("queued") or len(queued_raw)),
                running=[
                    _participant_from_raw(r, lookup=lookup) for r in running_raw
                ],
                queued=[
                    _participant_from_raw(r, lookup=lookup, position=i + 1)
                    for i, r in enumerate(queued_raw)
                ],
            )
        )
    return buckets


def _parse_fails(
    dashboard: dict[str, Any],
    *,
    lookup: MinerLookup | None,
    limit: int = 100,
) -> list[AlbedoEvalFail]:
    rows: list[AlbedoEvalFail] = []
    for raw in dashboard.get("fails") or []:
        if not isinstance(raw, dict):
            continue
        repo, _, _, _ = _resolve_repo(raw, lookup=lookup)
        rows.append(
            AlbedoEvalFail(
                submission_id=raw.get("submission_id"),
                eval_run_id=raw.get("eval_run_id"),
                uid=int(raw["uid"]) if raw.get("uid") is not None else None,
                hotkey=raw.get("hotkey"),
                repo=repo,
                model_uri=raw.get("model_uri"),
                state=raw.get("state"),
                fault_class=raw.get("fault_class"),
                fault_code=raw.get("fault_code"),
                fault_message=raw.get("fault_message"),
                updated_at=raw.get("updated_at"),
            )
        )
    rows.sort(key=lambda r: r.updated_at or "", reverse=True)
    return rows[:limit]


def build_eval_queue_overview(
    dashboard: dict[str, Any],
    *,
    state: dict[str, Any] | None,
    subnet: int,
    source_url: str,
    miner_lookup: MinerLookup | None = None,
    fail_limit: int = 100,
) -> AlbedoEvalQueueOverview:
    queue = _parse_queue(dashboard, lookup=miner_lookup)
    pipeline = _parse_pipeline_buckets(state, lookup=miner_lookup)
    fails = _parse_fails(dashboard, lookup=miner_lookup, limit=fail_limit)
    fail_counts: dict[str, int] = {}
    for row in fails:
        key = row.fault_class or "UNKNOWN"
        fail_counts[key] = fail_counts.get(key, 0) + 1

    updated_at = dashboard.get("updated_at")
    if state and state.get("updated_at"):
        updated_at = state.get("updated_at")

    return AlbedoEvalQueueOverview(
        subnet=subnet,
        source_url=source_url,
        updated_at=updated_at,
        dashboard_updated_at=dashboard.get("updated_at"),
        state_updated_at=state.get("updated_at") if state else None,
        current_eval=_current_eval(dashboard.get("current_eval"), miner_lookup),
        queue=queue,
        pipeline=pipeline,
        fails=fails,
        fail_counts_by_class=fail_counts,
        queue_length=len(queue),
        fail_count=len(fails),
        note="Eval queue and pipeline from Hippius dashboard.json + state.json.",
    )


async def get_eval_queue_overview(
    subnet: int = 97,
    *,
    settings: Settings | None = None,
    miner_lookup: MinerLookup | None = None,
    fail_limit: int = 100,
) -> AlbedoEvalQueueOverview:
    settings = settings or get_settings()
    base = settings.albedo_dashboard_url.rstrip("/")
    source_url = f"{base}/data/dashboard.json"
    dashboard = await fetch_dashboard(settings=settings, live=True)
    state_payload: dict[str, Any] | None = None
    try:
        state_payload = await fetch_state(settings=settings, live=True)
    except Exception:
        state_payload = None
    return build_eval_queue_overview(
        dashboard,
        state=state_payload,
        subnet=subnet,
        source_url=source_url,
        miner_lookup=miner_lookup,
        fail_limit=fail_limit,
    )
