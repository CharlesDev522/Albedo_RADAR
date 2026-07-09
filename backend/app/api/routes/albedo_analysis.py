"""Albedo duel and king-of-the-hill analysis from Hippius dashboard JSON."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.schemas.albedo_analysis import AlbedoAnalysisOverview
from app.schemas.albedo_eval_queue import AlbedoEvalQueueOverview
from app.schemas.albedo_live import AlbedoLiveDuel
from app.schemas.albedo_scoring_analysis import (
    AlbedoDatasetBuildSummary,
    AlbedoScoringAnalysis,
    ScoringConsensusPolarity,
)
from app.services.albedo_analysis_service import get_albedo_analysis_overview
from app.services.albedo_eval_queue_service import get_eval_queue_overview
from app.services.albedo_live_duel_service import get_live_duel
from app.services.albedo_miner_lookup import load_historical_miner_lookup
from app.services.albedo_scoring_analysis_service import (
    get_binary_dataset_export,
    get_binary_dataset_summary,
    get_consensus_export,
    get_dedup_script_export,
    get_scoring_analysis_for_eval,
)

router = APIRouter(prefix="/albedo", tags=["albedo"])


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


@router.get("/scoring-analysis", response_model=AlbedoScoringAnalysis)
async def albedo_scoring_analysis(
    eval_run_id: str = Query(..., min_length=8),
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    polarity: ScoringConsensusPolarity = Query(
        default="zero",
        description="Consensus polarity: zero (both score 0) or one (both score 1)",
    ),
) -> AlbedoScoringAnalysis:
    """GLM + Qwen dual-zero or dual-one on both challenger and king side for one duel."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring analysis is only available for SN97")
    settings = get_settings()
    try:
        return await get_scoring_analysis_for_eval(
            eval_run_id,
            subnet=subnet,
            settings=settings,
            fresh=fresh,
            polarity=polarity,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to analyze scoring results: {exc}",
        ) from exc


@router.get("/scoring-analysis/export")
async def albedo_scoring_analysis_export(
    eval_run_id: str = Query(..., min_length=8),
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    polarity: ScoringConsensusPolarity = Query(
        default="zero",
        description="Consensus polarity: zero or one",
    ),
) -> Response:
    """Download minimal dual-zero or dual-one JSONL (sample_id + questions + 4 judge reasons)."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring export is only available for SN97")
    settings = get_settings()
    try:
        payload = await get_consensus_export(
            eval_run_id,
            subnet=subnet,
            settings=settings,
            fresh=fresh,
            polarity=polarity,
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
            detail=f"Failed to export scoring results: {exc}",
        ) from exc


@router.get("/scoring-dataset/summary", response_model=AlbedoDatasetBuildSummary)
async def albedo_scoring_dataset_summary(
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    polarity: ScoringConsensusPolarity = Query(
        default="zero",
        description="Consensus polarity: zero or one",
    ),
) -> AlbedoDatasetBuildSummary:
    """Summarize combined dual-zero or dual-one JSONL across all binary rubric duels."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring dataset is only available for SN97")
    settings = get_settings()
    try:
        return await get_binary_dataset_summary(settings=settings, fresh=fresh, polarity=polarity)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to build scoring dataset summary: {exc}",
        ) from exc


@router.get("/scoring-dataset/export")
async def albedo_scoring_dataset_export(
    subnet: int = Query(default=97, ge=0),
    fresh: bool = Query(default=False),
    polarity: ScoringConsensusPolarity = Query(
        default="zero",
        description="Consensus polarity: zero or one",
    ),
) -> Response:
    """Download combined, deduplicated dual-zero or dual-one JSONL for binary rubric duels."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring dataset export is only available for SN97")
    settings = get_settings()
    try:
        payload = await get_binary_dataset_export(settings=settings, fresh=fresh, polarity=polarity)
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
            detail=f"Failed to export scoring dataset: {exc}",
        ) from exc


@router.get("/scoring-dataset/dedup-script")
async def albedo_scoring_dataset_dedup_script(
    subnet: int = Query(default=97, ge=0),
) -> Response:
    """Download the sample_id deduplication helper script."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring dataset is only available for SN97")
    try:
        payload = get_dedup_script_export()
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
