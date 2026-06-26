"""Build merged repo-activity views from slots, hub tracks, and optional chain commits."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import infer_albedo_model_family, repo_from_slot_detail
from app.db.models import HippiusRepoTrack, MinerCommitment, MinerSlotStatus
from app.integrations.model_registry import infer_repo_host, remote_digests_match
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


def _has_definite_remote_time(entry: RepoTrackEntry) -> bool:
    return entry.last_hub_change_at is not None or entry.hub_updated_at is not None


def _definite_remote_timestamp(entry: RepoTrackEntry) -> datetime | None:
    return entry.last_hub_change_at or entry.hub_updated_at


def _sort_tracks_latest_first(entries: list[RepoTrackEntry]) -> list[RepoTrackEntry]:
    """Definite hub remote times first, then newest within each tier."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(entry: RepoTrackEntry) -> tuple[int, float]:
        definite = _has_definite_remote_time(entry)
        ts = (
            _definite_remote_timestamp(entry)
            if definite
            else _activity_timestamp(entry)
        ) or epoch
        return (0 if definite else 1, -ts.timestamp())

    return sorted(entries, key=sort_key)


def _slot_to_entry(slot: MinerSlotStatus, repo: str, family: str) -> RepoTrackEntry:
    now = datetime.now(timezone.utc)
    return RepoTrackEntry(
        id=-(slot.id or 0) - 100_000,
        subnet=slot.subnet,
        repo=repo,
        repo_host="hippius",
        uid=slot.uid,
        hotkey=slot.hotkey,
        coldkey=slot.coldkey,
        model_family=family,
        chain_digest=None,
        hub_digest=None,
        hub_revision="main",
        hub_commit_message=None,
        hub_updated_at=None,
        file_count=None,
        total_bytes=None,
        digest_in_sync=None,
        last_checked_at=None,
        last_hub_change_at=None,
        first_tracked_at=slot.last_updated or now,
        last_updated=slot.last_updated or now,
        pending_hub_poll=True,
        track_source="slot",
    )


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


def _track_to_entry(track: HippiusRepoTrack, *, track_source: str | None = None) -> RepoTrackEntry:
    source = track_source or ("hub_watch" if is_hub_watch_hotkey(track.hotkey) else "hub_poll")
    return RepoTrackEntry(
        id=track.id,
        subnet=track.subnet,
        repo=track.repo,
        repo_host=track.repo_host or "hippius",
        uid=track.uid,
        hotkey=track.hotkey,
        coldkey=track.coldkey,
        model_family=track.model_family,
        chain_digest=track.chain_digest,
        hub_digest=track.hub_digest,
        hub_revision=track.hub_revision or "main",
        hub_commit_message=track.hub_commit_message,
        hub_updated_at=track.hub_updated_at,
        file_count=track.file_count,
        total_bytes=track.total_bytes,
        digest_in_sync=track.digest_in_sync,
        last_checked_at=track.last_checked_at,
        last_hub_change_at=track.last_hub_change_at,
        first_tracked_at=track.first_tracked_at,
        last_updated=track.last_updated,
        pending_hub_poll=track.hub_digest is None,
        track_source=source,
    )


def _with_sync(entry: RepoTrackEntry) -> RepoTrackEntry:
    if entry.chain_digest and entry.hub_digest:
        return entry.model_copy(
            update={
                "digest_in_sync": remote_digests_match(
                    entry.chain_digest, entry.hub_digest
                ),
                "pending_hub_poll": False,
            }
        )
    return entry


def _passes_filters(
    entry: RepoTrackEntry,
    *,
    family: str | None,
    in_sync: bool | None,
) -> bool:
    if family and entry.model_family != family:
        return False
    if in_sync is not None and entry.digest_in_sync != in_sync:
        return False
    return True


def build_merged_repo_tracks(
    *,
    slots: list[MinerSlotStatus],
    commits: list[MinerCommitment],
    tracks: list[HippiusRepoTrack],
    family: str | None = None,
    in_sync: bool | None = None,
) -> list[RepoTrackEntry]:
    """Hub-first merge: slot repos primary, chain commit optional overlay."""
    commit_by_hotkey = {c.hotkey: c for c in commits}
    track_by_hotkey = {t.hotkey: t for t in tracks if t.hotkey}

    merged: list[RepoTrackEntry] = []
    seen_hotkeys: set[str] = set()
    seen_repos: set[str] = set()

    def emit(entry: RepoTrackEntry) -> None:
        if _passes_filters(entry, family=family, in_sync=in_sync):
            merged.append(_with_sync(entry))

    slot_rows = sorted(
        (
            (slot, repo, infer_albedo_model_family(repo))
            for slot in slots
            if (repo := repo_from_slot_detail(slot.detail, slot.commitment_type))
            and infer_albedo_model_family(repo)
        ),
        key=lambda row: row[0].uid,
    )

    for slot, repo, model_family in slot_rows:
        commit = commit_by_hotkey.get(slot.hotkey)
        track = track_by_hotkey.get(slot.hotkey)
        source = "commitment" if commit else "slot"

        if track:
            entry = _track_to_entry(track, track_source=source).model_copy(
                update={
                    "uid": slot.uid,
                    "coldkey": slot.coldkey or (commit.coldkey if commit else track.coldkey),
                    "repo": repo,
                    "model_family": model_family,
                    "chain_digest": commit.digest if commit else track.chain_digest,
                }
            )
        elif commit:
            entry = _commitment_to_entry(commit).model_copy(
                update={"uid": slot.uid, "repo": repo, "model_family": model_family}
            )
        else:
            entry = _slot_to_entry(slot, repo, model_family)

        emit(entry)
        seen_hotkeys.add(slot.hotkey)
        seen_repos.add(repo)

    for commit in commits:
        if commit.hotkey in seen_hotkeys:
            continue
        track = track_by_hotkey.get(commit.hotkey)
        entry = (
            _track_to_entry(track, track_source="commitment").model_copy(
                update={"chain_digest": commit.digest, "uid": commit.uid}
            )
            if track
            else _commitment_to_entry(commit)
        )
        emit(entry)
        seen_hotkeys.add(commit.hotkey)
        seen_repos.add(commit.repo)

    for track in tracks:
        if is_hub_watch_hotkey(track.hotkey):
            if track.repo in seen_repos:
                continue
            emit(_track_to_entry(track, track_source="hub_watch"))
            seen_repos.add(track.repo)
            continue

        if track.hotkey in seen_hotkeys:
            continue
        emit(_track_to_entry(track, track_source="hub_poll"))
        seen_hotkeys.add(track.hotkey or "")
        seen_repos.add(track.repo)

    return _sort_tracks_latest_first(merged)


async def merged_repo_tracks(
    session: AsyncSession,
    subnet: int,
    *,
    family: str | None = None,
    in_sync: bool | None = None,
) -> list[RepoTrackEntry]:
    commits = (
        await session.execute(
            select(MinerCommitment).where(MinerCommitment.subnet == subnet)
        )
    ).scalars().all()
    slots = (
        await session.execute(select(MinerSlotStatus).where(MinerSlotStatus.subnet == subnet))
    ).scalars().all()
    tracks = (
        await session.execute(select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == subnet))
    ).scalars().all()

    return build_merged_repo_tracks(
        slots=list(slots),
        commits=list(commits),
        tracks=list(tracks),
        family=family,
        in_sync=in_sync,
    )
