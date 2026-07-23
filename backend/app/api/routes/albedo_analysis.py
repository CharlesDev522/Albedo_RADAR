"""Albedo duel and king-of-the-hill analysis from Hippius dashboard JSON."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.schemas.albedo_analysis import AlbedoAnalysisOverview
from app.schemas.albedo_eval_queue import AlbedoEvalQueueOverview
from app.schemas.albedo_live import AlbedoLiveDuel
from app.schemas.albedo_merge_advisor import AlbedoMergeAdvisorRecommendation, MergeAdvisorMode
from app.schemas.albedo_scoring_export import AlbedoScoringExportOverview
from app.schemas.albedo_scoring_analysis import AlbedoScoringDuelAnalysis
from app.services.albedo_analysis_service import get_albedo_analysis_overview
from app.services.albedo_eval_queue_service import get_eval_queue_overview
from app.services.albedo_live_duel_service import get_live_duel
from app.services.albedo_merge_advisor_service import get_merge_advisor_recommendation
from app.services.albedo_miner_lookup import load_historical_miner_lookup
from app.services.albedo_scoring_export_service import (
    export_scoring_results_for_eval,
    get_scoring_analysis_for_eval,
    get_scoring_export_overview,
)

router = APIRouter(prefix="/albedo", tags=["albedo"])


def _parse_king_versions(raw: str) -> list[int]:
    versions: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid king_version: {part!r}",
            ) from exc
        if value > 0:
            versions.append(value)
    if not versions:
        raise HTTPException(status_code=400, detail="At least one king_version is required")
    return versions


async def _load_miner_lookup(db: AsyncSession, subnet: int):
    return await load_historical_miner_lookup(db, subnet)


@router.get("/analysis", response_model=AlbedoAnalysisOverview)
async def albedo_analysis_overview(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AlbedoAnalysisOverview:
    """Cross-dimensional duel analytics: judges, repo/coldkey crowns, king history."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo duel analysis is only available for SN97")
    settings = get_settings()
    try:
        lookup = await _load_miner_lookup(db, subnet)
        return await get_albedo_analysis_overview(
            subnet, settings=settings, miner_lookup=lookup, db=db
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch Albedo dashboard: {exc}",
        ) from exc


@router.get("/eval-queue", response_model=AlbedoEvalQueueOverview)
async def albedo_eval_queue(
    subnet: int = Query(default=97, ge=0),
    fail_limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> AlbedoEvalQueueOverview:
    """Eval wait queue, pipeline stages, and recent DQ failures (poll-friendly)."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo eval queue is only available for SN97")
    settings = get_settings()
    try:
        lookup = await _load_miner_lookup(db, subnet)
        return await get_eval_queue_overview(
            subnet,
            settings=settings,
            miner_lookup=lookup,
            fail_limit=fail_limit,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch Albedo eval queue: {exc}",
        ) from exc


@router.get("/live-duel", response_model=AlbedoLiveDuel)
async def albedo_live_duel(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AlbedoLiveDuel:
    """Lightweight snapshot of the active duel / pipeline (poll-friendly)."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo live duel is only available for SN97")
    settings = get_settings()
    try:
        lookup = await _load_miner_lookup(db, subnet)
        return await get_live_duel(subnet, settings=settings, miner_lookup=lookup)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch Albedo live duel: {exc}",
        ) from exc


@router.get("/scoring-results", response_model=AlbedoScoringExportOverview)
async def albedo_scoring_results_overview(
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    include_line_counts: bool = Query(
        default=False,
        description="Fetch each artifact to count JSONL lines (slower)",
    ),
) -> AlbedoScoringExportOverview:
    """List finished duels that have a scoring-results.jsonl artifact."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring export is only available for SN97")
    settings = get_settings()
    try:
        return await get_scoring_export_overview(
            settings=settings,
            fresh=fresh,
            limit=limit,
            include_line_counts=include_line_counts,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to list scoring-results exports: {exc}",
        ) from exc


@router.get("/scoring-results/analysis", response_model=AlbedoScoringDuelAnalysis)
async def albedo_scoring_results_analysis(
    eval_run_id: str = Query(..., min_length=8),
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
) -> AlbedoScoringDuelAnalysis:
    """Category and requires breakdown for one duel's scoring-results.jsonl."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring analysis is only available for SN97")
    settings = get_settings()
    try:
        return await get_scoring_analysis_for_eval(
            eval_run_id,
            settings=settings,
            fresh=fresh,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to analyze scoring-results: {exc}",
        ) from exc


