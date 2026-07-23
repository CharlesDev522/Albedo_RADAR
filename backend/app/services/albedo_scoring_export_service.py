"""Simple per-duel scoring-results.jsonl listing and download."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.albedo_scoring_results import (
    count_scoring_results_lines,
    fetch_scoring_results_text,
    scoring_results_url,
)
from app.schemas.albedo_scoring_export import AlbedoScoringExportDuel, AlbedoScoringExportOverview
from app.services.albedo_analysis_service import parse_model_uri

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class ScoringExportPayload:
    content: bytes
    filename: str
    media_type: str = "application/x-ndjson"


def _challenger_label(run: dict[str, Any]) -> str:
    uri = str(run.get("model_uri") or "")
    ns, name, _ = parse_model_uri(uri)
    if ns and name:
        return f"{ns}/{name}"
    return name or uri or "challenger"


def _king_label(run: dict[str, Any]) -> str | None:
    king = run.get("king") or {}
    uri = str(king.get("model_uri") or "")
    if not uri:
        return None
    ns, name, _ = parse_model_uri(uri)
    if ns and name:
        return f"{ns}/{name}"
    return name or uri


def _export_filename(eval_run_id: str) -> str:
    short_id = eval_run_id[:8] if len(eval_run_id) >= 8 else eval_run_id
    return f"scoring-results-{short_id}.jsonl"


def _duel_row(
    run: dict[str, Any],
    *,
    sample_line_count: int | None = None,
) -> AlbedoScoringExportDuel:
    eval_run_id = str(run.get("eval_run_id") or "")
    ns, name, _ = parse_model_uri(str(run.get("model_uri") or ""))
    repo = f"{ns}/{name}" if ns and name else (name or None)
    return AlbedoScoringExportDuel(
        eval_run_id=eval_run_id,
        finished_at=str(run.get("finished_at") or ""),
        model_uri=str(run.get("model_uri") or ""),
        repo=repo,
        challenger_label=_challenger_label(run),
        king_label=_king_label(run),
        challenger_won=bool(run.get("challenger_won")),
        coronated=bool(run.get("coronated")),
        scoring_mode=run.get("scoring_mode"),
        scored_sample_count=run.get("scored_sample_count"),
        sample_line_count=sample_line_count,
        export_filename=_export_filename(eval_run_id),
    )


def _find_eval_run(eval_runs: list[dict[str, Any]], eval_run_id: str) -> dict[str, Any] | None:
    for run in eval_runs:
        if str(run.get("eval_run_id") or "") == eval_run_id:
            return run
    return None


async def get_scoring_export_overview(
  settings: Settings | None = None,
  *,
  fresh: bool = False,
  limit: int = _DEFAULT_LIMIT,
  include_line_counts: bool = False,
) -> AlbedoScoringExportOverview:
    settings = settings or get_settings()
    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_runs = list(dashboard.get("eval_runs") or [])
    eval_runs.sort(key=lambda r: str(r.get("finished_at") or ""), reverse=True)

    duels: list[AlbedoScoringExportDuel] = []
    with_scoring = 0
    for run in eval_runs:
        if not scoring_results_url(run):
            continue
        with_scoring += 1
        sample_line_count = None
        if include_line_counts:
            url = scoring_results_url(run)
            assert url
            try:
                text = await fetch_scoring_results_text(url, settings=settings, fresh=fresh)
                sample_line_count = count_scoring_results_lines(text)
            except Exception:
                logger.warning(
                    "Failed to count scoring-results lines eval_run_id=%s",
                    run.get("eval_run_id"),
                    exc_info=True,
                )
        duels.append(_duel_row(run, sample_line_count=sample_line_count))
        if len(duels) >= limit:
            break

    return AlbedoScoringExportOverview(
        generated_at=datetime.now(timezone.utc).isoformat(),
        duels_total=len(eval_runs),
        duels_with_scoring=with_scoring,
        duels=duels,
    )


async def export_scoring_results_for_eval(
    eval_run_id: str,
    settings: Settings | None = None,
    *,
    fresh: bool = False,
) -> ScoringExportPayload:
    settings = settings or get_settings()
    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_runs = list(dashboard.get("eval_runs") or [])
    run = _find_eval_run(eval_runs, eval_run_id)
    if run is None:
        raise LookupError(f"Eval run not found: {eval_run_id}")

    url = scoring_results_url(run)
    if not url:
        raise LookupError(f"No scoring-results artifact for eval run {eval_run_id}")

    text = await fetch_scoring_results_text(url, settings=settings, fresh=fresh)
    if not text.endswith("\n") and text.strip():
        text = f"{text.rstrip()}\n"

    return ScoringExportPayload(
        content=text.encode("utf-8"),
        filename=_export_filename(eval_run_id),
    )
