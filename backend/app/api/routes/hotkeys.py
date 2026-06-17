"""Hotkey intelligence API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HotkeyRecord, Miner, MinerStatus
from app.db.session import get_db
from app.processing.relationship_builder import RelationshipBuilder
from app.schemas.miner import HotkeyResponse, MinerResponse

router = APIRouter(prefix="/hotkeys", tags=["hotkeys"])
relationship_builder = RelationshipBuilder()


@router.get("/search", response_model=list[HotkeyResponse])
async def search_hotkeys(
    q: str = Query(min_length=4, description="Hotkey prefix to search"),
    subnet: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[HotkeyResponse]:
    query = select(HotkeyRecord).where(HotkeyRecord.hotkey.ilike(f"{q}%"))
    if subnet is not None:
        query = query.where(HotkeyRecord.subnet == subnet)
    query = query.order_by(HotkeyRecord.last_seen.desc()).limit(limit)

    result = await db.execute(query)
    return [HotkeyResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/{hotkey}", response_model=HotkeyResponse)
async def get_hotkey(hotkey: str, subnet: int = Query(default=1), db: AsyncSession = Depends(get_db)) -> HotkeyResponse:
    result = await db.execute(
        select(HotkeyRecord).where(HotkeyRecord.hotkey == hotkey, HotkeyRecord.subnet == subnet)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Hotkey not found")
    return HotkeyResponse.model_validate(record)


@router.get("/{hotkey}/history")
async def get_hotkey_history(hotkey: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await relationship_builder.get_hotkey_history(db, hotkey)


@router.get("/{hotkey}/miners", response_model=list[MinerResponse])
async def get_hotkey_miners(hotkey: str, db: AsyncSession = Depends(get_db)) -> list[MinerResponse]:
    result = await db.execute(
        select(Miner).where(Miner.hotkey == hotkey, Miner.status == MinerStatus.ACTIVE)
    )
    return [MinerResponse.model_validate(m) for m in result.scalars().all()]
