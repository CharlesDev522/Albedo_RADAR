"""Discover Hippius / Hugging Face repos to watch for hub activity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import (
    FAMILY_QWEN36_35B,
    FAMILY_QWEN3_4B,
    infer_albedo_model_family,
    repo_from_slot_detail,
)
from app.db.models import (
    CommitmentHistory,
    HippiusRepoRevision,
    HippiusRepoTrack,
    MinerCommitment,
    MinerSlotStatus,
)
from app.integrations.model_registry import RepoHost, infer_repo_host

HUB_WATCH_PREFIX = "hub:"

SOURCE_COMMITMENT = "commitment"
SOURCE_SLOT = "slot"
SOURCE_HISTORY = "history"
SOURCE_HUB_SEARCH = "hub_search"
SOURCE_KNOWN_TRACK = "known_track"


@dataclass(frozen=True)
class RepoWatchTarget:
    repo: str
    hotkey: str
    uid: int | None
    coldkey: str | None
    chain_digest: str | None
    model_family: str | None
    track_source: str
    preferred_host: RepoHost | None = None


def hub_watch_hotkey(repo: str, host: RepoHost | None = None) -> str:
    if host:
        return f"{HUB_WATCH_PREFIX}{host}:{repo}"
    return f"{HUB_WATCH_PREFIX}{repo}"


def is_hub_watch_hotkey(hotkey: str | None) -> bool:
    return bool(hotkey and hotkey.startswith(HUB_WATCH_PREFIX))


def parse_hub_watch_hotkey(hotkey: str | None) -> tuple[str | None, RepoHost | None]:
    if not is_hub_watch_hotkey(hotkey):
        return None, None
    rest = hotkey[len(HUB_WATCH_PREFIX) :]
    if rest.startswith("hippius:"):
        return rest[len("hippius:") :], "hippius"
    if rest.startswith("huggingface:"):
        return rest[len("huggingface:") :], "huggingface"
    return rest, None


def repo_from_hub_watch_hotkey(hotkey: str | None) -> str | None:
    repo, _host = parse_hub_watch_hotkey(hotkey)
    return repo


def _target_rank(source: str) -> int:
    return {
        SOURCE_COMMITMENT: 0,
        SOURCE_SLOT: 1,
        SOURCE_HISTORY: 2,
        SOURCE_KNOWN_TRACK: 3,
        SOURCE_HUB_SEARCH: 4,
    }.get(source, 9)


async def discover_watch_targets(
    session: AsyncSession,
    netuid: int,
    *,
    extra_repos: list[str] | None = None,
    hippius_hub_repos: list[str] | None = None,
) -> list[RepoWatchTarget]:
    """Merge on-chain, slot, history, DB, and hub-search repo targets."""
    by_key: dict[str, RepoWatchTarget] = {}

    def _add(
        repo: str,
        *,
        hotkey: str | None,
        uid: int | None,
        coldkey: str | None,
        chain_digest: str | None,
        source: str,
        preferred_host: RepoHost | None = None,
    ) -> None:
        family = infer_albedo_model_family(repo)
        if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
            return
        hk = hotkey or hub_watch_hotkey(repo)
        key = hk
        candidate = RepoWatchTarget(
            repo=repo,
            hotkey=hk,
            uid=uid,
            coldkey=coldkey,
            chain_digest=chain_digest,
            model_family=family,
            track_source=source,
            preferred_host=preferred_host or (infer_repo_host(chain_digest) if chain_digest else None),
        )
        existing = by_key.get(key)
        if existing is None or _target_rank(source) < _target_rank(existing.track_source):
            by_key[key] = candidate

    commits = (
        await session.execute(
            select(MinerCommitment).where(MinerCommitment.subnet == netuid)
        )
    ).scalars().all()
    commit_hotkeys = {c.hotkey for c in commits}
    commit_by_hotkey = {c.hotkey: c for c in commits}
    for commit in commits:
        _add(
            commit.repo,
            hotkey=commit.hotkey,
            uid=commit.uid,
            coldkey=commit.coldkey,
            chain_digest=commit.digest,
            source=SOURCE_COMMITMENT,
        )

    slots = (
        await session.execute(select(MinerSlotStatus).where(MinerSlotStatus.subnet == netuid))
    ).scalars().all()
    for slot in slots:
        repo = repo_from_slot_detail(slot.detail, slot.commitment_type)
        if not repo:
            continue
        _add(
            repo,
            hotkey=slot.hotkey,
            uid=slot.uid,
            coldkey=slot.coldkey,
            chain_digest=commit_by_hotkey[slot.hotkey].digest
            if slot.hotkey in commit_by_hotkey
            else None,
            source=SOURCE_SLOT,
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    history = (
        await session.execute(
            select(CommitmentHistory)
            .where(CommitmentHistory.subnet == netuid, CommitmentHistory.revealed_at >= cutoff)
            .order_by(CommitmentHistory.revealed_at.desc())
        )
    ).scalars().all()
    for row in history:
        _add(
            row.repo,
            hotkey=row.hotkey if row.hotkey in commit_hotkeys else None,
            uid=row.uid,
            coldkey=row.coldkey,
            chain_digest=row.digest,
            source=SOURCE_HISTORY,
        )

    tracks = (
        await session.execute(select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == netuid))
    ).scalars().all()
    for track in tracks:
        if is_hub_watch_hotkey(track.hotkey):
            _add(
                track.repo,
                hotkey=track.hotkey,
                uid=track.uid,
                coldkey=track.coldkey,
                chain_digest=track.chain_digest,
                source=SOURCE_KNOWN_TRACK,
                preferred_host=track.repo_host,  # type: ignore[arg-type]
            )
        elif track.hotkey and track.hotkey not in commit_hotkeys:
            _add(
                track.repo,
                hotkey=track.hotkey,
                uid=track.uid,
                coldkey=track.coldkey,
                chain_digest=track.chain_digest,
                source=SOURCE_KNOWN_TRACK,
                preferred_host=track.repo_host,  # type: ignore[arg-type]
            )

    revisions = (
        await session.execute(
            select(HippiusRepoRevision.repo)
            .where(HippiusRepoRevision.subnet == netuid)
            .distinct()
        )
    ).scalars().all()
    for repo in revisions:
        _add(repo, hotkey=None, uid=None, coldkey=None, chain_digest=None, source=SOURCE_KNOWN_TRACK)

    for repo in extra_repos or []:
        _add(
            repo,
            hotkey=hub_watch_hotkey(repo, "huggingface"),
            uid=None,
            coldkey=None,
            chain_digest=None,
            source=SOURCE_HUB_SEARCH,
            preferred_host="huggingface",
        )

    for repo in hippius_hub_repos or []:
        _add(
            repo,
            hotkey=hub_watch_hotkey(repo, "hippius"),
            uid=None,
            coldkey=None,
            chain_digest=None,
            source=SOURCE_HUB_SEARCH,
            preferred_host="hippius",
        )

    return list(by_key.values())
