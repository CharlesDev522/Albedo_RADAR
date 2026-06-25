"""Build merged repo-activity views from DB tracks and on-chain commitments."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import infer_albedo_model_family
from app.db.models import HippiusRepoTrack, MinerCommitment
from app.integrations.model_registry import infer_repo_host
from app.schemas.repo_activity import RepoTrackEntry


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
    )


async def merged_repo_tracks(
    session: AsyncSession,
    subnet: int,
    *,
    family: str | None = None,
    in_sync: bool | None = None,
) -> list[RepoTrackEntry]:
    """Always include every published miner; overlay collector track rows when present."""
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

    merged: list[RepoTrackEntry] = []
    for commit in commits:
        track = by_hotkey.get(commit.hotkey)
        if track:
            entry = RepoTrackEntry.model_validate(track).model_copy(
                update={"pending_hub_poll": track.hub_digest is None},
            )
        else:
            entry = _commitment_to_entry(commit)
        if family and entry.model_family != family:
            continue
        if in_sync is not None and entry.digest_in_sync != in_sync:
            continue
        merged.append(entry)
    return merged
