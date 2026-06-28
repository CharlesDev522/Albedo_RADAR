"""Hippius + Hugging Face repo tracking and miner activity feed."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HippiusRepoRevision, HippiusRepoTrack, RepoActivityEvent
from app.db.session import get_db
from app.processing.repo_track_builder import RepoTrackBuilder
from app.schemas.repo_activity import (
    PriorityMinerStatus,
    RepoActivityEventResponse,
    RepoActivityOverview,
    RepoRevisionResponse,
    RepoTrackEntry,
)
from app.services.priority_miner_service import build_priority_miner_status
from app.services.repo_activity_service import merged_repo_tracks

router = APIRouter(prefix="/repo-activity", tags=["repo-activity"])


@router.post("/sync")
async def sync_repo_activity(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """On-demand Hippius/HF poll — use when collector has not run yet."""
    builder = RepoTrackBuilder()
    stats = await builder.sync_subnet(db, subnet)
    await builder.prune_stale_tracks(db, subnet)
    await db.commit()
    return {"status": "ok", "subnet": subnet, **stats}


@router.get("/overview", response_model=RepoActivityOverview)
async def repo_activity_overview(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> RepoActivityOverview:
    merged = await merged_repo_tracks(db, subnet)

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

    unique_repos = len({t.repo for t in merged})

    return RepoActivityOverview(
        subnet=subnet,
        tracked_miners=len(merged),
        unique_repos=unique_repos,
        tracked_repos=len(merged),
        qwen36_35b_repos=sum(1 for t in merged if t.model_family == "qwen3.6-35b"),
        qwen3_4b_repos=sum(1 for t in merged if t.model_family == "qwen3-4b"),
        in_sync_count=sum(1 for t in merged if t.digest_in_sync is True),
        mismatch_count=sum(1 for t in merged if t.digest_in_sync is False),
        hub_updates_24h=sum(1 for e in events_24h if e.event_type == "hub_manifest_update"),
        on_chain_events_24h=sum(1 for e in events_24h if e.event_type == "on_chain_commit"),
        last_poll_at=last_poll,
        hippius_count=sum(1 for t in merged if t.repo_host == "hippius"),
        huggingface_count=sum(1 for t in merged if t.repo_host == "huggingface"),
        pending_hub_poll=sum(1 for t in merged if t.pending_hub_poll),
        hub_watch_count=sum(1 for t in merged if t.track_source == "hub_watch"),
        priority_miner_count=sum(1 for t in merged if t.track_source == "priority_miner"),
        slot_only_count=sum(1 for t in merged if t.track_source == "slot"),
        chain_committed_count=sum(
            1 for t in merged if t.track_source == "commitment" or t.chain_digest
        ),
    )


@router.get("/repos", response_model=list[RepoTrackEntry])
async def list_tracked_repos(
    subnet: int = Query(default=97, ge=0),
    family: str | None = Query(default=None, description="qwen3.6-35b | qwen3-4b"),
    in_sync: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[RepoTrackEntry]:
    return await merged_repo_tracks(db, subnet, family=family, in_sync=in_sync)


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


@router.get("/priority-miners", response_model=list[PriorityMinerStatus])
async def priority_miner_status(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[PriorityMinerStatus]:
    """Top miner namespaces with dual Hippius + Hugging Face repo tracking."""
    return await build_priority_miner_status(db, subnet)
