"""Event feed and subnet stats API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, EventType, Miner, MinerStatus, SubnetSnapshot
from app.db.session import get_db
from app.schemas.miner import EventFeedResponse, EventResponse, SubnetStatsResponse

router = APIRouter(tags=["events"])


@router.get("/events", response_model=EventFeedResponse)
async def list_events(
    subnet: int | None = None,
    event_type: EventType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> EventFeedResponse:
    query = select(Event)
    count_query = select(func.count()).select_from(Event)

    if subnet is not None:
        query = query.where(Event.subnet == subnet)
        count_query = count_query.where(Event.subnet == subnet)
    if event_type is not None:
        query = query.where(Event.event_type == event_type)
        count_query = count_query.where(Event.event_type == event_type)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Event.timestamp.desc()).limit(limit).offset(offset))
    events = list(result.scalars().all())

    return EventFeedResponse(
        events=[EventResponse.model_validate(e) for e in events],
        total=total,
    )


@router.get("/events/registrations", response_model=EventFeedResponse)
async def registration_feed(
    subnet: int = Query(default=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> EventFeedResponse:
    result = await db.execute(
        select(Event)
        .where(Event.subnet == subnet, Event.event_type == EventType.REGISTERED)
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    events = list(result.scalars().all())
    return EventFeedResponse(
        events=[EventResponse.model_validate(e) for e in events],
        total=len(events),
    )


@router.get("/events/deregistrations", response_model=EventFeedResponse)
async def deregistration_feed(
    subnet: int = Query(default=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> EventFeedResponse:
    result = await db.execute(
        select(Event)
        .where(Event.subnet == subnet, Event.event_type == EventType.DEREGISTERED)
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    events = list(result.scalars().all())
    return EventFeedResponse(
        events=[EventResponse.model_validate(e) for e in events],
        total=len(events),
    )


@router.get("/subnets/{subnet}/stats", response_model=SubnetStatsResponse)
async def subnet_stats(subnet: int, db: AsyncSession = Depends(get_db)) -> SubnetStatsResponse:
    miners_result = await db.execute(
        select(Miner).where(Miner.subnet == subnet, Miner.status == MinerStatus.ACTIVE)
    )
    miners = list(miners_result.scalars().all())

    snapshot_result = await db.execute(
        select(SubnetSnapshot)
        .where(SubnetSnapshot.subnet == subnet)
        .order_by(SubnetSnapshot.timestamp.desc())
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()

    return SubnetStatsResponse(
        subnet=subnet,
        block=snapshot.block if snapshot else 0,
        neuron_count=len(miners),
        active_miners=sum(1 for m in miners if not m.is_validator),
        active_validators=sum(1 for m in miners if m.is_validator),
        total_stake=sum(m.current_stake for m in miners),
        total_emission=sum(m.current_emission for m in miners),
        last_updated=snapshot.timestamp if snapshot else datetime.now(timezone.utc),
    )
