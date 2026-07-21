"""GitHub repo watch status API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import GithubCommitAlert, GithubRepoWatchState
from app.db.session import get_db
from app.integrations.github_client import parse_github_watch_specs
from app.processing.github_repo_watcher import GithubRepoWatcher
from app.schemas.github_watch import (
    GithubCommitAlertResponse,
    GithubRepoWatchResponse,
    GithubWatchOverviewResponse,
)

router = APIRouter(prefix="/github", tags=["github"])


async def _github_watch_overview(
    db: AsyncSession,
    settings: Settings,
    *,
    limit: int,
) -> GithubWatchOverviewResponse:
    configured = [
        {
            "owner": t.owner,
            "repo": t.repo,
            "branch": t.branch,
            "tree_url": t.tree_url,
            "full_name": t.full_name,
        }
        for t in parse_github_watch_specs(settings.github_repo_watches)
    ]
    states = (
        await db.execute(
            select(GithubRepoWatchState).order_by(
                GithubRepoWatchState.owner,
                GithubRepoWatchState.repo,
                GithubRepoWatchState.branch,
            )
        )
    ).scalars().all()
    alerts = (
        await db.execute(
            select(GithubCommitAlert).order_by(desc(GithubCommitAlert.created_at)).limit(limit)
        )
    ).scalars().all()
    return GithubWatchOverviewResponse(
        enabled=settings.github_repo_tracking_enabled and bool(configured),
        poll_interval_seconds=settings.github_poll_interval_seconds,
        configured_targets=configured,
        watch_states=[GithubRepoWatchResponse.model_validate(s) for s in states],
        recent_alerts=[GithubCommitAlertResponse.model_validate(a) for a in alerts],
    )


@router.post("/sync")
async def sync_github_watch(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """On-demand GitHub poll — same logic as the collector background loop."""
    watcher = GithubRepoWatcher(settings)
    try:
        stats = await watcher.sync_once(db)
        await db.commit()
        return {"status": "ok", **stats}
    finally:
        await watcher.close()


@router.get("/watch", response_model=GithubWatchOverviewResponse)
async def github_watch_overview(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limit: int = Query(default=20, ge=1, le=100),
) -> GithubWatchOverviewResponse:
    return await _github_watch_overview(db, settings, limit=limit)
