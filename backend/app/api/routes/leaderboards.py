"""Leaderboard API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Miner, MinerStatus
from app.db.session import get_db
from app.schemas.miner import LeaderboardEntry, LeaderboardResponse

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])


@router.get("/emission", response_model=LeaderboardResponse)
async def top_emission(
    subnet: int = Query(default=1, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    result = await db.execute(
        select(Miner)
        .where(Miner.subnet == subnet, Miner.status == MinerStatus.ACTIVE)
        .order_by(Miner.current_emission.desc())
        .limit(limit)
    )
    miners = list(result.scalars().all())

    entries = [
        LeaderboardEntry(
            rank=i + 1,
            miner_id=m.id,
            uid=m.uid,
            hotkey=m.hotkey,
            coldkey=m.coldkey,
            value=m.current_emission,
        )
        for i, m in enumerate(miners)
    ]

    return LeaderboardResponse(
        category="top_emission",
        subnet=subnet,
        entries=entries,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/stake", response_model=LeaderboardResponse)
async def top_stake(
    subnet: int = Query(default=1, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    result = await db.execute(
        select(Miner)
        .where(Miner.subnet == subnet, Miner.status == MinerStatus.ACTIVE)
        .order_by(Miner.current_stake.desc())
        .limit(limit)
    )
    miners = list(result.scalars().all())

    entries = [
        LeaderboardEntry(
            rank=i + 1,
            miner_id=m.id,
            uid=m.uid,
            hotkey=m.hotkey,
            coldkey=m.coldkey,
            value=m.current_stake,
        )
        for i, m in enumerate(miners)
    ]

    return LeaderboardResponse(
        category="top_stake",
        subnet=subnet,
        entries=entries,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/rank", response_model=LeaderboardResponse)
async def top_rank(
    subnet: int = Query(default=1, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    result = await db.execute(
        select(Miner)
        .where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
            Miner.rank_position.isnot(None),
        )
        .order_by(Miner.rank_position.asc())
        .limit(limit)
    )
    miners = list(result.scalars().all())

    entries = [
        LeaderboardEntry(
            rank=m.rank_position or (i + 1),
            miner_id=m.id,
            uid=m.uid,
            hotkey=m.hotkey,
            coldkey=m.coldkey,
            value=m.current_incentive,
        )
        for i, m in enumerate(miners)
    ]

    return LeaderboardResponse(
        category="top_rank",
        subnet=subnet,
        entries=entries,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/rising", response_model=LeaderboardResponse)
async def rising_miners(
    subnet: int = Query(default=1, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    """Miners with highest incentive scores (rising performers)."""
    result = await db.execute(
        select(Miner)
        .where(Miner.subnet == subnet, Miner.status == MinerStatus.ACTIVE, Miner.is_validator == False)  # noqa: E712
        .order_by(Miner.current_incentive.desc())
        .limit(limit)
    )
    miners = list(result.scalars().all())

    entries = [
        LeaderboardEntry(
            rank=i + 1,
            miner_id=m.id,
            uid=m.uid,
            hotkey=m.hotkey,
            coldkey=m.coldkey,
            value=m.current_incentive,
        )
        for i, m in enumerate(miners)
    ]

    return LeaderboardResponse(
        category="rising_miners",
        subnet=subnet,
        entries=entries,
        updated_at=datetime.now(timezone.utc),
    )
