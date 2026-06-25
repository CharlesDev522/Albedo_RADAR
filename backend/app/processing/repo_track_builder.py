"""Sync Hippius hub manifests and miner on-chain repo activity."""

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
from app.integrations.hippius_registry import (
    HippiusManifest,
    HippiusManifestFile,
    HippiusRegistryClient,
    diff_manifest_files,
    digests_match,
    normalize_digest,
)

logger = logging.getLogger(__name__)


class RepoTrackBuilder:
    """Poll Hippius registry for every published miner repo on the subnet."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = HippiusRegistryClient(self.settings)

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

        revision = self.settings.repo_track_revision
        manifest_cache: dict[str, HippiusManifest | None] = {}

        async with httpx.AsyncClient(timeout=self.settings.market_http_timeout_seconds) as http:
            for commit in commits:
                stats["miners_checked"] += 1
                try:
                    if commit.repo not in manifest_cache:
                        manifest_cache[commit.repo] = await self.client.fetch_manifest(
                            commit.repo, revision, client=http
                        )
                    manifest = manifest_cache[commit.repo]
                    if manifest is None:
                        continue
                    await self._apply_manifest(session, netuid, commit, manifest, stats)
                except httpx.HTTPStatusError as exc:
                    stats["errors"] += 1
                    logger.warning(
                        "hippius fetch failed repo=%s uid=%s status=%s",
                        commit.repo,
                        commit.uid,
                        exc.response.status_code,
                    )
                except Exception:
                    stats["errors"] += 1
                    logger.exception(
                        "hippius track failed repo=%s uid=%s hotkey=%s",
                        commit.repo,
                        commit.uid,
                        commit.hotkey,
                    )

        await session.flush()
        return stats

    async def _all_published_commits(
        self, session: AsyncSession, netuid: int
    ) -> list[MinerCommitment]:
        """Every on-chain published commitment — one row per miner (hotkey)."""
        result = await session.execute(
            select(MinerCommitment)
            .where(MinerCommitment.subnet == netuid)
            .order_by(MinerCommitment.uid.asc().nullslast(), MinerCommitment.hotkey.asc())
        )
        return list(result.scalars().all())

    async def _apply_manifest(
        self,
        session: AsyncSession,
        netuid: int,
        commit: MinerCommitment,
        manifest: HippiusManifest,
        stats: dict[str, int],
    ) -> None:
        family = infer_albedo_model_family(commit.repo)
        chain_digest = normalize_digest(commit.digest)
        hub_digest = normalize_digest(manifest.manifest_digest)
        in_sync = digests_match(chain_digest, hub_digest)

        track = await self._get_track(session, netuid, commit.hotkey)
        previous_digest = track.hub_digest if track else None
        hub_changed = bool(previous_digest and previous_digest != hub_digest)
        is_new_track = track is None
        now = datetime.now(timezone.utc)

        if track is None:
            track = HippiusRepoTrack(
                subnet=netuid,
                repo=commit.repo,
                uid=commit.uid,
                hotkey=commit.hotkey,
                coldkey=commit.coldkey,
                model_family=family,
                hub_revision=manifest.revision,
            )
            session.add(track)

        track.repo = commit.repo
        track.uid = commit.uid
        track.hotkey = commit.hotkey
        track.coldkey = commit.coldkey
        track.model_family = family
        track.chain_digest = chain_digest
        track.hub_revision = manifest.revision
        track.hub_commit_message = manifest.commit_message
        track.hub_updated_at = manifest.created_at
        track.file_count = manifest.file_count
        track.total_bytes = manifest.total_bytes
        track.digest_in_sync = in_sync
        track.last_checked_at = now
        track.last_updated = now

        if hub_changed or (is_new_track and hub_digest):
            prev_files = await self._files_for_digest(session, netuid, commit.repo, previous_digest)
            changed_files = diff_manifest_files(prev_files, manifest.files)
            track.hub_digest = hub_digest
            track.last_hub_change_at = manifest.created_at or now
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
                    revision=manifest.revision,
                    commit_message=manifest.commit_message,
                    changed_files=changed_files,
                    source_key=f"hub:{commit.repo}:{hub_digest}",
                    meta={
                        "file_count": manifest.file_count,
                        "total_bytes": manifest.total_bytes,
                        "uid": commit.uid,
                        "hotkey": commit.hotkey,
                    },
                )
                if emitted:
                    stats["hub_updates"] += 1
            await self._record_revision(session, netuid, commit.repo, manifest, changed_files)
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
                revision=manifest.revision,
                source_key=mismatch_key,
                meta={"note": "on-chain digest differs from Hippius main manifest"},
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
                meta={"payload_hash": row.payload_hash},
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
    ) -> tuple[HippiusManifestFile, ...] | None:
        if not manifest_digest:
            return None
        rev = await self._latest_revision(session, netuid, repo, manifest_digest)
        if not rev or not rev.files_json:
            return None
        return tuple(
            HippiusManifestFile(
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
        manifest: HippiusManifest,
        changed_files: list[dict],
    ) -> None:
        existing = await self._latest_revision(session, netuid, repo, manifest.manifest_digest)
        if existing:
            return
        files_json = [{"name": f.name, "digest": f.digest, "size": f.size} for f in manifest.files]
        session.add(
            HippiusRepoRevision(
                subnet=netuid,
                repo=repo,
                revision=manifest.revision,
                manifest_digest=manifest.manifest_digest,
                commit_message=manifest.commit_message,
                hub_created_at=manifest.created_at,
                file_count=manifest.file_count,
                total_bytes=manifest.total_bytes,
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
        """Remove track rows for miners no longer in miner_commitments."""
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
