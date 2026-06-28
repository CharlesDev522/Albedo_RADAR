"""Priority miner namespace status for repo activity dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import HippiusRepoTrack, RepoActivityEvent
from app.processing.priority_miner_discovery import discover_priority_miner_repos
from app.schemas.repo_activity import PriorityMinerRepoStatus, PriorityMinerStatus


def _namespace_from_repo(repo: str) -> str | None:
    if "/" not in repo:
        return None
    return repo.split("/", 1)[0].lower()


async def build_priority_miner_status(
    session: AsyncSession,
    subnet: int,
    *,
    settings: Settings | None = None,
) -> list[PriorityMinerStatus]:
    settings = settings or get_settings()
    namespaces = [ns.strip().lower() for ns in (settings.priority_miner_namespaces or []) if ns.strip()]
    if not namespaces:
        return []

    discovered = await discover_priority_miner_repos(settings=settings)
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

    by_ns: dict[str, PriorityMinerStatus] = {
        ns: PriorityMinerStatus(namespace=ns, discovered_repos=0, repos=[])
        for ns in namespaces
    }

    discovered_by_ns: dict[str, set[str]] = {ns: set() for ns in namespaces}
    for repo in discovered:
        ns = _namespace_from_repo(repo)
        if ns in discovered_by_ns:
            discovered_by_ns[ns].add(repo)

    repo_hosts: dict[str, dict[str, HippiusRepoTrack]] = {}
    for track in tracks:
        ns = _namespace_from_repo(track.repo)
        if ns not in by_ns:
            continue
        repo_hosts.setdefault(track.repo, {})[track.repo_host or "hippius"] = track

    for ns in namespaces:
        by_ns[ns].discovered_repos = len(discovered_by_ns.get(ns, set()))

    all_repos = sorted({repo for ns in namespaces for repo in discovered_by_ns.get(ns, set())})
    for repo in all_repos:
        ns = _namespace_from_repo(repo)
        if ns not in by_ns:
            continue
        hosts = repo_hosts.get(repo, {})
        hippius = hosts.get("hippius")
        hf = hosts.get("huggingface")
        recent = [
            e
            for e in events
            if e.repo == repo
            and (e.event_type in ("hub_manifest_update", "on_chain_commit", "digest_mismatch"))
        ]
        last_event = recent[0] if recent else None
        by_ns[ns].repos.append(
            PriorityMinerRepoStatus(
                repo=repo,
                model_family=hippius.model_family if hippius else (hf.model_family if hf else None),
                hippius_tracked=hippius is not None,
                hippius_digest=hippius.hub_digest if hippius else None,
                hippius_updated_at=hippius.hub_updated_at or hippius.last_hub_change_at if hippius else None,
                hippius_commit_message=hippius.hub_commit_message if hippius else None,
                hippius_pending=hippius is None or hippius.hub_digest is None,
                huggingface_tracked=hf is not None,
                huggingface_digest=hf.hub_digest if hf else None,
                huggingface_updated_at=hf.hub_updated_at or hf.last_hub_change_at if hf else None,
                huggingface_commit_message=hf.hub_commit_message if hf else None,
                huggingface_pending=hf is None or hf.hub_digest is None,
                huggingface_exists=hf is not None and hf.hub_digest is not None,
                last_event_type=last_event.event_type if last_event else None,
                last_event_at=last_event.detected_at if last_event else None,
            )
        )
        if last_event and (
            by_ns[ns].last_activity_at is None or last_event.detected_at > by_ns[ns].last_activity_at
        ):
            by_ns[ns].last_activity_at = last_event.detected_at

    for ns, status in by_ns.items():
        status.hippius_tracked_count = sum(1 for r in status.repos if r.hippius_tracked and not r.hippius_pending)
        status.huggingface_tracked_count = sum(
            1 for r in status.repos if r.huggingface_tracked and r.huggingface_exists
        )
        status.updates_24h = sum(
            1
            for e in events
            if _namespace_from_repo(e.repo) == ns and e.event_type == "hub_manifest_update"
        )
        status.repos.sort(
            key=lambda r: (
                r.last_event_at or datetime.min.replace(tzinfo=timezone.utc),
                r.hippius_updated_at or r.huggingface_updated_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

    return [by_ns[ns] for ns in namespaces if by_ns[ns].repos or by_ns[ns].discovered_repos > 0]
