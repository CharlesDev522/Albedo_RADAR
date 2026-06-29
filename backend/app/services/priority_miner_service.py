"""Priority miner namespace status for repo activity dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import HippiusRepoTrack, RepoActivityEvent
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.hippius_hub_client import HippiusHubClient
from app.processing.priority_miner_discovery import (
    compute_challenger_stats,
    discover_priority_miner_repos,
    hippius_browse_url,
    huggingface_browse_url,
    resolve_watch_namespaces,
)


def _namespace_from_repo(repo: str) -> str | None:
    if "/" not in repo:
        return None
    return repo.split("/", 1)[0].lower()


def _repo_activity_timestamp(
    *,
    last_event_at: datetime | None,
    hippius_updated_at: datetime | None,
    huggingface_updated_at: datetime | None,
) -> float:
    best = 0.0
    for ts in (last_event_at, hippius_updated_at, huggingface_updated_at):
        if ts is not None:
            best = max(best, ts.timestamp())
    return best


async def build_priority_miner_status(
    session: AsyncSession,
    subnet: int,
    *,
    settings: Settings | None = None,
) -> list[PriorityMinerStatus]:
    from app.schemas.repo_activity import PriorityMinerRepoStatus, PriorityMinerStatus

    settings = settings or get_settings()
    try:
        dashboard = await fetch_dashboard(settings=settings)
    except Exception:
        dashboard = {}

    watch_list = resolve_watch_namespaces(settings, dashboard)
    if not watch_list:
        return []

    ns_stats, repo_stats = compute_challenger_stats(dashboard)
    hub_index = await HippiusHubClient(settings).fetch_albedo_index()
    discovered = await discover_priority_miner_repos(
        settings=settings,
        dashboard=dashboard,
        hub_index=hub_index,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    tracks = (
        await session.execute(select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == subnet))
    ).scalars().all()
    events = (
        await session.execute(
            select(RepoActivityEvent)
            .where(RepoActivityEvent.subnet == subnet, RepoActivityEvent.detected_at >= cutoff)
            .order_by(RepoActivityEvent.detected_at.desc())
        )
    ).scalars().all()

    discovered_by_ns: dict[str, set[str]] = {}
    for repo in discovered:
        ns = _namespace_from_repo(repo)
        if ns:
            discovered_by_ns.setdefault(ns, set()).add(repo)

    repo_hosts: dict[str, dict[str, HippiusRepoTrack]] = {}
    for track in tracks:
        ns = _namespace_from_repo(track.repo)
        if not ns:
            continue
        repo_hosts.setdefault(track.repo, {})[track.repo_host or "hippius"] = track

    results: list[PriorityMinerStatus] = []
    for watch in watch_list:
        ns = watch.namespace
        ns_challenger = watch.stats or ns_stats.get(ns)
        repos_for_ns = sorted(discovered_by_ns.get(ns, set()))
        top_repo_key = None
        if repos_for_ns and repo_stats:
            ranked_repos = sorted(
                ((r, repo_stats[r]) for r in repos_for_ns if r in repo_stats),
                key=lambda item: (-item[1].duels, -item[1].wins, -item[1].coronations, item[0]),
            )
            if ranked_repos:
                top_repo_key = ranked_repos[0][0]

        repo_rows: list[PriorityMinerRepoStatus] = []
        for repo in repos_for_ns:
            hosts = repo_hosts.get(repo, {})
            hippius = hosts.get("hippius")
            hf = hosts.get("huggingface")
            hub_entry = hub_index.get(repo)
            recent = [
                e
                for e in events
                if e.repo == repo
                and e.event_type in (
                    "hub_manifest_update",
                    "hub_repo_added",
                    "on_chain_commit",
                    "digest_mismatch",
                )
            ]
            last_event = recent[0] if recent else None
            rstats = repo_stats.get(repo)
            repo_rows.append(
                PriorityMinerRepoStatus(
                    repo=repo,
                    model_family=hippius.model_family if hippius else (hf.model_family if hf else None),
                    hippius_url=hippius_browse_url(repo),
                    huggingface_url=huggingface_browse_url(repo),
                    hippius_tracked=hippius is not None,
                    hippius_digest=hippius.hub_digest if hippius else (hub_entry.digest if hub_entry else None),
                    hippius_updated_at=(
                        hippius.hub_updated_at or hippius.last_hub_change_at
                        if hippius
                        else (hub_entry.indexed_at if hub_entry else None)
                    ),
                    hippius_commit_message=hippius.hub_commit_message if hippius else None,
                    hippius_pending=hippius is None or hippius.hub_digest is None,
                    huggingface_tracked=hf is not None,
                    huggingface_digest=hf.hub_digest if hf else None,
                    huggingface_updated_at=hf.hub_updated_at or hf.last_hub_change_at if hf else None,
                    huggingface_commit_message=hf.hub_commit_message if hf else None,
                    huggingface_pending=hf is None or hf.hub_digest is None,
                    huggingface_exists=hf is not None and hf.hub_digest is not None,
                    duel_count=rstats.duels if rstats else 0,
                    challenger_wins=rstats.wins if rstats else 0,
                    challenger_win_pct=rstats.win_pct if rstats else None,
                    coronations=rstats.coronations if rstats else 0,
                    is_top_repo=repo == top_repo_key,
                    last_event_type=last_event.event_type if last_event else None,
                    last_event_at=last_event.detected_at if last_event else None,
                )
            )

        repo_rows.sort(
            key=lambda r: (
                -_repo_activity_timestamp(
                    last_event_at=r.last_event_at,
                    hippius_updated_at=r.hippius_updated_at,
                    huggingface_updated_at=r.huggingface_updated_at,
                ),
                r.repo,
            ),
        )

        last_activity = max(
            (r.last_event_at for r in repo_rows if r.last_event_at),
            default=None,
        )

        status = PriorityMinerStatus(
            namespace=ns,
            watch_source=watch.source,
            challenger_rank=watch.rank,
            duel_count=ns_challenger.duels if ns_challenger else 0,
            challenger_wins=ns_challenger.wins if ns_challenger else 0,
            challenger_win_pct=ns_challenger.win_pct if ns_challenger else None,
            coronations=ns_challenger.coronations if ns_challenger else 0,
            discovered_repos=len(repos_for_ns),
            repos=repo_rows,
            last_activity_at=last_activity,
        )
        status.hippius_tracked_count = sum(
            1 for r in status.repos if r.hippius_tracked and not r.hippius_pending
        )
        status.huggingface_tracked_count = sum(
            1 for r in status.repos if r.huggingface_tracked and r.huggingface_exists
        )
        status.updates_24h = sum(
            1
            for e in events
            if _namespace_from_repo(e.repo) == ns
            and e.event_type in ("hub_manifest_update", "hub_repo_added")
        )
        results.append(status)

    results.sort(
        key=lambda s: (
            0 if s.watch_source == "pinned" else 1,
            s.challenger_rank if s.challenger_rank is not None else 999,
            -(s.duel_count or 0),
            s.namespace,
        )
    )
    return results
