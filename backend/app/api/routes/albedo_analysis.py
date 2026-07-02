"""Albedo duel and king-of-the-hill analysis from Hippius dashboard JSON."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.subnet_commit_rules import model_versions_sql_tuple
from app.config import get_settings
from app.db.models import MinerCommitment
from app.db.session import get_db
from app.schemas.albedo_analysis import AlbedoAnalysisOverview
from app.schemas.albedo_eval_queue import AlbedoEvalQueueOverview
from app.schemas.albedo_live import AlbedoLiveDuel
from app.services.albedo_analysis_service import get_albedo_analysis_overview
from app.services.albedo_eval_queue_service import get_eval_queue_overview
from app.services.albedo_live_duel_service import get_live_duel
from app.services.albedo_miner_lookup import build_miner_lookup

router = APIRouter(prefix="/albedo", tags=["albedo"])


async def _load_miner_lookup(db: AsyncSession, subnet: int):
    rows = (
        await db.execute(
            select(MinerCommitment).where(
                MinerCommitment.subnet == subnet,
                MinerCommitment.version.in_(model_versions_sql_tuple(subnet)),
            )
        )
    ).scalars().all()
    return build_miner_lookup(list(rows))


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
        return await get_albedo_analysis_overview(subnet, settings=settings, miner_lookup=lookup)
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
