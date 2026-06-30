"""Miner API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Emission, Event, Miner, MinerStatus, Ranking, Stake
from app.db.session import get_db
from app.schemas.miner import (
    EmissionPoint,
    MinerListResponse,
    MinerResponse,
    MinerTimelineEvent,
    MinerTimelineResponse,
    RankPoint,
    StakePoint,
)

router = APIRouter(prefix="/miners", tags=["miners"])


@router.get("", response_model=MinerListResponse)
async def list_miners(
    subnet: int = Query(default=1, ge=0),
    status: MinerStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> MinerListResponse:
    query = select(Miner).where(Miner.subnet == subnet)
    count_query = select(func.count()).select_from(Miner).where(Miner.subnet == subnet)

    if status:
        query = query.where(Miner.status == status)
        count_query = count_query.where(Miner.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(Miner.rank_position.asc().nullslast(), Miner.uid.asc()).limit(limit).offset(offset)
    )
    miners = list(result.scalars().all())

    return MinerListResponse(
        miners=[MinerResponse.model_validate(m) for m in miners],
        total=total,
        subnet=subnet,
    )


@router.get("/{miner_id}", response_model=MinerResponse)
async def get_miner(miner_id: int, db: AsyncSession = Depends(get_db)) -> MinerResponse:
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    return MinerResponse.model_validate(miner)


@router.get("/uid/{subnet}/{uid}", response_model=MinerResponse)
async def get_miner_by_uid(subnet: int, uid: int, db: AsyncSession = Depends(get_db)) -> MinerResponse:
    result = await db.execute(
        select(Miner).where(Miner.subnet == subnet, Miner.uid == uid, Miner.status == MinerStatus.ACTIVE)
    )
    miner = result.scalar_one_or_none()
    if not miner:
        raise HTTPException(status_code=404, detail="Active miner not found for UID")
    return MinerResponse.model_validate(miner)


@router.get("/{miner_id}/timeline", response_model=MinerTimelineResponse)
async def get_miner_timeline(miner_id: int, db: AsyncSession = Depends(get_db)) -> MinerTimelineResponse:
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")

    events_result = await db.execute(
        select(Event).where(Event.miner_id == miner_id).order_by(Event.timestamp.asc())
    )
    events = list(events_result.scalars().all())

    timeline = [
        MinerTimelineEvent(
            event_type=e.event_type,
            timestamp=e.timestamp,
            block=e.block,
            data=e.data or {},
        )
        for e in events
    ]

    return MinerTimelineResponse(
        miner=MinerResponse.model_validate(miner),
        timeline=timeline,
    )


@router.get("/{miner_id}/emissions", response_model=list[EmissionPoint])
async def get_miner_emissions(
    miner_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
) -> list[EmissionPoint]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Emission)
        .where(Emission.miner_id == miner_id, Emission.timestamp >= since)
        .order_by(Emission.timestamp.asc())
    )
    return [
        EmissionPoint(block=e.block, emission=e.emission, incentive=e.incentive, timestamp=e.timestamp)
        for e in result.scalars().all()
    ]


@router.get("/{miner_id}/stakes", response_model=list[StakePoint])
async def get_miner_stakes(
    miner_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
) -> list[StakePoint]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Stake)
        .where(Stake.miner_id == miner_id, Stake.timestamp >= since)
        .order_by(Stake.timestamp.asc())
    )
    return [
        StakePoint(
            block=s.block,
            stake=s.stake,
            alpha_stake=s.alpha_stake,
            tao_stake=s.tao_stake,
            timestamp=s.timestamp,
        )
        for s in result.scalars().all()
    ]


@router.get("/{miner_id}/ranks", response_model=list[RankPoint])
async def get_miner_ranks(
    miner_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
) -> list[RankPoint]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(Ranking)
        .where(Ranking.miner_id == miner_id, Ranking.timestamp >= since)
        .order_by(Ranking.timestamp.asc())
    )
    return [
        RankPoint(
            block=r.block,
            rank=r.rank,
            rank_position=r.rank_position,
            trust=r.trust,
            timestamp=r.timestamp,
        )
        for r in result.scalars().all()
    ]
