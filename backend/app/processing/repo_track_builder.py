"""Sync Hippius / Hugging Face hub manifests and miner on-chain repo activity."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import infer_albedo_model_family
from app.config import Settings, get_settings
from app.db.models import (
    CommitmentHistory,
    HippiusRepoRevision,
    HippiusRepoTrack,
    MinerCommitment,
    RepoActivityEvent,
)
from app.integrations.model_registry import (
    ModelRegistryClient,
    RemoteRepoFile,
    RemoteRepoSnapshot,
    diff_remote_files,
    infer_repo_host,
    normalize_digest,
    remote_digests_match,
)

logger = logging.getLogger(__name__)


class RepoTrackBuilder:
    """Poll Hippius + Hugging Face for every published miner repo on the subnet."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = ModelRegistryClient(self.settings)

    async def sync_subnet(self, session: AsyncSession, netuid: int) -> dict[str, int]:
        stats = {
            "miners_checked": 0,
            "unique_repos": 0,
            "hub_updates": 0,
            "on_chain_events": 0,
            "mismatches": 0,
            "errors": 0,
        }
        await self._ingest_on_chain_history(session, netuid, stats)
        commits = await self._all_published_commits(session, netuid)
        stats["unique_repos"] = len({c.repo for c in commits})
        if not commits:
            await session.flush()
            return stats

        snapshot_cache: dict[tuple[str, str], RemoteRepoSnapshot | None] = {}

        async with httpx.AsyncClient(timeout=self.settings.market_http_timeout_seconds) as http:
            for commit in commits:
                stats["miners_checked"] += 1
                cache_key = (commit.repo, commit.digest or "")
                try:
                    if cache_key not in snapshot_cache:
                        snapshot_cache[cache_key] = await self.registry.fetch_snapshot(
                            commit.repo, commit.digest, client=http
                        )
                    snapshot = snapshot_cache[cache_key]
                    if snapshot is None:
                        await self._upsert_pending_track(session, netuid, commit)
                        continue
                    await self._apply_snapshot(session, netuid, commit, snapshot, stats)
                except httpx.HTTPStatusError as exc:
                    stats["errors"] += 1
                    logger.warning(
                        "registry fetch failed repo=%s uid=%s status=%s",
                        commit.repo,
                        commit.uid,
                        exc.response.status_code,
                    )
                    await self._upsert_pending_track(session, netuid, commit)
                except Exception:
                    stats["errors"] += 1
                    logger.exception(
                        "repo track failed repo=%s uid=%s hotkey=%s",
                        commit.repo,
                        commit.uid,
                        commit.hotkey,
                    )
                    await self._upsert_pending_track(session, netuid, commit)

        await session.flush()
        return stats

    async def _all_published_commits(
        self, session: AsyncSession, netuid: int
    ) -> list[MinerCommitment]:
        result = await session.execute(
            select(MinerCommitment)
            .where(MinerCommitment.subnet == netuid)
            .order_by(MinerCommitment.uid.asc().nullslast(), MinerCommitment.hotkey.asc())
        )
        return list(result.scalars().all())

    async def _upsert_pending_track(
        self, session: AsyncSession, netuid: int, commit: MinerCommitment
    ) -> None:
        family = infer_albedo_model_family(commit.repo)
        host = infer_repo_host(commit.digest)
        track = await self._get_track(session, netuid, commit.hotkey)
        now = datetime.now(timezone.utc)
        if track is None:
            track = HippiusRepoTrack(
                subnet=netuid,
                repo=commit.repo,
                repo_host=host,
                uid=commit.uid,
                hotkey=commit.hotkey,
                coldkey=commit.coldkey,
                model_family=family,
            )
            session.add(track)
        track.repo = commit.repo
        track.repo_host = host
        track.uid = commit.uid
        track.coldkey = commit.coldkey
        track.model_family = family
        track.chain_digest = normalize_digest(commit.digest)
        track.last_checked_at = now
        track.last_updated = now

    async def _apply_snapshot(
        self,
        session: AsyncSession,
        netuid: int,
        commit: MinerCommitment,
        snapshot: RemoteRepoSnapshot,
        stats: dict[str, int],
    ) -> None:
        family = infer_albedo_model_family(commit.repo)
        chain_digest = normalize_digest(commit.digest)
        hub_digest = normalize_digest(snapshot.remote_digest)
        in_sync = remote_digests_match(commit.digest, snapshot.remote_digest)

        track = await self._get_track(session, netuid, commit.hotkey)
        previous_digest = track.hub_digest if track else None
        hub_changed = bool(previous_digest and previous_digest != hub_digest)
        is_new_track = track is None
        now = datetime.now(timezone.utc)

        if track is None:
            track = HippiusRepoTrack(
                subnet=netuid,
                repo=commit.repo,
                repo_host=snapshot.host,
                uid=commit.uid,
                hotkey=commit.hotkey,
                coldkey=commit.coldkey,
                model_family=family,
                hub_revision=snapshot.revision,
            )
            session.add(track)

        track.repo = commit.repo
        track.repo_host = snapshot.host
        track.uid = commit.uid
        track.hotkey = commit.hotkey
        track.coldkey = commit.coldkey
        track.model_family = family
        track.chain_digest = chain_digest
        track.hub_revision = snapshot.revision
        track.hub_commit_message = snapshot.commit_message
        track.hub_updated_at = snapshot.created_at
        track.file_count = snapshot.file_count
        track.total_bytes = snapshot.total_bytes
        track.digest_in_sync = in_sync
        track.last_checked_at = now
        track.last_updated = now

        if hub_changed or (is_new_track and hub_digest):
            prev_files = await self._files_for_digest(session, netuid, commit.repo, previous_digest)
            changed_files = diff_remote_files(prev_files, snapshot.files)
            track.hub_digest = hub_digest
            track.last_hub_change_at = snapshot.created_at or now
            if hub_changed:
                emitted = await self._emit_event(
                    session,
                    netuid,
                    event_type="hub_manifest_update",
                    repo=commit.repo,
                    uid=commit.uid,
                    hotkey=commit.hotkey,
                    coldkey=commit.coldkey,
                    model_family=family,
                    chain_digest=chain_digest,
                    hub_digest=hub_digest,
                    previous_digest=previous_digest,
                    revision=snapshot.revision,
                    commit_message=snapshot.commit_message,
                    changed_files=changed_files,
                    source_key=f"hub:{snapshot.host}:{commit.repo}:{hub_digest}",
                    meta={
                        "host": snapshot.host,
                        "file_count": snapshot.file_count,
                        "total_bytes": snapshot.total_bytes,
                    },
                )
                if emitted:
                    stats["hub_updates"] += 1
            await self._record_revision(session, netuid, commit.repo, snapshot, changed_files)
        elif track.hub_digest is None and hub_digest:
            track.hub_digest = hub_digest

        if chain_digest and hub_digest and not in_sync:
            mismatch_key = f"mismatch:{commit.hotkey}:{chain_digest}:{hub_digest}"
            if await self._emit_event(
                session,
                netuid,
                event_type="digest_mismatch",
                repo=commit.repo,
                uid=commit.uid,
                hotkey=commit.hotkey,
                coldkey=commit.coldkey,
                model_family=family,
                chain_digest=chain_digest,
                hub_digest=hub_digest,
                revision=snapshot.revision,
                source_key=mismatch_key,
                meta={
                    "host": snapshot.host,
                    "note": "on-chain digest differs from remote registry",
                },
            ):
                stats["mismatches"] += 1

    async def _ingest_on_chain_history(
        self,
        session: AsyncSession,
        netuid: int,
        stats: dict[str, int],
    ) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        result = await session.execute(
            select(CommitmentHistory)
            .where(CommitmentHistory.subnet == netuid, CommitmentHistory.revealed_at >= cutoff)
            .order_by(CommitmentHistory.revealed_at.desc())
        )
        for row in result.scalars().all():
            source_key = f"onchain:{row.id}"
            existing = await session.execute(
                select(RepoActivityEvent.id).where(RepoActivityEvent.source_key == source_key)
            )
            if existing.scalar_one_or_none() is not None:
                continue
            family = infer_albedo_model_family(row.repo)
            await self._emit_event(
                session,
                netuid,
                event_type="on_chain_commit",
                repo=row.repo,
                uid=row.uid,
                hotkey=row.hotkey,
                coldkey=row.coldkey,
                model_family=family,
                chain_digest=normalize_digest(row.digest),
                commit_block=row.commit_block,
                source_key=source_key,
                detected_at=row.revealed_at,
                meta={"payload_hash": row.payload_hash, "host": infer_repo_host(row.digest)},
            )
            stats["on_chain_events"] += 1

    async def _get_track(
        self, session: AsyncSession, netuid: int, hotkey: str
    ) -> HippiusRepoTrack | None:
        result = await session.execute(
            select(HippiusRepoTrack).where(
                HippiusRepoTrack.subnet == netuid,
                HippiusRepoTrack.hotkey == hotkey,
            )
        )
        return result.scalar_one_or_none()

    async def _latest_revision(
        self, session: AsyncSession, netuid: int, repo: str, manifest_digest: str
    ) -> HippiusRepoRevision | None:
        result = await session.execute(
            select(HippiusRepoRevision).where(
                HippiusRepoRevision.subnet == netuid,
                HippiusRepoRevision.repo == repo,
                HippiusRepoRevision.manifest_digest == manifest_digest,
            )
        )
        return result.scalar_one_or_none()

    async def _files_for_digest(
        self,
        session: AsyncSession,
        netuid: int,
        repo: str,
        manifest_digest: str | None,
    ) -> tuple[RemoteRepoFile, ...] | None:
        if not manifest_digest:
            return None
        rev = await self._latest_revision(session, netuid, repo, manifest_digest)
        if not rev or not rev.files_json:
            return None
        return tuple(
            RemoteRepoFile(
                name=str(f["name"]),
                digest=str(f.get("digest", "")),
                size=int(f.get("size", 0)),
            )
            for f in rev.files_json
        )

    async def _record_revision(
        self,
        session: AsyncSession,
        netuid: int,
        repo: str,
        snapshot: RemoteRepoSnapshot,
        changed_files: list[dict],
    ) -> None:
        digest = normalize_digest(snapshot.remote_digest) or snapshot.remote_digest
        existing = await self._latest_revision(session, netuid, repo, digest)
        if existing:
            return
        files_json = [{"name": f.name, "digest": f.digest, "size": f.size} for f in snapshot.files]
        session.add(
            HippiusRepoRevision(
                subnet=netuid,
                repo=repo,
                revision=snapshot.revision,
                manifest_digest=digest,
                commit_message=snapshot.commit_message,
                hub_created_at=snapshot.created_at,
                file_count=snapshot.file_count,
                total_bytes=snapshot.total_bytes,
                files_json=files_json,
                changed_files=changed_files,
            )
        )

    async def _emit_event(
        self,
        session: AsyncSession,
        netuid: int,
        *,
        event_type: str,
        repo: str,
        source_key: str,
        uid: int | None = None,
        hotkey: str | None = None,
        coldkey: str | None = None,
        model_family: str | None = None,
        chain_digest: str | None = None,
        hub_digest: str | None = None,
        previous_digest: str | None = None,
        revision: str | None = None,
        commit_block: int | None = None,
        commit_message: str | None = None,
        changed_files: list[dict] | None = None,
        detected_at: datetime | None = None,
        meta: dict | None = None,
    ) -> bool:
        existing = await session.execute(
            select(RepoActivityEvent.id).where(RepoActivityEvent.source_key == source_key)
        )
        if existing.scalar_one_or_none() is not None:
            return False
        session.add(
            RepoActivityEvent(
                subnet=netuid,
                event_type=event_type,
                repo=repo,
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                model_family=model_family,
                chain_digest=chain_digest,
                hub_digest=hub_digest,
                previous_digest=previous_digest,
                revision=revision,
                commit_block=commit_block,
                commit_message=commit_message,
                changed_files=changed_files or [],
                source_key=source_key,
                detected_at=detected_at or datetime.now(timezone.utc),
                meta=meta or {},
            )
        )
        return True

    async def prune_stale_tracks(self, session: AsyncSession, netuid: int) -> int:
        commits = await self._all_published_commits(session, netuid)
        active_hotkeys = {c.hotkey for c in commits}
        result = await session.execute(
            select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == netuid)
        )
        removed = 0
        for row in result.scalars().all():
            if row.hotkey not in active_hotkeys:
                await session.delete(row)
                removed += 1
        if removed:
            logger.info("pruned %d stale repo track rows netuid=%d", removed, netuid)
        return removed
