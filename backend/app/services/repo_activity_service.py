"""Build merged repo-activity views from DB tracks and on-chain commitments."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import infer_albedo_model_family
from app.db.models import HippiusRepoTrack, MinerCommitment
from app.integrations.model_registry import infer_repo_host
from app.processing.repo_watch_targets import is_hub_watch_hotkey
from app.schemas.repo_activity import RepoTrackEntry


def _activity_timestamp(entry: RepoTrackEntry) -> datetime:
    return (
        entry.last_hub_change_at
        or entry.hub_updated_at
        or entry.last_checked_at
        or entry.last_updated
        or entry.first_tracked_at
    )


def _sort_tracks_latest_first(entries: list[RepoTrackEntry]) -> list[RepoTrackEntry]:
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(entries, key=lambda e: _activity_timestamp(e) or epoch, reverse=True)


def _track_source_from_entry(entry: RepoTrackEntry) -> str:
    if entry.track_source:
        return entry.track_source
    if is_hub_watch_hotkey(entry.hotkey):
        return "hub_watch"
    return "commitment"


def _commitment_to_entry(commit: MinerCommitment) -> RepoTrackEntry:
    family = infer_albedo_model_family(commit.repo)
    now = datetime.now(timezone.utc)
    return RepoTrackEntry(
        id=-(commit.id or 0),
        subnet=commit.subnet,
        repo=commit.repo,
        repo_host=infer_repo_host(commit.digest),
        uid=commit.uid,
        hotkey=commit.hotkey,
        coldkey=commit.coldkey,
        model_family=family,
        chain_digest=commit.digest,
        hub_digest=None,
        hub_revision="main",
        hub_commit_message=None,
        hub_updated_at=None,
        file_count=None,
        total_bytes=None,
        digest_in_sync=None,
        last_checked_at=None,
        last_hub_change_at=None,
        first_tracked_at=commit.first_seen or now,
        last_updated=commit.last_updated or now,
        pending_hub_poll=True,
        track_source="commitment",
    )


def _track_to_entry(track: HippiusRepoTrack) -> RepoTrackEntry:
    source = "hub_watch" if is_hub_watch_hotkey(track.hotkey) else "known_track"
    return RepoTrackEntry.model_validate(track).model_copy(
        update={
            "pending_hub_poll": track.hub_digest is None,
            "track_source": source,
        },
    )


async def merged_repo_tracks(
    session: AsyncSession,
    subnet: int,
    *,
    family: str | None = None,
    in_sync: bool | None = None,
) -> list[RepoTrackEntry]:
    """Include on-chain miners, hub watches, and overlay collector track rows."""
    commits = (
        await session.execute(
            select(MinerCommitment)
            .where(MinerCommitment.subnet == subnet)
            .order_by(MinerCommitment.uid.asc().nullslast(), MinerCommitment.hotkey.asc())
        )
    ).scalars().all()

    tracks = (
        await session.execute(select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == subnet))
    ).scalars().all()
    by_hotkey = {t.hotkey: t for t in tracks if t.hotkey}
    by_repo = {t.repo: t for t in tracks}

    merged: list[RepoTrackEntry] = []
    seen_repos: set[str] = set()

    for commit in commits:
        track = by_hotkey.get(commit.hotkey)
        if track:
            entry = _track_to_entry(track).model_copy(
                update={
                    "track_source": "commitment",
                    "uid": commit.uid,
                    "coldkey": commit.coldkey,
                    "chain_digest": commit.digest,
                },
            )
        else:
            entry = _commitment_to_entry(commit)
        if family and entry.model_family != family:
            continue
        if in_sync is not None and entry.digest_in_sync != in_sync:
            continue
        merged.append(entry)
        seen_repos.add(entry.repo)

    for track in tracks:
        if is_hub_watch_hotkey(track.hotkey) and track.repo not in seen_repos:
            entry = _track_to_entry(track)
            if family and entry.model_family != family:
                continue
            if in_sync is not None and entry.digest_in_sync != in_sync:
                continue
            merged.append(entry)
            seen_repos.add(track.repo)
        elif track.hotkey and not is_hub_watch_hotkey(track.hotkey):
            if track.repo in seen_repos:
                continue
            if any(c.hotkey == track.hotkey for c in commits):
                continue
            entry = _track_to_entry(track)
            if family and entry.model_family != family:
                continue
            if in_sync is not None and entry.digest_in_sync != in_sync:
                continue
            merged.append(entry)
            seen_repos.add(track.repo)

    return _sort_tracks_latest_first(merged)
