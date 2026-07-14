"""Build live in-progress duel status from Albedo dashboard + pipeline state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.schemas.albedo_live import AlbedoLiveDuel, AlbedoLiveDuelParticipant
from app.services.albedo_analysis_service import parse_model_uri
from app.services.albedo_miner_lookup import MinerLookup

PHASE_LABELS: dict[str, str] = {
    "DISPATCHED": "Dispatched to GPU",
    "EVAL_RUNNING": "Duel running",
    "GENERATING": "Generating samples",
    "GENERATION": "Generating samples",
    "JUDGING": "Judge panel scoring",
    "SCORING": "Aggregating scores",
    "EVAL_QUEUED": "Queued for duel",
    "PRE_EVAL_QUEUED": "Pre-eval queue",
    "PRE_EVAL_RUNNING": "Pre-eval running",
    "PRE_EVAL_PASSED": "Passed pre-eval",
    "HIPPIUS_RUNNING": "Hippius validation",
    "SUBMITTED": "Submitted",
}


def _parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_seconds(started_at: str | None, now: datetime) -> float | None:
    start = _parse_dt(started_at)
    if not start:
        return None
    return round((now - start).total_seconds(), 0)


def _participant_from_model(
    model_uri: str | None,
    *,
    hotkey: str | None = None,
    uid: int | None = None,
    king_version: int | None = None,
    lookup: MinerLookup | None = None,
) -> AlbedoLiveDuelParticipant | None:
    if not model_uri and not hotkey:
        return None
    ns, name, uri = parse_model_uri(model_uri)
    repo = None
    if lookup and hotkey:
        ident = lookup.resolve(hotkey=hotkey, uid=uid)
        repo = ident.repo if ident else None
    if not repo and ns:
        repo = f"{ns}/{name}" if name else ns
    return AlbedoLiveDuelParticipant(
        uid=uid,
        hotkey=hotkey,
        repo=repo,
        model_name=name or None,
        namespace=ns or None,
        model_uri=uri or model_uri,
        king_version=king_version,
    )


def _phase_label(state: str | None) -> str:
    if not state:
        return "In progress"
    return PHASE_LABELS.get(state.upper(), state.replace("_", " ").title())


def _pipeline_counts(state: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    if not state:
        return {}
    counts = state.get("counts") or {}
    result: dict[str, dict[str, int]] = {}
    for stage, data in counts.items():
        if isinstance(data, dict):
            result[str(stage)] = {
                "running": int(data.get("running") or 0),
                "queued": int(data.get("queued") or 0),
            }
    return result


def _first_pipeline_item(state: dict[str, Any] | None, stage: str) -> dict[str, Any] | None:
    if not state:
        return None
    stages = state.get("stages") or {}
    bucket = stages.get(stage) or {}
    for key in ("running", "queued"):
        items = bucket.get(key) or []
        if items and isinstance(items[0], dict):
            return items[0]
    return None


def build_live_duel(
    dashboard: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    subnet: int = 97,
    dashboard_base_url: str,
    miner_lookup: MinerLookup | None = None,
) -> AlbedoLiveDuel:
    now = datetime.now(timezone.utc)
    updated_at = dashboard.get("updated_at") or state.get("updated_at") if state else dashboard.get("updated_at")
    pipeline_counts = _pipeline_counts(state)

    reign_members = (dashboard.get("reign") or {}).get("members") or []
    reign_king = reign_members[0] if reign_members else None
    king_participant = None
    if reign_king:
        king_participant = _participant_from_model(
            reign_king.get("model_uri"),
            hotkey=reign_king.get("hotkey"),
            uid=int(reign_king["uid"]) if reign_king.get("uid") is not None else None,
            king_version=int(reign_king["king_version"]) if reign_king.get("king_version") is not None else None,
            lookup=miner_lookup,
        )

    current = dashboard.get("current_eval")
    queue = list(dashboard.get("queue") or [])
    eval_queue_depth = len(queue) + pipeline_counts.get("eval", {}).get("queued", 0)

    if current:
        state_name = str(current.get("state") or "EVAL_RUNNING")
        sample_count = current.get("sample_count")
        generated = current.get("generated_sample_count")
        progress = None
        if sample_count and int(sample_count) > 0 and generated is not None:
            progress = round(int(generated) / int(sample_count) * 100, 1)

        challenger = _participant_from_model(
            current.get("model_uri"),
            hotkey=current.get("hotkey"),
            uid=int(current["uid"]) if current.get("uid") is not None else None,
            lookup=miner_lookup,
        )

        return AlbedoLiveDuel(
            subnet=subnet,
            is_active=True,
            status="duel",
            phase_label=_phase_label(state_name),
            eval_run_id=current.get("eval_run_id"),
            submission_id=current.get("submission_id"),
            pipeline_stage="eval",
            pipeline_detail=state_name,
            challenger=challenger,
            king=king_participant,
            progress_pct=progress,
            sample_count=int(sample_count) if sample_count is not None else None,
            generated_sample_count=int(generated) if generated is not None else None,
            started_at=current.get("started_at"),
            elapsed_seconds=_elapsed_seconds(current.get("started_at"), now),
            eval_queue_depth=eval_queue_depth,
            pipeline_counts=pipeline_counts,
            dashboard_url=f"{dashboard_base_url.rstrip('/')}/index.html",
            updated_at=updated_at,
            note="Live duel from dashboard current_eval.",
        )

    for stage in ("eval", "pre_eval", "hippius_validate"):
        item = _first_pipeline_item(state, stage)
        if item:
            state_name = str(item.get("state") or item.get("status") or f"{stage}_running")
            challenger = _participant_from_model(
                item.get("model_uri"),
                hotkey=item.get("hotkey"),
                uid=int(item["uid"]) if item.get("uid") is not None else None,
                lookup=miner_lookup,
            )
            return AlbedoLiveDuel(
                subnet=subnet,
                is_active=True,
                status="pipeline",
                phase_label=_phase_label(state_name),
                eval_run_id=item.get("eval_run_id"),
                submission_id=item.get("submission_id"),
                pipeline_stage=stage,
                pipeline_detail=state_name,
                challenger=challenger,
                king=king_participant if stage == "eval" else None,
                started_at=item.get("started_at") or item.get("updated_at"),
                elapsed_seconds=_elapsed_seconds(item.get("started_at") or item.get("updated_at"), now),
                eval_queue_depth=eval_queue_depth,
                pipeline_counts=pipeline_counts,
                dashboard_url=f"{dashboard_base_url.rstrip('/')}/index.html",
                updated_at=updated_at,
                note=f"Pipeline activity in {stage} stage.",
            )

    if queue:
        first = queue[0] if isinstance(queue[0], dict) else {}
        challenger = _participant_from_model(
            first.get("model_uri"),
            hotkey=first.get("hotkey"),
            uid=int(first["uid"]) if first.get("uid") is not None else None,
            lookup=miner_lookup,
        )
        return AlbedoLiveDuel(
            subnet=subnet,
            is_active=True,
            status="queued",
            phase_label="Waiting in eval queue",
            challenger=challenger,
            king=king_participant,
            eval_queue_depth=len(queue),
            pipeline_counts=pipeline_counts,
            dashboard_url=f"{dashboard_base_url.rstrip('/')}/index.html",
            updated_at=updated_at,
            note="Challenger queued for next duel.",
        )

    eval_running = pipeline_counts.get("eval", {}).get("running", 0)
    if eval_running > 0:
        return AlbedoLiveDuel(
            subnet=subnet,
            is_active=True,
            status="pipeline",
            phase_label="Eval stage running",
            king=king_participant,
            eval_queue_depth=eval_queue_depth,
            pipeline_counts=pipeline_counts,
            dashboard_url=f"{dashboard_base_url.rstrip('/')}/index.html",
            updated_at=updated_at,
            note="Eval workers active (awaiting dashboard current_eval sync).",
        )

    return AlbedoLiveDuel(
        subnet=subnet,
        is_active=False,
        status="idle",
        phase_label="No duel in progress",
        king=king_participant,
        eval_queue_depth=eval_queue_depth,
        pipeline_counts=pipeline_counts,
        dashboard_url=f"{dashboard_base_url.rstrip('/')}/index.html",
        updated_at=updated_at,
        note="Idle — no current_eval or pipeline running items.",
    )


async def get_live_duel(
    subnet: int = 97,
    *,
    settings: Settings | None = None,
    miner_lookup: MinerLookup | None = None,
) -> AlbedoLiveDuel:
    settings = settings or get_settings()
    base = settings.albedo_dashboard_url.rstrip("/")
    dashboard = await fetch_dashboard(settings=settings, live=True)
    state_payload: dict[str, Any] | None = None
    try:
        state_payload = await fetch_state(settings=settings, live=True)
    except Exception:
        state_payload = None
    return build_live_duel(
        dashboard,
        state=state_payload,
        subnet=subnet,
        dashboard_base_url=base,
        miner_lookup=miner_lookup,
    )
