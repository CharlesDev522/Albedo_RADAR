"""Hippius repo tracking and miner activity feed."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HippiusRepoRevision, HippiusRepoTrack, RepoActivityEvent
from app.db.session import get_db
from app.schemas.repo_activity import (
    RepoActivityEventResponse,
    RepoActivityOverview,
    RepoRevisionResponse,
    RepoTrackEntry,
)

router = APIRouter(prefix="/repo-activity", tags=["repo-activity"])


@router.get("/overview", response_model=RepoActivityOverview)
async def repo_activity_overview(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> RepoActivityOverview:
    tracks = (
        await db.execute(select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == subnet))
    ).scalars().all()

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    events_24h = (
        await db.execute(
            select(RepoActivityEvent).where(
                RepoActivityEvent.subnet == subnet,
                RepoActivityEvent.detected_at >= since,
            )
        )
    ).scalars().all()

    last_poll = (
        await db.execute(
            select(func.max(HippiusRepoTrack.last_checked_at)).where(
                HippiusRepoTrack.subnet == subnet
            )
        )
    ).scalar()

    unique_repos = len({t.repo for t in tracks})

    return RepoActivityOverview(
        subnet=subnet,
        tracked_miners=len(tracks),
        unique_repos=unique_repos,
        tracked_repos=len(tracks),
        qwen36_35b_repos=sum(1 for t in tracks if t.model_family == "qwen3.6-35b"),
        qwen3_4b_repos=sum(1 for t in tracks if t.model_family == "qwen3-4b"),
        in_sync_count=sum(1 for t in tracks if t.digest_in_sync is True),
        mismatch_count=sum(1 for t in tracks if t.digest_in_sync is False),
        hub_updates_24h=sum(1 for e in events_24h if e.event_type == "hub_manifest_update"),
        on_chain_events_24h=sum(1 for e in events_24h if e.event_type == "on_chain_commit"),
        last_poll_at=last_poll,
    )


@router.get("/repos", response_model=list[RepoTrackEntry])
async def list_tracked_repos(
    subnet: int = Query(default=97, ge=0),
    family: str | None = Query(default=None, description="qwen3.6-35b | qwen3-4b"),
    in_sync: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[RepoTrackEntry]:
    q = select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == subnet)
    if family:
        q = q.where(HippiusRepoTrack.model_family == family)
    if in_sync is not None:
        q = q.where(HippiusRepoTrack.digest_in_sync == in_sync)
    q = q.order_by(HippiusRepoTrack.uid.asc().nullslast(), HippiusRepoTrack.repo.asc())
    rows = (await db.execute(q)).scalars().all()
    return [RepoTrackEntry.model_validate(r) for r in rows]


@router.get("/feed", response_model=list[RepoActivityEventResponse])
async def repo_activity_feed(
    subnet: int = Query(default=97, ge=0),
    family: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
) -> list[RepoActivityEventResponse]:
    q = select(RepoActivityEvent).where(RepoActivityEvent.subnet == subnet)
    if family:
        q = q.where(RepoActivityEvent.model_family == family)
    if event_type:
        q = q.where(RepoActivityEvent.event_type == event_type)
    q = q.order_by(RepoActivityEvent.detected_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [RepoActivityEventResponse.model_validate(r) for r in rows]


@router.get("/repos/{repo:path}/history", response_model=list[RepoRevisionResponse])
async def repo_revision_history(
    repo: str,
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[RepoRevisionResponse]:
    q = (
        select(HippiusRepoRevision)
        .where(HippiusRepoRevision.subnet == subnet, HippiusRepoRevision.repo == repo)
        .order_by(HippiusRepoRevision.detected_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    return [RepoRevisionResponse.model_validate(r) for r in rows]
