"""Albedo king status + metagraph incentive overview for SN97."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.models import Miner, MinerCommitment, MinerStatus
from app.db.session import get_db
from app.integrations.albedo_client import fetch_albedo_dashboard, king_hotkey, king_uid
from app.schemas.albedo import (
    AlbedoEvalStats,
    AlbedoHistoryItem,
    AlbedoKing,
    AlbedoStatusResponse,
    IncentiveOverviewResponse,
    MinerIncentiveEntry,
)

router = APIRouter(prefix="/albedo", tags=["albedo"])
settings = get_settings()

_MODEL_VERSIONS = ("v5", "v6")


def _parse_king(raw: dict | None) -> AlbedoKing | None:
    if not raw:
        return None
    return AlbedoKing(
        hotkey=str(raw.get("hotkey", "")),
        uid=raw.get("uid"),
        coldkey=raw.get("coldkey") or None,
        model_repo=raw.get("model_repo"),
        model_digest=raw.get("model_digest"),
        crowned_at=raw.get("crowned_at"),
        reign_number=raw.get("reign_number"),
        weight=raw.get("weight"),
        weight_share=raw.get("weight_share"),
        registered=raw.get("registered"),
        challenge_id=raw.get("challenge_id"),
    )


def _parse_history(items: list[dict]) -> list[AlbedoHistoryItem]:
    out: list[AlbedoHistoryItem] = []
    for item in items[:30]:
        verdict = item.get("verdict") or {}
        out.append(
            AlbedoHistoryItem(
                type=str(item.get("type", "unknown")),
                eval_id=item.get("eval_id"),
                hotkey=item.get("hotkey"),
                uid=item.get("uid"),
                model_repo=item.get("model_repo"),
                accepted=item.get("accepted"),
                winner=item.get("winner") or verdict.get("winner"),
                code=item.get("code") or item.get("error_code"),
                detail=item.get("detail") or item.get("error_detail"),
                completed_at=item.get("completed_at"),
            )
        )
    return out


@router.get("/status", response_model=AlbedoStatusResponse)
async def albedo_status(
    subnet: int = Query(default=97, ge=0),
) -> AlbedoStatusResponse:
    """Current Albedo king, eval queue, and recent duel history (Hippius dashboard API)."""
    dashboard = await fetch_albedo_dashboard()
    stats_raw = (dashboard or {}).get("stats") or {}
    king_raw = (dashboard or {}).get("king")
    chain_raw = (dashboard or {}).get("king_chain") or []
    history_raw = (dashboard or {}).get("history") or []

    return AlbedoStatusResponse(
        subnet=subnet,
        updated_at=(dashboard or {}).get("updated_at"),
        source_url=settings.albedo_dashboard_url,
        king=_parse_king(king_raw),
        king_chain=[k for k in (_parse_king(x) for x in chain_raw) if k is not None],
        queue_len=int((dashboard or {}).get("queue_len") or 0),
        current_eval=(dashboard or {}).get("current_eval"),
        stats=AlbedoEvalStats(
            queued=int(stats_raw.get("queued") or 0),
            accepted=int(stats_raw.get("accepted") or 0),
            rejected=int(stats_raw.get("rejected") or 0),
            failed=int(stats_raw.get("failed") or 0),
            duplicates=int(stats_raw.get("duplicates") or 0),
            injection_attempts=int(stats_raw.get("injection_attempts") or 0),
        ),
        recent_history=_parse_history(history_raw),
    )


@router.get("/incentives", response_model=IncentiveOverviewResponse)
async def incentive_overview(
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=50, ge=1, le=256),
    min_incentive: float = Query(default=0.0, ge=0.0),
    live: bool = Query(default=False, description="Fetch metagraph from chain (slow)"),
    db: AsyncSession = Depends(get_db),
) -> IncentiveOverviewResponse:
    """Metagraph incentive/emission per miner, merged with Albedo king identity."""
    dashboard = await fetch_albedo_dashboard()
    king = _parse_king((dashboard or {}).get("king"))
    king_hk = king_hotkey(dashboard)
    king_id = king_uid(dashboard)

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
        miners_result = await _load_miners(db, subnet)
        for m in miners_result:
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
        is_king = (king_hk is not None and hotkey == king_hk) or (
            king_id is not None and uid == king_id
        )
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
                is_king=is_king,
                king_model_repo=king.model_repo if is_king and king else None,
                commit_repo=commit.repo if commit else None,
            )
        )

    entries.sort(key=lambda e: (-e.incentive, e.uid))
    entries = entries[:limit]
    top = entries[0].incentive if entries else 0.0
    incentivized = sum(1 for e in entries if e.receiving_incentive)

    return IncentiveOverviewResponse(
        subnet=subnet,
        metagraph_block=metagraph_block,
        king=king,
        incentivized_count=incentivized,
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
