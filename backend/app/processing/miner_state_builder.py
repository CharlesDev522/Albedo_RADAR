"""Processing engine: builds miner state, relationships, and detects changes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import MetagraphSnapshot, NeuronSnapshot
from app.db.models import (
    ColdkeyRecord,
    Emission,
    Event,
    EventType,
    HotkeyRecord,
    Miner,
    MinerStatus,
    Ranking,
    Stake,
    SubnetSnapshot,
)

logger = logging.getLogger(__name__)

STAKE_CHANGE_THRESHOLD = 0.01  # 1% relative change
EMISSION_CHANGE_THRESHOLD = 0.05  # 5% relative change
RANK_CHANGE_THRESHOLD = 0.01


class MinerStateBuilder:
    """Processes metagraph snapshots into persistent miner state and events."""

    def __init__(self, publisher: EventPublisher | None = None) -> None:
        self.publisher = publisher

    async def process_snapshot(self, session: AsyncSession, snapshot: MetagraphSnapshot) -> dict[str, int]:
        """Diff metagraph snapshot against DB state and emit events."""
        stats = {"new": 0, "updated": 0, "deregistered": 0, "events": 0}

        result = await session.execute(
            select(Miner).where(
                Miner.subnet == snapshot.subnet,
                Miner.status == MinerStatus.ACTIVE,
            )
        )
        existing_miners = {m.uid: m for m in result.scalars().all()}
        seen_uids: set[int] = set()

        # Compute rank positions from incentive scores
        ranked = sorted(snapshot.neurons, key=lambda n: n.incentive, reverse=True)
        rank_positions = {n.uid: pos + 1 for pos, n in enumerate(ranked)}

        for neuron in snapshot.neurons:
            seen_uids.add(neuron.uid)
            rank_pos = rank_positions.get(neuron.uid)

            if neuron.uid not in existing_miners:
                await self._register_miner(session, snapshot, neuron, rank_pos, stats)
            else:
                await self._update_miner(session, snapshot, existing_miners[neuron.uid], neuron, rank_pos, stats)

            await self._update_hotkey_record(session, snapshot.subnet, neuron)
            await self._update_coldkey_record(session, snapshot.subnet, neuron)

        # Detect deregistrations
        for uid, miner in existing_miners.items():
            if uid not in seen_uids:
                await self._deregister_miner(session, snapshot, miner, stats)

        # Record subnet snapshot
        session.add(
            SubnetSnapshot(
                subnet=snapshot.subnet,
                block=snapshot.block,
                neuron_count=len(snapshot.neurons),
                total_stake=snapshot.total_stake,
            )
        )

        await session.flush()
        return stats

    async def _register_miner(
        self,
        session: AsyncSession,
        snapshot: MetagraphSnapshot,
        neuron: NeuronSnapshot,
        rank_pos: int | None,
        stats: dict[str, int],
    ) -> Miner:
        # Check if hotkey was previously on a different UID (hotkey replacement)
        hotkey_result = await session.execute(
            select(HotkeyRecord).where(
                HotkeyRecord.hotkey == neuron.hotkey,
                HotkeyRecord.subnet == snapshot.subnet,
                HotkeyRecord.is_active == True,  # noqa: E712
            )
        )
        prev_hotkey = hotkey_result.scalar_one_or_none()

        miner = Miner(
            uid=neuron.uid,
            hotkey=neuron.hotkey,
            coldkey=neuron.coldkey,
            subnet=snapshot.subnet,
            registered_at_block=snapshot.block,
            status=MinerStatus.ACTIVE,
            is_validator=neuron.is_validator,
            current_stake=neuron.stake,
            current_alpha_stake=neuron.alpha_stake,
            current_tao_stake=neuron.tao_stake,
            current_emission=neuron.emission,
            current_incentive=neuron.incentive,
            current_rank=neuron.rank,
            current_trust=neuron.trust,
            rank_position=rank_pos,
        )
        session.add(miner)
        await session.flush()

        event_data: dict[str, Any] = {
            "uid": neuron.uid,
            "hotkey": neuron.hotkey,
            "coldkey": neuron.coldkey,
            "block": snapshot.block,
        }

        if prev_hotkey and prev_hotkey.uid != neuron.uid:
            event_data["previous_uid"] = prev_hotkey.uid
            await self._emit_event(
                session, EventType.HOTKEY_CHANGED, snapshot.subnet, miner, snapshot.block, event_data, stats
            )
        else:
            await self._emit_event(
                session, EventType.REGISTERED, snapshot.subnet, miner, snapshot.block, event_data, stats
            )

        self._record_timeseries(session, miner, neuron, snapshot.block, rank_pos or 0)
        stats["new"] += 1
        return miner

    async def _update_miner(
        self,
        session: AsyncSession,
        snapshot: MetagraphSnapshot,
        miner: Miner,
        neuron: NeuronSnapshot,
        rank_pos: int | None,
        stats: dict[str, int],
    ) -> None:
        changed = False

        if miner.hotkey != neuron.hotkey:
            event_data = {
                "old_hotkey": miner.hotkey,
                "new_hotkey": neuron.hotkey,
                "uid": neuron.uid,
                "block": snapshot.block,
            }
            await self._emit_event(
                session, EventType.HOTKEY_CHANGED, snapshot.subnet, miner, snapshot.block, event_data, stats
            )
            miner.hotkey = neuron.hotkey
            changed = True

        if miner.coldkey != neuron.coldkey:
            event_data = {
                "old_coldkey": miner.coldkey,
                "new_coldkey": neuron.coldkey,
                "uid": neuron.uid,
                "block": snapshot.block,
            }
            await self._emit_event(
                session, EventType.HOTKEY_TRANSFER, snapshot.subnet, miner, snapshot.block, event_data, stats
            )
            miner.coldkey = neuron.coldkey
            changed = True

        if self._relative_change(miner.current_stake, neuron.stake) > STAKE_CHANGE_THRESHOLD:
            event_data = {
                "old_stake": miner.current_stake,
                "new_stake": neuron.stake,
                "change_pct": self._relative_change(miner.current_stake, neuron.stake) * 100,
                "uid": neuron.uid,
            }
            await self._emit_event(
                session, EventType.STAKE_CHANGED, snapshot.subnet, miner, snapshot.block, event_data, stats
            )
            changed = True

        if self._relative_change(miner.current_emission, neuron.emission) > EMISSION_CHANGE_THRESHOLD:
            event_data = {
                "old_emission": miner.current_emission,
                "new_emission": neuron.emission,
                "uid": neuron.uid,
            }
            await self._emit_event(
                session, EventType.EMISSION_CHANGED, snapshot.subnet, miner, snapshot.block, event_data, stats
            )
            changed = True

        if abs(miner.current_rank - neuron.rank) > RANK_CHANGE_THRESHOLD or miner.rank_position != rank_pos:
            event_data = {
                "old_rank": miner.current_rank,
                "new_rank": neuron.rank,
                "old_position": miner.rank_position,
                "new_position": rank_pos,
                "uid": neuron.uid,
            }
            await self._emit_event(
                session, EventType.RANK_CHANGED, snapshot.subnet, miner, snapshot.block, event_data, stats
            )
            changed = True

        miner.current_stake = neuron.stake
        miner.current_alpha_stake = neuron.alpha_stake
        miner.current_tao_stake = neuron.tao_stake
        miner.current_emission = neuron.emission
        miner.current_incentive = neuron.incentive
        miner.current_rank = neuron.rank
        miner.current_trust = neuron.trust
        miner.rank_position = rank_pos
        miner.is_validator = neuron.is_validator
        miner.last_seen = datetime.now(timezone.utc)

        self._record_timeseries(session, miner, neuron, snapshot.block, rank_pos or 0)

        if changed:
            stats["updated"] += 1

    async def _deregister_miner(
        self,
        session: AsyncSession,
        snapshot: MetagraphSnapshot,
        miner: Miner,
        stats: dict[str, int],
    ) -> None:
        miner.status = MinerStatus.DEREGISTERED
        miner.last_seen = datetime.now(timezone.utc)

        event_data = {
            "uid": miner.uid,
            "hotkey": miner.hotkey,
            "coldkey": miner.coldkey,
            "block": snapshot.block,
        }
        await self._emit_event(
            session, EventType.DEREGISTERED, snapshot.subnet, miner, snapshot.block, event_data, stats
        )
        stats["deregistered"] += 1

    async def _emit_event(
        self,
        session: AsyncSession,
        event_type: EventType,
        subnet: int,
        miner: Miner | None,
        block: int,
        data: dict[str, Any],
        stats: dict[str, int],
    ) -> None:
        event = Event(
            event_type=event_type,
            miner_id=miner.id if miner else None,
            subnet=subnet,
            block=block,
            data=data,
        )
        session.add(event)
        stats["events"] += 1

        if self.publisher:
            await self.publisher.publish(event_type.value, subnet, data)

    def _record_timeseries(
        self,
        session: AsyncSession,
        miner: Miner,
        neuron: NeuronSnapshot,
        block: int,
        rank_pos: int,
    ) -> None:
        session.add(
            Emission(
                miner_id=miner.id,
                block=block,
                emission=neuron.emission,
                incentive=neuron.incentive,
                dividends=neuron.dividends,
            )
        )
        session.add(
            Stake(
                miner_id=miner.id,
                block=block,
                stake=neuron.stake,
                alpha_stake=neuron.alpha_stake,
                tao_stake=neuron.tao_stake,
            )
        )
        session.add(
            Ranking(
                miner_id=miner.id,
                block=block,
                rank=neuron.rank,
                rank_position=rank_pos,
                trust=neuron.trust,
            )
        )

    async def _update_hotkey_record(
        self, session: AsyncSession, subnet: int, neuron: NeuronSnapshot
    ) -> None:
        result = await session.execute(
            select(HotkeyRecord).where(
                HotkeyRecord.hotkey == neuron.hotkey,
                HotkeyRecord.subnet == subnet,
            )
        )
        record = result.scalar_one_or_none()

        if record is None:
            record = HotkeyRecord(
                hotkey=neuron.hotkey,
                coldkey=neuron.coldkey,
                subnet=subnet,
                uid=neuron.uid,
                uid_history=[{"uid": neuron.uid, "block": None, "timestamp": datetime.now(timezone.utc).isoformat()}],
            )
            session.add(record)
        else:
            record.coldkey = neuron.coldkey
            record.uid = neuron.uid
            record.is_active = True
            record.last_seen = datetime.now(timezone.utc)

            if record.uid_history and record.uid_history[-1].get("uid") != neuron.uid:
                history = list(record.uid_history)
                history.append(
                    {"uid": neuron.uid, "block": None, "timestamp": datetime.now(timezone.utc).isoformat()}
                )
                record.uid_history = history

    async def _update_coldkey_record(
        self, session: AsyncSession, subnet: int, neuron: NeuronSnapshot
    ) -> None:
        result = await session.execute(
            select(ColdkeyRecord).where(ColdkeyRecord.coldkey == neuron.coldkey)
        )
        record = result.scalar_one_or_none()

        if record is None:
            record = ColdkeyRecord(
                coldkey=neuron.coldkey,
                miner_count=0 if neuron.is_validator else 1,
                validator_count=1 if neuron.is_validator else 0,
                total_stake=neuron.stake,
                total_emission=neuron.emission,
                hotkeys=[neuron.hotkey],
                subnets=[subnet],
            )
            session.add(record)
        else:
            # Re-aggregate from active miners for this coldkey
            miners_result = await session.execute(
                select(Miner).where(
                    Miner.coldkey == neuron.coldkey,
                    Miner.status == MinerStatus.ACTIVE,
                )
            )
            miners = list(miners_result.scalars().all())
            record.miner_count = sum(1 for m in miners if not m.is_validator)
            record.validator_count = sum(1 for m in miners if m.is_validator)
            record.total_stake = sum(m.current_stake for m in miners)
            record.total_emission = sum(m.current_emission for m in miners)
            record.hotkeys = list({m.hotkey for m in miners})
            record.subnets = list({m.subnet for m in miners})
            record.last_seen = datetime.now(timezone.utc)

    @staticmethod
    def _relative_change(old: float, new: float) -> float:
        if old == 0:
            return 1.0 if new != 0 else 0.0
        return abs(new - old) / abs(old)