@router.get("/scoring-results/download")
async def albedo_scoring_results_download(
    eval_run_id: str = Query(..., min_length=8),
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
) -> Response:
    """Download raw scoring-results.jsonl for one duel."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring export is only available for SN97")
    settings = get_settings()
    try:
        payload = await export_scoring_results_for_eval(
            eval_run_id,
            settings=settings,
            fresh=fresh,
        )
        return Response(
            content=payload.content,
            media_type=payload.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{payload.filename}"',
                "X-Export-Filename": payload.filename,
            },
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download scoring-results: {exc}",
        ) from exc


@router.get("/merge-advisor/recommendation", response_model=AlbedoMergeAdvisorRecommendation)
async def albedo_merge_advisor_recommendation(
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    mode: MergeAdvisorMode = Query(
        default="multi_king",
        description="current_king = only vs current king; multi_king = reign windows + global BT",
    ),
    king_versions: str | None = Query(
        default=None,
        description="Comma-separated king versions for multi_king mode, e.g. 12,13",
    ),
    include_past_kings: bool = Query(
        default=True,
        description="Include coronated kings from history as donor candidates",
    ),
    min_duels: int = Query(default=2, ge=1, le=20),
    max_donors: int = Query(default=5, ge=1, le=10),
    consensus_only: bool = Query(
        default=False,
        description="Only count duels where judges strongly agree",
    ),
    export_all_methods: bool = Query(
        default=True,
        description="Include YAML for top alternative merge methods",
    ),
) -> AlbedoMergeAdvisorRecommendation:
    """Data-driven mergekit recipe from duel and reign history."""
    if subnet != 97:
        raise HTTPException(
            status_code=400,
            detail="Albedo merge advisor is only available for SN97",
        )
    settings = get_settings()
    versions = _parse_king_versions(king_versions) if king_versions else None
    try:
        return await get_merge_advisor_recommendation(
            subnet=subnet,
            settings=settings,
            fresh=fresh,
            mode=mode,
            king_versions=versions,
            include_past_kings=include_past_kings,
            min_duels=min_duels,
            max_donors=max_donors,
            consensus_only=consensus_only,
            export_all_methods=export_all_methods,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to build merge recommendation: {exc}",
        ) from exc


@router.get("/merge-advisor/config")
async def albedo_merge_advisor_config(
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    mode: MergeAdvisorMode = Query(default="multi_king"),
    king_versions: str | None = Query(default=None),
    include_past_kings: bool = Query(default=True),
    min_duels: int = Query(default=2, ge=1, le=20),
    max_donors: int = Query(default=5, ge=1, le=10),
    consensus_only: bool = Query(default=False),
    export_all_methods: bool = Query(default=True),
    method: str | None = Query(
        default=None,
        description="Download YAML for a specific method (e.g. ties, nuslerp). Defaults to primary.",
    ),
) -> Response:
    """Download mergekit YAML config for the current recommendation."""
    if subnet != 97:
        raise HTTPException(
            status_code=400,
            detail="Albedo merge advisor is only available for SN97",
        )
    settings = get_settings()
    versions = _parse_king_versions(king_versions) if king_versions else None
    try:
        rec = await get_merge_advisor_recommendation(
            subnet=subnet,
            settings=settings,
            fresh=fresh,
            mode=mode,
            king_versions=versions,
            include_past_kings=include_past_kings,
            min_duels=min_duels,
            max_donors=max_donors,
            consensus_only=consensus_only,
            export_all_methods=export_all_methods,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to build merge config: {exc}",
        ) from exc
    yaml_text = rec.mergekit_yaml
    method_name = rec.method.method
    if method:
        match = next((row for row in rec.method_yamls if row.method == method), None)
        if match:
            yaml_text = match.yaml
            method_name = match.method
    filename = f"albedo-sn{subnet}-merge-{method_name}.yaml"
    return Response(
        content=yaml_text.encode("utf-8"),
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Filename": filename,
        },
    )
