"""Sync metagraph incentive/emission fields into the miner registry."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.subtensor_client import MetagraphSnapshot
from app.db.models import Miner, MinerStatus

logger = logging.getLogger(__name__)

INCENTIVE_EPSILON = 1e-9


async def sync_metagraph_incentives(
    session: AsyncSession,
    snapshot: MetagraphSnapshot,
) -> dict[str, int]:
    """Update current incentive/emission/rank on active miners from a metagraph snapshot."""
    result = await session.execute(
        select(Miner).where(
            Miner.subnet == snapshot.subnet,
            Miner.status == MinerStatus.ACTIVE,
        )
    )
    by_uid = {m.uid: m for m in result.scalars().all()}
    seen: set[int] = set()

    miners_only = [n for n in snapshot.neurons if not n.is_validator]
    ranked = sorted(miners_only, key=lambda n: n.incentive, reverse=True)
    rank_positions = {n.uid: pos + 1 for pos, n in enumerate(ranked)}

    updated = 0
    for neuron in snapshot.neurons:
        seen.add(neuron.uid)
        miner = by_uid.get(neuron.uid)
        if miner is None:
            miner = Miner(
                uid=neuron.uid,
                hotkey=neuron.hotkey,
                coldkey=neuron.coldkey,
                subnet=snapshot.subnet,
                registered_at_block=neuron.registered_at_block,
                status=MinerStatus.ACTIVE,
                is_validator=neuron.is_validator,
            )
            session.add(miner)
            by_uid[neuron.uid] = miner

        rank_pos = rank_positions.get(neuron.uid)
        changed = (
            miner.hotkey != neuron.hotkey
            or miner.coldkey != neuron.coldkey
            or abs(miner.current_incentive - neuron.incentive) > INCENTIVE_EPSILON
            or abs(miner.current_emission - neuron.emission) > INCENTIVE_EPSILON
            or miner.rank_position != rank_pos
            or miner.is_validator != neuron.is_validator
        )
        miner.hotkey = neuron.hotkey
        miner.coldkey = neuron.coldkey
        miner.is_validator = neuron.is_validator
        miner.current_stake = neuron.stake
        miner.current_tao_stake = neuron.tao_stake
        miner.current_emission = neuron.emission
        miner.current_incentive = neuron.incentive
        miner.current_rank = neuron.rank
        miner.current_trust = neuron.trust
        miner.rank_position = rank_pos
        miner.last_seen = datetime.now(timezone.utc)
        if changed:
            updated += 1

    top_uid = ranked[0].uid if ranked else None
    top_incentive = ranked[0].incentive if ranked else 0.0
    logger.info(
        "incentive sync netuid=%d miners=%d updated=%d top_uid=%s top_incentive=%.6f block=%d",
        snapshot.subnet,
        len(miners_only),
        updated,
        top_uid,
        top_incentive,
        snapshot.block,
    )
    await session.flush()
    return {"updated": updated, "miners": len(miners_only), "block": snapshot.block}
