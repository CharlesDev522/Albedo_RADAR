"""Sync Hippius / Hugging Face hub manifests and miner on-chain repo activity."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import (
    FAMILY_QWEN36_35B,
    FAMILY_QWEN3_4B,
    infer_albedo_model_family,
    repo_from_slot_detail,
)
from app.config import Settings, get_settings
from app.db.models import (
    CommitmentHistory,
    HippiusRepoRevision,
    HippiusRepoTrack,
    MinerCommitment,
    MinerSlotStatus,
    RepoActivityEvent,
)
from app.integrations.hippius_hub_client import HippiusHubClient, HippiusHubModel
from app.integrations.model_registry import (
    ModelRegistryClient,
    RemoteRepoFile,
    RemoteRepoSnapshot,
    diff_remote_files,
    infer_repo_host,
    normalize_digest,
    remote_digests_match,
)
from app.processing.priority_miner_discovery import discover_priority_miner_repos
from app.processing.repo_watch_targets import (
    HUB_WATCH_PREFIX,
    RepoWatchTarget,
    discover_watch_targets,
    is_hub_watch_hotkey,
    parse_hub_watch_hotkey,
)

logger = logging.getLogger(__name__)

HF_DISCOVERY_QUERIES = ("albedo-qwen3.6-35b", "albedo-qwen3-4b")


class RepoTrackBuilder:
    """Poll Hippius + Hugging Face for every watched Albedo model repo."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = ModelRegistryClient(self.settings)
        self.hippius_hub = HippiusHubClient(self.settings)

    async def sync_subnet(self, session: AsyncSession, netuid: int) -> dict[str, int]:
        stats = {
            "miners_checked": 0,
            "unique_repos": 0,
            "hub_updates": 0,
            "hub_discoveries": 0,
            "on_chain_events": 0,
            "mismatches": 0,
            "errors": 0,
            "hub_watches": 0,
            "hippius_hub_indexed": 0,
        }
        await self._ingest_on_chain_history(session, netuid, stats)

        async with httpx.AsyncClient(timeout=self.settings.market_http_timeout_seconds) as http:
            hub_index = await self._fetch_hippius_hub_index(http)
            stats["hippius_hub_indexed"] = len(hub_index)

            hub_repos = self._albedo_repos_from_hub_index(hub_index)
            hf_repos = await self._discover_hub_search_repos(http)
            priority_repos = await self._discover_priority_miner_repos(http, hub_index=hub_index)
            targets = await discover_watch_targets(
                session,
                netuid,
                extra_repos=hf_repos,
                hippius_hub_repos=hub_repos,
                priority_repos=priority_repos,
            )
            stats["unique_repos"] = len({t.repo for t in targets})
            stats["hub_watches"] = sum(1 for t in targets if is_hub_watch_hotkey(t.hotkey))
            if not targets:
                await session.flush()
                return stats

            for target in targets:
                if target.preferred_host != "hippius":
                    continue
                entry = hub_index.get(target.repo)
                if entry is None:
                    continue
                try:
                    await self._apply_hub_index_entry(session, netuid, target, entry, stats)
                except Exception:
                    logger.exception("hippius hub index apply failed repo=%s", target.repo)

            snapshot_cache: dict[tuple[str, str | None, str | None], RemoteRepoSnapshot | None] = {}
            now = datetime.now(timezone.utc)

            for target in targets:
                stats["miners_checked"] += 1
                if target.preferred_host == "hippius":
                    entry = hub_index.get(target.repo)
                    if entry is not None:
                        track = await self._get_track(session, netuid, target.hotkey)
                        if (
                            track
                            and normalize_digest(track.hub_digest) == entry.digest
                            and track.last_checked_at
                            and (now - track.last_checked_at).total_seconds() < 120
                        ):
                            continue

                cache_key = (target.repo, target.chain_digest, target.preferred_host)
                try:
                    if cache_key not in snapshot_cache:
                        snapshot_cache[cache_key] = await self.registry.fetch_snapshot(
                            target.repo,
                            target.chain_digest,
                            client=http,
                            preferred_host=target.preferred_host,
                            host_only=target.preferred_host is not None,
                        )
                    snapshot = snapshot_cache[cache_key]
                    if snapshot is None:
                        await self._upsert_pending_track(session, netuid, target)
                        continue
                    await self._apply_snapshot(session, netuid, target, snapshot, stats)
                except httpx.HTTPStatusError as exc:
                    stats["errors"] += 1
                    logger.warning(
                        "registry fetch failed repo=%s hotkey=%s status=%s",
                        target.repo,
                        target.hotkey,
                        exc.response.status_code,
                    )
                    await self._upsert_pending_track(session, netuid, target)
                except Exception:
                    stats["errors"] += 1
                    logger.exception(
                        "repo track failed repo=%s hotkey=%s",
                        target.repo,
                        target.hotkey,
                    )
                    await self._upsert_pending_track(session, netuid, target)

        await session.flush()
        return stats

    async def _fetch_hippius_hub_index(
        self, client: httpx.AsyncClient
    ) -> dict[str, HippiusHubModel]:
        try:
            return await self.hippius_hub.fetch_albedo_index(client=client)
        except Exception:
            logger.exception("hippius hub index fetch failed")
            return {}

    def _albedo_repos_from_hub_index(self, hub_index: dict[str, HippiusHubModel]) -> list[str]:
        repos: list[str] = []
        for repo in hub_index:
            family = infer_albedo_model_family(repo)
            if family in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
                repos.append(repo)
        return sorted(set(repos))

    async def _discover_hub_search_repos(self, client: httpx.AsyncClient) -> list[str]:
        repos: list[str] = []
        try:
            for query in HF_DISCOVERY_QUERIES:
                found = await self.registry.huggingface.search_models(
                    query, limit=100, client=client
                )
                repos.extend(found)
        except Exception:
            logger.exception("hub search discovery failed")
        return list(dict.fromkeys(repos))

    async def _discover_priority_miner_repos(
        self,
        client: httpx.AsyncClient,
        *,
        hub_index: dict[str, HippiusHubModel] | None = None,
    ) -> list[str]:
        try:
            return await discover_priority_miner_repos(
                settings=self.settings,
                client=client,
                hub_index=hub_index,
            )
        except Exception:
            logger.exception("priority miner discovery failed")
            return []

    async def _apply_hub_index_entry(
        self,
        session: AsyncSession,
        netuid: int,
        target: RepoWatchTarget,
        entry: HippiusHubModel,
        stats: dict[str, int],
    ) -> None:
        family = target.model_family or infer_albedo_model_family(target.repo)
        chain_digest = normalize_digest(target.chain_digest)
        hub_digest = entry.digest
        now = datetime.now(timezone.utc)

        track = await self._get_track(session, netuid, target.hotkey)
        previous_digest = normalize_digest(track.hub_digest) if track else None
        digest_changed = hub_digest != previous_digest

        if track is None:
            track = HippiusRepoTrack(
                subnet=netuid,
                repo=target.repo,
                repo_host="hippius",
                uid=target.uid,
                hotkey=target.hotkey,
                coldkey=target.coldkey,
                model_family=family,
                hub_revision=entry.primary_tag,
            )
            session.add(track)

        track.repo = target.repo
        track.repo_host = "hippius"
        track.uid = target.uid
        track.hotkey = target.hotkey
        track.coldkey = target.coldkey
        track.model_family = family
        track.chain_digest = chain_digest
        track.hub_revision = entry.primary_tag
        track.hub_updated_at = entry.indexed_at
        track.file_count = entry.file_count
        track.total_bytes = entry.total_size_bytes
        track.last_checked_at = now
        track.last_updated = now

        if digest_changed:
            track.hub_digest = hub_digest
            track.last_hub_change_at = entry.indexed_at or now
            event_type = "hub_repo_added" if previous_digest is None else "hub_manifest_update"
            emitted = await self._emit_event(
                session,
                netuid,
                event_type=event_type,
                repo=target.repo,
                uid=target.uid,
                hotkey=target.hotkey if not is_hub_watch_hotkey(target.hotkey) else None,
                coldkey=target.coldkey,
                model_family=family,
                chain_digest=chain_digest,
                hub_digest=hub_digest,
                previous_digest=previous_digest,
                revision=entry.primary_tag,
                source_key=f"hub:hippius:{target.repo}:{hub_digest}",
                detected_at=entry.indexed_at,
                meta={
                    "host": "hippius",
                    "file_count": entry.file_count,
                    "total_bytes": entry.total_size_bytes,
                    "track_source": target.track_source,
                    "index_source": "hippius_hub_api",
                },
            )
            if emitted:
                if event_type == "hub_repo_added":
                    stats["hub_discoveries"] += 1
                else:
                    stats["hub_updates"] += 1

            existing = await self._latest_revision(session, netuid, target.repo, hub_digest)
            if existing is None:
                session.add(
                    HippiusRepoRevision(
                        subnet=netuid,
                        repo=target.repo,
                        revision=entry.primary_tag,
                        manifest_digest=hub_digest,
                        hub_created_at=entry.indexed_at,
                        file_count=entry.file_count,
                        total_bytes=entry.total_size_bytes,
                        files_json=[],
                        changed_files=[],
                    )
                )
        elif track.hub_digest is None:
            track.hub_digest = hub_digest
            if entry.indexed_at:
                track.last_hub_change_at = entry.indexed_at

    async def _upsert_pending_track(
        self, session: AsyncSession, netuid: int, target: RepoWatchTarget
    ) -> None:
        family = target.model_family or infer_albedo_model_family(target.repo)
        host = target.preferred_host or infer_repo_host(target.chain_digest)
        track = await self._get_track(session, netuid, target.hotkey)
        now = datetime.now(timezone.utc)
        if track is None:
            track = HippiusRepoTrack(
                subnet=netuid,
                repo=target.repo,
                repo_host=host,
                uid=target.uid,
                hotkey=target.hotkey,
                coldkey=target.coldkey,
                model_family=family,
            )
            session.add(track)
        track.repo = target.repo
        track.repo_host = host
        track.uid = target.uid
        track.coldkey = target.coldkey
        track.model_family = family
        track.chain_digest = normalize_digest(target.chain_digest)
        track.last_checked_at = now
        track.last_updated = now

    async def _apply_snapshot(
        self,
        session: AsyncSession,
        netuid: int,
        target: RepoWatchTarget,
        snapshot: RemoteRepoSnapshot,
        stats: dict[str, int],
    ) -> None:
        family = target.model_family or infer_albedo_model_family(target.repo)
        chain_digest = normalize_digest(target.chain_digest)
        hub_digest = normalize_digest(snapshot.remote_digest)
        in_sync = (
            remote_digests_match(target.chain_digest, snapshot.remote_digest)
            if chain_digest
            else None
        )

        track = await self._get_track(session, netuid, target.hotkey)
        previous_digest = normalize_digest(track.hub_digest) if track else None
        hub_digest = normalize_digest(snapshot.remote_digest)
        digest_changed = bool(hub_digest and hub_digest != previous_digest)
        now = datetime.now(timezone.utc)

        if track is None:
            track = HippiusRepoTrack(
                subnet=netuid,
                repo=target.repo,
                repo_host=snapshot.host,
                uid=target.uid,
                hotkey=target.hotkey,
                coldkey=target.coldkey,
                model_family=family,
                hub_revision=snapshot.revision,
            )
            session.add(track)

        track.repo = target.repo
        track.repo_host = snapshot.host
        track.uid = target.uid
        track.hotkey = target.hotkey
        track.coldkey = target.coldkey
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

        if digest_changed:
            prev_files = await self._files_for_digest(session, netuid, target.repo, previous_digest)
            changed_files = diff_remote_files(prev_files, snapshot.files)
            track.hub_digest = hub_digest
            track.last_hub_change_at = snapshot.created_at or now
            event_type = "hub_repo_added" if previous_digest is None else "hub_manifest_update"
            emitted = await self._emit_event(
                session,
                netuid,
                event_type=event_type,
                repo=target.repo,
                uid=target.uid,
                hotkey=target.hotkey if not is_hub_watch_hotkey(target.hotkey) else None,
                coldkey=target.coldkey,
                model_family=family,
                chain_digest=chain_digest,
                hub_digest=hub_digest,
                previous_digest=previous_digest,
                revision=snapshot.revision,
                commit_message=snapshot.commit_message,
                changed_files=changed_files,
                source_key=f"hub:{snapshot.host}:{target.repo}:{hub_digest}",
                meta={
                    "host": snapshot.host,
                    "file_count": snapshot.file_count,
                    "total_bytes": snapshot.total_bytes,
                    "track_source": target.track_source,
                    "index_source": "oci_manifest",
                },
            )
            if emitted:
                if event_type == "hub_repo_added":
                    stats["hub_discoveries"] += 1
                else:
                    stats["hub_updates"] += 1
            await self._record_revision(session, netuid, target.repo, snapshot, changed_files)
        elif track.hub_digest is None and hub_digest:
            track.hub_digest = hub_digest
            if snapshot.created_at:
                track.last_hub_change_at = snapshot.created_at

        if chain_digest and hub_digest and in_sync is False:
            mismatch_key = f"mismatch:{target.hotkey}:{chain_digest}:{hub_digest}"
            if await self._emit_event(
                session,
                netuid,
                event_type="digest_mismatch",
                repo=target.repo,
                uid=target.uid,
                hotkey=target.hotkey if not is_hub_watch_hotkey(target.hotkey) else None,
                coldkey=target.coldkey,
                model_family=family,
                chain_digest=chain_digest,
                hub_digest=hub_digest,
                revision=snapshot.revision,
                source_key=mismatch_key,
                meta={
                    "host": snapshot.host,
                    "note": "on-chain digest differs from remote registry",
                    "track_source": target.track_source,
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
        commits = (
            await session.execute(select(MinerCommitment).where(MinerCommitment.subnet == netuid))
        ).scalars().all()
        active_hotkeys = {c.hotkey for c in commits}

        slots = (
            await session.execute(select(MinerSlotStatus).where(MinerSlotStatus.subnet == netuid))
        ).scalars().all()
        for slot in slots:
            repo = repo_from_slot_detail(slot.detail, slot.commitment_type)
            if repo and infer_albedo_model_family(repo):
                active_hotkeys.add(slot.hotkey)

        result = await session.execute(
            select(HippiusRepoTrack).where(HippiusRepoTrack.subnet == netuid)
        )
        removed = 0
        for row in result.scalars().all():
            if is_hub_watch_hotkey(row.hotkey):
                continue
            if row.hotkey not in active_hotkeys:
                await session.delete(row)
                removed += 1
        if removed:
            logger.info("pruned %d stale repo track rows netuid=%d", removed, netuid)
        return removed
