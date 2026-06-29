"""Coldkey intelligence API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ColdkeyRecord, Miner, MinerStatus
from app.db.session import get_db
from app.processing.relationship_builder import RelationshipBuilder
from app.schemas.miner import ColdkeyDetailResponse, ColdkeyResponse, MinerResponse

router = APIRouter(prefix="/coldkeys", tags=["coldkeys"])
relationship_builder = RelationshipBuilder()


@router.get("/search", response_model=list[ColdkeyResponse])
async def search_coldkeys(
    q: str = Query(min_length=4, description="Coldkey prefix to search"),
    min_miners: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ColdkeyResponse]:
    query = (
        select(ColdkeyRecord)
        .where(ColdkeyRecord.coldkey.ilike(f"{q}%"), ColdkeyRecord.miner_count >= min_miners)
        .order_by(ColdkeyRecord.total_stake.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return [ColdkeyResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/clusters")
async def get_wallet_clusters(
    subnet: int = Query(default=1),
    min_miners: int = Query(default=3, ge=2),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Detect coldkeys operating multiple miners (potential operator farms)."""
    return await relationship_builder.detect_clusters(db, subnet, min_miners)


@router.get("/{coldkey}", response_model=ColdkeyDetailResponse)
async def get_coldkey(coldkey: str, db: AsyncSession = Depends(get_db)) -> ColdkeyDetailResponse:
    result = await db.execute(select(ColdkeyRecord).where(ColdkeyRecord.coldkey == coldkey))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Coldkey not found")

    miners_result = await db.execute(
        select(Miner).where(Miner.coldkey == coldkey, Miner.status == MinerStatus.ACTIVE)
    )
    miners = [MinerResponse.model_validate(m) for m in miners_result.scalars().all()]

    return ColdkeyDetailResponse(
        coldkey=record.coldkey,
        miner_count=record.miner_count,
        validator_count=record.validator_count,
        total_stake=record.total_stake,
        total_emission=record.total_emission,
        hotkeys=record.hotkeys,
        subnets=record.subnets,
        first_seen=record.first_seen,
        last_seen=record.last_seen,
        miners=miners,
    )


@router.get("/{coldkey}/graph")
async def get_coldkey_graph(coldkey: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Return relationship graph: coldkey → hotkey → UID."""
    return await relationship_builder.get_coldkey_graph(db, coldkey)
