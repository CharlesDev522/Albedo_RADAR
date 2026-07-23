"""Process v6 model commitment scans into persistent state."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.commitment_scanner import Commit
from app.chain_reader.subnet_commit_rules import (
    is_albedo_pipe_history_row,
    model_versions_for_subnet,
    model_versions_sql_tuple,
    normalize_stored_version,
)
from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import MetagraphSnapshot, SubtensorClient
from app.db.models import (
    CommitmentHistory,
    Event,
    EventType,
    Miner,
    MinerCommitment,
    MinerStatus,
)

logger = logging.getLogger(__name__)


class CommitmentStateBuilder:
    """Upserts latest model commitments and records history on changes."""

    def __init__(
        self,
        publisher: EventPublisher | None = None,
    ) -> None:
        self.publisher = publisher

    async def process_commits(
        self,
        session: AsyncSession,
        commits: list[Commit],
        snapshot: MetagraphSnapshot | None = None,
    ) -> dict[str, int]:
        stats = {"new": 0, "updated": 0, "unchanged": 0, "events": 0}

        if snapshot:
            await self._sync_miner_registry(session, snapshot)

        commit_by_hotkey = {c.hotkey: c for c in commits}

        for commit in commits:
            result = await session.execute(
                select(MinerCommitment).where(
                    MinerCommitment.subnet == commit.netuid,
                    MinerCommitment.hotkey == commit.hotkey,
                )
            )
            existing = result.scalar_one_or_none()

            miner = await self._resolve_miner(session, commit)

            if existing is None:
                row = self._build_commitment(commit, miner)
                session.add(row)
                await self._record_history(session, commit)
                await self._emit(
                    session,
                    EventType.COMMITMENT_REVEALED,
                    commit,
                    {"model_uri": commit.model_uri, "commit_block": commit.block_number},
                    stats,
                )
                stats["new"] += 1
            elif existing.payload_hash != commit.payload_hash:
                previous_hash = existing.payload_hash
                existing.uid = commit.uid
                existing.coldkey = commit.coldkey
                existing.registered_at_block = commit.registered_at_block
                self._apply_block_and_source(existing, commit)
                existing.block_hash = commit.block_hash or existing.block_hash
                existing.reveal_string = commit.reveal_string
                existing.version = self._normalize_version(
                    commit.commit_payload.get("version", existing.version),
                    commit.netuid,
                )
                existing.repo = commit.commit_payload["repo"]
                existing.digest = commit.commit_payload["digest"]
                existing.model_uri = commit.model_uri
                existing.payload_hash = commit.payload_hash
                existing.commit_payload = commit.commit_payload
                existing.miner_id = miner.id if miner else None
                existing.last_updated = datetime.now(timezone.utc)
                await self._record_history(session, commit)
                await self._emit(
                    session,
                    EventType.COMMITMENT_UPDATED,
                    commit,
                    {
                        "model_uri": commit.model_uri,
                        "commit_block": existing.commit_block,
                        "previous_hash": previous_hash,
                    },
                    stats,
                )
                stats["updated"] += 1
            else:
                existing.uid = commit.uid
                existing.coldkey = commit.coldkey
                existing.registered_at_block = commit.registered_at_block
                existing.miner_id = miner.id if miner else None
                normalized_version = self._normalize_version(existing.version, commit.netuid)
                if existing.version != normalized_version:
                    existing.version = normalized_version
                    existing.last_updated = datetime.now(timezone.utc)
                if self._refresh_block_and_source(existing, commit):
                    existing.last_updated = datetime.now(timezone.utc)
                stats["unchanged"] += 1

        if snapshot:
            for neuron in snapshot.neurons:
                if neuron.hotkey not in commit_by_hotkey:
                    result = await session.execute(
                        select(Miner).where(
                            Miner.subnet == snapshot.subnet,
                            Miner.hotkey == neuron.hotkey,
                            Miner.status == MinerStatus.ACTIVE,
                        )
                    )
                    miner = result.scalar_one_or_none()
                    if miner:
                        miner.last_seen = datetime.now(timezone.utc)

        await session.flush()
        return stats

    async def prune_absent_model_commits(
        self,
        session: AsyncSession,
        netuid: int,
        present_hotkeys: set[str],
        *,
        retain_hotkeys: set[str] | None = None,
    ) -> int:
        """Drop model-commit rows absent from a full on-chain scan (e.g. deregistered miners)."""
        keep = present_hotkeys | (retain_hotkeys or set())
        versions = model_versions_sql_tuple(netuid)
        result = await session.execute(
            select(MinerCommitment).where(
                MinerCommitment.subnet == netuid,
                MinerCommitment.version.in_(versions),
            )
        )
        removed = 0
        for row in result.scalars().all():
            if row.hotkey not in keep:
                await session.delete(row)
                removed += 1
        if removed:
            logger.info("pruned %d stale model-commit rows netuid=%d", removed, netuid)
            await session.flush()
        return removed

    async def prune_invalid_subnet_versions(self, session: AsyncSession, netuid: int) -> int:
        """Remove rows with wrong commit version for this subnet (e.g. v5/json on SN97)."""
        allowed = model_versions_for_subnet(netuid)
        result = await session.execute(
            select(MinerCommitment).where(MinerCommitment.subnet == netuid)
        )
        removed = 0
        for row in result.scalars().all():
            if row.version not in allowed:
                await session.delete(row)
                removed += 1
        if removed:
            logger.info("pruned %d invalid-version rows netuid=%d", removed, netuid)
            await session.flush()
        return removed

    async def prune_non_pipe_history(self, session: AsyncSession, netuid: int) -> int:
        """Drop commitment history rows that are not v6/v7 pipe commits."""
        result = await session.execute(
            select(CommitmentHistory).where(CommitmentHistory.subnet == netuid)
        )
        removed = 0
        for row in result.scalars().all():
            if not is_albedo_pipe_history_row(row.reveal_string, row.commit_payload):
                await session.delete(row)
                removed += 1
        if removed:
            logger.info("pruned %d non-pipe history rows netuid=%d", removed, netuid)
            await session.flush()
        return removed

    # Backwards-compatible alias
    prune_non_v6_history = prune_non_pipe_history

    # Backwards-compatible alias
    prune_absent_v6 = prune_absent_model_commits

    @staticmethod
    def _apply_block_and_source(existing: MinerCommitment, commit: Commit) -> None:
        """Active CommitmentOf is authoritative; revealed only refines same payload."""
        if not commit.block_number or commit.block_number <= 0:
            return
        if commit.commit_source == "active":
            existing.commit_block = commit.block_number
            existing.commit_source = "active"
            return
        if commit.block_number >= existing.commit_block:
            existing.commit_block = commit.block_number
        existing.commit_source = "revealed"

    @staticmethod
    def _refresh_block_and_source(existing: MinerCommitment, commit: Commit) -> bool:
        """Update block/source on unchanged payload when scan metadata advances."""
        if not commit.block_number or commit.block_number <= 0:
            return False
        if commit.commit_source == "active":
            if (
                existing.commit_source != "active"
                or commit.block_number != existing.commit_block
            ):
                existing.commit_block = commit.block_number
                existing.commit_source = "active"
                return True
            return False
        if commit.block_number > existing.commit_block:
            existing.commit_block = commit.block_number
            existing.commit_source = "revealed"
            return True
        return False

    async def _sync_miner_registry(self, session: AsyncSession, snapshot: MetagraphSnapshot) -> None:
        """Keep a lightweight miner registry for uid/coldkey/registration lookups."""
        result = await session.execute(
            select(Miner).where(
                Miner.subnet == snapshot.subnet,
                Miner.status == MinerStatus.ACTIVE,
            )
        )
        existing = {m.uid: m for m in result.scalars().all()}
        seen: set[int] = set()

        for neuron in snapshot.neurons:
            seen.add(neuron.uid)
            if neuron.uid not in existing:
                session.add(
                    Miner(
                        uid=neuron.uid,
                        hotkey=neuron.hotkey,
                        coldkey=neuron.coldkey,
                        subnet=snapshot.subnet,
                        registered_at_block=neuron.registered_at_block,
                        status=MinerStatus.ACTIVE,
                        is_validator=neuron.is_validator,
                    )
                )
            else:
                m = existing[neuron.uid]
                m.hotkey = neuron.hotkey
                m.coldkey = neuron.coldkey
                m.registered_at_block = neuron.registered_at_block
                m.last_seen = datetime.now(timezone.utc)

        for uid, miner in existing.items():
            if uid not in seen:
                miner.status = MinerStatus.DEREGISTERED

    async def _resolve_miner(self, session: AsyncSession, commit: Commit) -> Miner | None:
        if commit.uid is None:
            return None
        result = await session.execute(
            select(Miner).where(
                Miner.subnet == commit.netuid,
                Miner.uid == commit.uid,
                Miner.status == MinerStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _normalize_version(version: str | None, netuid: int) -> str:
        normalized = normalize_stored_version(version, netuid)
        return normalized or "v6"

    def _build_commitment(self, commit: Commit, miner: Miner | None) -> MinerCommitment:
        version = self._normalize_version(commit.commit_payload.get("version"), commit.netuid)
        return MinerCommitment(
            miner_id=miner.id if miner else None,
            subnet=commit.netuid,
            uid=commit.uid,
            hotkey=commit.hotkey,
            coldkey=commit.coldkey,
            registered_at_block=commit.registered_at_block,
            commit_block=commit.block_number,
            block_hash=commit.block_hash,
            reveal_string=commit.reveal_string,
            version=version,
            repo=commit.commit_payload["repo"],
            digest=commit.commit_payload["digest"],
            model_uri=commit.model_uri,
            payload_hash=commit.payload_hash,
            commit_payload=commit.commit_payload,
            commit_source=commit.commit_source,
        )

    async def _record_history(self, session: AsyncSession, commit: Commit) -> None:
        if not is_albedo_pipe_history_row(commit.reveal_string, commit.commit_payload):
            return
        result = await session.execute(
            select(CommitmentHistory).where(
                CommitmentHistory.subnet == commit.netuid,
                CommitmentHistory.hotkey == commit.hotkey,
                CommitmentHistory.commit_block == commit.block_number,
                CommitmentHistory.payload_hash == commit.payload_hash,
            )
        )
        if result.scalar_one_or_none() is not None:
            return
        session.add(
            CommitmentHistory(
                subnet=commit.netuid,
                uid=commit.uid,
                hotkey=commit.hotkey,
                coldkey=commit.coldkey,
                commit_block=commit.block_number,
                block_hash=commit.block_hash,
                reveal_string=commit.reveal_string,
                repo=commit.commit_payload["repo"],
                digest=commit.commit_payload["digest"],
                model_uri=commit.model_uri,
                payload_hash=commit.payload_hash,
                commit_payload=commit.commit_payload,
            )
        )

    async def _emit(
        self,
        session: AsyncSession,
        event_type: EventType,
        commit: Commit,
        data: dict,
        stats: dict[str, int],
    ) -> None:
        miner = await self._resolve_miner(session, commit)
        session.add(
            Event(
                event_type=event_type,
                miner_id=miner.id if miner else None,
                subnet=commit.netuid,
                block=commit.block_number,
                data={**data, "uid": commit.uid, "hotkey": commit.hotkey},
            )
        )
        stats["events"] += 1
        if self.publisher:
            await self.publisher.publish(event_type.value, commit.netuid, data)
            await self.publisher.publish_live({
                "type": event_type.value,
                "subnet": commit.netuid,
                "uid": commit.uid,
                "hotkey": commit.hotkey,
                "coldkey": commit.coldkey,
                "registered_at_block": commit.registered_at_block,
                "commit_block": commit.block_number,
                "repo": commit.commit_payload.get("repo"),
                "digest": commit.commit_payload.get("digest"),
                "model_uri": commit.model_uri,
                "payload_hash": commit.payload_hash,
                "commit_source": commit.commit_source,
                "version": commit.commit_payload.get("version"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
