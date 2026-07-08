"""Albedo duel and king-of-the-hill analysis from Hippius dashboard JSON."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.schemas.albedo_analysis import AlbedoAnalysisOverview
from app.schemas.albedo_eval_queue import AlbedoEvalQueueOverview
from app.schemas.albedo_live import AlbedoLiveDuel
from app.schemas.albedo_scoring_analysis import AlbedoScoringAnalysis
from app.services.albedo_analysis_service import get_albedo_analysis_overview
from app.services.albedo_eval_queue_service import get_eval_queue_overview
from app.services.albedo_live_duel_service import get_live_duel
from app.services.albedo_miner_lookup import load_historical_miner_lookup
from app.services.albedo_scoring_analysis_service import get_scoring_analysis_for_eval

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
) -> AlbedoScoringAnalysis:
    """GLM + Qwen dual-zero rubric questions from scoring-results.jsonl for one duel."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo scoring analysis is only available for SN97")
    settings = get_settings()
    try:
        return await get_scoring_analysis_for_eval(
            eval_run_id,
            subnet=subnet,
            settings=settings,
            fresh=fresh,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to analyze scoring results: {exc}",
        ) from exc
