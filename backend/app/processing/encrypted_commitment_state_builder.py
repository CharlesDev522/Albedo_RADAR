"""Persist TimelockEncrypted commitment scans."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.encrypted_commitment_scanner import EncryptedCommit
from app.db.models import EncryptedCommitmentStatus, EncryptedMinerCommitment

logger = logging.getLogger(__name__)


class EncryptedCommitmentStateBuilder:
    async def process_commits(
        self,
        session: AsyncSession,
        commits: list[EncryptedCommit],
        netuid: int,
    ) -> dict[str, int]:
        stats = {"new": 0, "updated": 0, "unchanged": 0, "revealed": 0}
        seen_hotkeys = {c.hotkey for c in commits}

        for commit in commits:
            result = await session.execute(
                select(EncryptedMinerCommitment).where(
                    EncryptedMinerCommitment.subnet == commit.netuid,
                    EncryptedMinerCommitment.hotkey == commit.hotkey,
                )
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                session.add(
                    EncryptedMinerCommitment(
                        subnet=commit.netuid,
                        uid=commit.uid,
                        hotkey=commit.hotkey,
                        coldkey=commit.coldkey,
                        registered_at_block=commit.registered_at_block,
                        commit_block=commit.block_number,
                        deposit=commit.deposit,
                        reveal_round=commit.reveal_round,
                        encrypted_hex=commit.encrypted_hex,
                        encrypted_hash=commit.payload_hash,
                        commitment_kind=commit.commitment_kind,
                        status=EncryptedCommitmentStatus.PENDING,
                    )
                )
                stats["new"] += 1
            elif existing.encrypted_hash != commit.payload_hash:
                existing.uid = commit.uid
                existing.coldkey = commit.coldkey
                existing.registered_at_block = commit.registered_at_block
                existing.commit_block = commit.block_number
                existing.deposit = commit.deposit
                existing.reveal_round = commit.reveal_round
                existing.encrypted_hex = commit.encrypted_hex
                existing.encrypted_hash = commit.payload_hash
                existing.status = EncryptedCommitmentStatus.PENDING
                existing.last_updated = datetime.now(timezone.utc)
                stats["updated"] += 1
            else:
                existing.uid = commit.uid
                existing.coldkey = commit.coldkey
                existing.registered_at_block = commit.registered_at_block
                existing.status = EncryptedCommitmentStatus.PENDING
                stats["unchanged"] += 1

        # No longer TimelockEncrypted on chain — likely revealed to plaintext v5
        active_result = await session.execute(
            select(EncryptedMinerCommitment).where(
                EncryptedMinerCommitment.subnet == netuid,
                EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING,
            )
        )
        for row in active_result.scalars().all():
            if row.hotkey not in seen_hotkeys:
                row.status = EncryptedCommitmentStatus.REVEALED
                row.last_updated = datetime.now(timezone.utc)
                stats["revealed"] += 1

        await session.flush()
        return stats
