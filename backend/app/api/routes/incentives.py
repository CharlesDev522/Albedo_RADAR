"""Metagraph incentive overview (no external king/duel linkage)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.models import Miner, MinerCommitment, MinerStatus
from app.db.session import get_db
from app.schemas.incentives import IncentiveOverviewResponse, MinerIncentiveEntry

router = APIRouter(prefix="/incentives", tags=["incentives"])
settings = get_settings()

_MODEL_VERSIONS = ("v5", "v6", "json", "quasar")


@router.get("", response_model=IncentiveOverviewResponse)
async def incentive_overview(
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=50, ge=1, le=256),
    min_incentive: float = Query(default=0.0, ge=0.0),
    live: bool = Query(default=False, description="Fetch metagraph from chain (slow)"),
    db: AsyncSession = Depends(get_db),
) -> IncentiveOverviewResponse:
    metagraph_block: int | None = None
    neuron_rows: list[tuple[int, str, str | None, float, float, int | None, bool]] = []

    if live:
        client = SubtensorClient(settings)
        await client.connect()
        try:
            snapshot = await client.get_subnet_snapshot(subnet)
            metagraph_block = snapshot.block
            miners_only = [n for n in snapshot.neurons if not n.is_validator]
            ranked = sorted(miners_only, key=lambda n: n.incentive, reverse=True)
            rank_positions = {n.uid: pos + 1 for pos, n in enumerate(ranked)}
            for n in snapshot.neurons:
                if n.is_validator:
                    continue
                neuron_rows.append(
                    (
                        n.uid,
                        n.hotkey,
                        n.coldkey,
                        n.incentive,
                        n.emission,
                        rank_positions.get(n.uid),
                        n.is_validator,
                    )
                )
        finally:
            await client.disconnect()
    else:
        for m in await _load_miners(db, subnet):
            if m.is_validator:
                continue
            neuron_rows.append(
                (
                    m.uid,
                    m.hotkey,
                    m.coldkey,
                    float(m.current_incentive or 0.0),
                    float(m.current_emission or 0.0),
                    m.rank_position,
                    m.is_validator,
                )
            )

    commits_by_uid = await _load_commits(db, subnet)
    entries: list[MinerIncentiveEntry] = []
    for uid, hotkey, coldkey, incentive, emission, rank_pos, is_validator in neuron_rows:
        if incentive < min_incentive:
            continue
        commit = commits_by_uid.get(uid)
        entries.append(
            MinerIncentiveEntry(
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                incentive=incentive,
                emission=emission,
                rank_position=rank_pos,
                is_validator=is_validator,
                receiving_incentive=incentive > 0,
                commit_repo=commit.repo if commit else None,
            )
        )

    entries.sort(key=lambda e: (-e.incentive, e.uid))
    entries = entries[:limit]
    top = entries[0].incentive if entries else 0.0
    return IncentiveOverviewResponse(
        subnet=subnet,
        metagraph_block=metagraph_block,
        incentivized_count=sum(1 for e in entries if e.receiving_incentive),
        top_incentive=top,
        miners=entries,
    )


async def _load_miners(db: AsyncSession, subnet: int) -> list[Miner]:
    result = await db.execute(
        select(Miner).where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
        ).order_by(Miner.current_incentive.desc(), Miner.uid.asc())
    )
    return list(result.scalars().all())


async def _load_commits(db: AsyncSession, subnet: int) -> dict[int, MinerCommitment]:
    result = await db.execute(
        select(MinerCommitment).where(
            MinerCommitment.subnet == subnet,
            MinerCommitment.version.in_(_MODEL_VERSIONS),
        )
    )
    rows = list(result.scalars().all())
    return {r.uid: r for r in rows if r.uid is not None}
