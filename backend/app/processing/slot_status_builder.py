"""Persist per-UID slot commitment status."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.slot_commitment_scanner import SlotStatus
from app.db.models import MinerSlotStatus


class SlotStatusBuilder:
    async def process_slots(
        self,
        session: AsyncSession,
        slots: list[SlotStatus],
        netuid: int,
    ) -> dict[str, int]:
        stats = {"updated": 0, "unchanged": 0}
        now = datetime.now(timezone.utc)

        for slot in slots:
            result = await session.execute(
                select(MinerSlotStatus).where(
                    MinerSlotStatus.subnet == netuid,
                    MinerSlotStatus.uid == slot.uid,
                )
            )
            row = result.scalar_one_or_none()
            ctype = slot.commitment_type.value

            if row is None:
                session.add(
                    MinerSlotStatus(
                        subnet=netuid,
                        uid=slot.uid,
                        hotkey=slot.hotkey,
                        coldkey=slot.coldkey,
                        registered_at_block=slot.registered_at_block,
                        commitment_type=ctype,
                        commit_block=slot.commit_block,
                        deposit=slot.deposit,
                        reveal_round=slot.reveal_round,
                        detail=slot.detail,
                        reveal_string=slot.reveal_string,
                        payload_hash=slot.payload_hash,
                        encrypted_hash=slot.encrypted_hash,
                        last_updated=now,
                    )
                )
                stats["updated"] += 1
            else:
                changed = (
                    row.hotkey != slot.hotkey
                    or row.commitment_type != ctype
                    or row.payload_hash != slot.payload_hash
                    or row.commit_block != slot.commit_block
                )
                row.hotkey = slot.hotkey
                row.coldkey = slot.coldkey
                row.registered_at_block = slot.registered_at_block
                row.commitment_type = ctype
                row.commit_block = slot.commit_block
                row.deposit = slot.deposit
                row.reveal_round = slot.reveal_round
                row.detail = slot.detail
                row.reveal_string = slot.reveal_string
                row.payload_hash = slot.payload_hash
                row.encrypted_hash = slot.encrypted_hash
                row.last_updated = now
                if changed:
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1

        await session.flush()
        return stats
