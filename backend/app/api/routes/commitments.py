"""V6 commitment tracking API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.subnet_commit_rules import (
    ALBEDO_PIPE_VERSIONS,
    is_albedo_subnet,
    is_albedo_pipe_history_row,
    model_versions_sql_tuple,
)
from app.config import get_settings
from app.db.models import CommitmentHistory, Miner, MinerCommitment, MinerStatus
from app.db.session import get_db
from app.schemas.commitment import (
    CommitmentHistoryResponse,
    CommitmentListResponse,
    CommitmentResponse,
    CommitmentStatsResponse,
    MinerRegistryEntry,
    MinerRegistryResponse,
)

router = APIRouter(prefix="/commitments", tags=["commitments"])
settings = get_settings()


def _model_only(subnet: int):
    return MinerCommitment.version.in_(model_versions_sql_tuple(subnet))


@router.get("", response_model=CommitmentListResponse)
async def list_commitments(
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="commit_block", pattern="^(commit_block|uid|last_updated)$"),
    db: AsyncSession = Depends(get_db),
) -> CommitmentListResponse:
    """List latest v6 commitments on a subnet, newest commits first."""
    order_col = {
        "commit_block": MinerCommitment.commit_block.desc(),
        "uid": MinerCommitment.uid.asc().nullslast(),
        "last_updated": MinerCommitment.last_updated.desc(),
    }[sort]

    total = (
        await db.execute(
            select(func.count())
            .select_from(MinerCommitment)
            .where(MinerCommitment.subnet == subnet, _model_only(subnet))
        )
    ).scalar() or 0

    result = await db.execute(
        select(MinerCommitment)
        .where(MinerCommitment.subnet == subnet, _model_only(subnet))
        .order_by(order_col)
        .limit(limit)
        .offset(offset)
    )
    commitments = list(result.scalars().all())

    miners_result = await db.execute(
        select(Miner.uid).where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
            ~Miner.is_validator,
        )
    )
    all_uids = {r[0] for r in miners_result.all()}
    committed_uids = {c.uid for c in commitments if c.uid is not None}
    uncommitted = sorted(all_uids - committed_uids)

    return CommitmentListResponse(
        commitments=[CommitmentResponse.model_validate(c) for c in commitments],
        total=total,
        subnet=subnet,
        committed_count=total,
        uncommitted_uids=uncommitted,
    )


@router.get("/stats", response_model=CommitmentStatsResponse)
async def commitment_stats(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> CommitmentStatsResponse:
    total_neurons = (
        await db.execute(
            select(func.count()).select_from(Miner).where(
                Miner.subnet == subnet,
                Miner.status == MinerStatus.ACTIVE,
                Miner.is_validator == False,  # noqa: E712
            )
        )
    ).scalar() or 0

    committed = (
        await db.execute(
            select(func.count())
            .select_from(MinerCommitment)
            .where(MinerCommitment.subnet == subnet, _model_only(subnet))
        )
    ).scalar() or 0

    latest_block = (
        await db.execute(
            select(func.max(MinerCommitment.commit_block)).where(
                MinerCommitment.subnet == subnet, _model_only(subnet)
            )
        )
    ).scalar()

    last_scan = (
        await db.execute(
            select(func.max(MinerCommitment.last_updated)).where(
                MinerCommitment.subnet == subnet, _model_only(subnet)
            )
        )
    ).scalar()

    coverage = (committed / total_neurons * 100) if total_neurons else 0.0

    return CommitmentStatsResponse(
        subnet=subnet,
        total_neurons=total_neurons,
        committed_miners=committed,
        uncommitted_miners=max(0, total_neurons - committed),
        coverage_pct=round(coverage, 1),
        latest_commit_block=latest_block,
        last_scan_at=last_scan or datetime.now(timezone.utc),
    )


@router.get("/registry", response_model=MinerRegistryResponse)
async def miner_registry(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> MinerRegistryResponse:
    """Full miner list with v6 commitment status — committed miners first."""
    miners_result = await db.execute(
        select(Miner).where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
            Miner.is_validator == False,  # noqa: E712
        ).order_by(Miner.uid.asc())
    )
    miners = list(miners_result.scalars().all())

    commits_result = await db.execute(
        select(MinerCommitment).where(MinerCommitment.subnet == subnet, _model_only(subnet))
    )
    all_commits = list(commits_result.scalars().all())
    commits_by_uid = {c.uid: c for c in all_commits if c.uid is not None}

    entries: list[MinerRegistryEntry] = []
    v6_count = 0
    seen_uids: set[int] = set()

    for m in miners:
        seen_uids.add(m.uid)
        c = commits_by_uid.get(m.uid)
        has_v6 = c is not None
        if has_v6:
            v6_count += 1
        incentive = float(m.current_incentive or 0.0)
        entries.append(
            MinerRegistryEntry(
                uid=m.uid,
                hotkey=m.hotkey,
                coldkey=m.coldkey,
                registered_at_block=m.registered_at_block,
                has_v6=has_v6,
                version=c.version if c else None,
                commit_block=c.commit_block if c else None,
                repo=c.repo if c else None,
                model_uri=c.model_uri if c else None,
                commit_source=c.commit_source if c else None,
                last_updated=c.last_updated if c else None,
                incentive=incentive,
                emission=float(m.current_emission or 0.0),
                rank_position=m.rank_position,
                receiving_incentive=incentive > 0,
            )
        )

    for c in all_commits:
        if c.uid is not None and c.uid not in seen_uids:
            v6_count += 1
            entries.append(
                MinerRegistryEntry(
                    uid=c.uid,
                    hotkey=c.hotkey,
                    coldkey=c.coldkey,
                    registered_at_block=c.registered_at_block,
                    has_v6=True,
                    version=c.version,
                    commit_block=c.commit_block,
                    repo=c.repo,
                    model_uri=c.model_uri,
                    commit_source=c.commit_source,
                    last_updated=c.last_updated,
                )
            )

    entries.sort(key=lambda e: (not e.has_v6, -(e.commit_block or 0), e.uid))

    return MinerRegistryResponse(
        subnet=subnet,
        miners=entries,
        total=len(entries),
        v6_count=v6_count,
        uncommitted_count=sum(1 for e in entries if not e.has_v6),
    )


@router.get("/uid/{uid}", response_model=CommitmentResponse)
async def get_commitment_by_uid(
    uid: int,
    subnet: int = Query(default=97),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    result = await db.execute(
        select(MinerCommitment).where(
            MinerCommitment.subnet == subnet,
            MinerCommitment.uid == uid,
            _model_only(subnet),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No v6 commitment for this UID")
    return CommitmentResponse.model_validate(row)


@router.get("/hotkey/{hotkey}", response_model=CommitmentResponse)
async def get_commitment_by_hotkey(
    hotkey: str,
    subnet: int = Query(default=97),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    result = await db.execute(
        select(MinerCommitment).where(
            MinerCommitment.subnet == subnet,
            MinerCommitment.hotkey == hotkey,
            _model_only(subnet),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No v6 commitment for this hotkey")
    return CommitmentResponse.model_validate(row)


@router.get("/history/by-hotkey/{hotkey}", response_model=list[CommitmentHistoryResponse])
async def get_commitment_history(
    hotkey: str,
    subnet: int = Query(default=97),
    db: AsyncSession = Depends(get_db),
) -> list[CommitmentHistoryResponse]:
    result = await db.execute(
        select(CommitmentHistory)
        .where(CommitmentHistory.subnet == subnet, CommitmentHistory.hotkey == hotkey)
        .order_by(CommitmentHistory.commit_block.desc())
    )
    rows = list(result.scalars().all())
    if is_albedo_subnet(subnet):
        rows = [h for h in rows if is_albedo_pipe_history_row(h.reveal_string, h.commit_payload)]
    return [CommitmentHistoryResponse.model_validate(h) for h in rows]


@router.get("/sync-status")
async def sync_status(
    subnet: int = Query(default=97, ge=0),
    live: bool = Query(default=False, description="Run on-chain scan (slow)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Compare on-chain v6 commits vs database. Default is DB-only (fast)."""
    db_rows = (
        await db.execute(
            select(MinerCommitment).where(
                MinerCommitment.subnet == subnet,
                _model_only(subnet),
            )
        )
    ).scalars().all()

    db_count = len(db_rows)
    db_uids = sorted({r.uid for r in db_rows if r.uid is not None})
    db_hotkeys = {r.hotkey: r.payload_hash for r in db_rows}
    last_db_update = max((r.last_updated for r in db_rows if r.last_updated), default=None)

    if not live:
        return {
            "subnet": subnet,
            "onchain_v6_count": None,
            "db_v6_count": db_count,
            "in_sync": None,
            "onchain_uids": [],
            "db_uids": db_uids,
            "missing_in_db": [],
            "stale_in_db": [],
            "repos": [r.repo for r in db_rows],
            "last_db_update": last_db_update.isoformat() if last_db_update else None,
            "mode": "db",
        }

    from bittensor.core.async_subtensor import AsyncSubtensor

    from app.chain_reader.chain_snapshot import load_chain_snapshot
    from app.chain_reader.commitment_scanner import _neuron_index, scan_v6_from_snapshot

    async with AsyncSubtensor(network=settings.bittensor_network) as st:
        neurons = await _neuron_index(st, subnet)
        snapshot = await load_chain_snapshot(st, subnet, include_revealed=True)
        commits = await scan_v6_from_snapshot(
            snapshot, neurons, st, include_revealed=True, fetch_block_hashes=False
        )

    onchain_uids = sorted({c.uid for c in commits if c.uid is not None})
    onchain_map = {c.hotkey: c.payload_hash for c in commits}
    missing_in_db = sorted(
        hk for hk, h in onchain_map.items() if db_hotkeys.get(hk) != h
    )
    stale_in_db = sorted(set(db_hotkeys) - set(onchain_map))

    return {
        "subnet": subnet,
        "onchain_v6_count": len(commits),
        "db_v6_count": db_count,
        "in_sync": not missing_in_db and not stale_in_db,
        "onchain_uids": onchain_uids,
        "db_uids": db_uids,
        "missing_in_db": [
            c.uid for c in commits if c.hotkey in missing_in_db and c.uid is not None
        ],
        "stale_in_db": [
            r.uid for r in db_rows if r.hotkey in stale_in_db and r.uid is not None
        ],
        "repos": [c.commit_payload.get("repo") for c in commits],
        "last_db_update": last_db_update.isoformat() if last_db_update else None,
        "mode": "live",
    }


@router.get("/unpublished")
async def unpublished_miners(
    subnet: int = Query(default=97, ge=0),
    live: bool = Query(default=False, description="Run on-chain scan (slow)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SN97: registered miners with no v6/v7 pipe publish."""
    if not is_albedo_subnet(subnet):
        return {
            "subnet": subnet,
            "note": "v6/v7 pipe unpublished detection applies to SN97 Albedo",
            "unpublished_uids": [],
            "unpublished_count": 0,
        }

    miners_result = await db.execute(
        select(Miner).where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
            Miner.is_validator == False,  # noqa: E712
        )
    )
    all_uids = {m.uid for m in miners_result.scalars().all()}

    if live:
        from bittensor.core.async_subtensor import AsyncSubtensor

        from app.chain_reader.chain_snapshot import load_chain_snapshot
        from app.chain_reader.commitment_scanner import _neuron_index, scan_v6_from_snapshot

        async with AsyncSubtensor(network=settings.bittensor_network) as st:
            neurons = await _neuron_index(st, subnet)
            snapshot = await load_chain_snapshot(st, subnet, include_revealed=True)
            commits = await scan_v6_from_snapshot(
                snapshot, neurons, st, include_revealed=True, fetch_block_hashes=False
            )
        published_uids = {c.uid for c in commits if c.uid is not None}
        source = "chain"
    else:
        commits_result = await db.execute(
            select(MinerCommitment.uid).where(
                MinerCommitment.subnet == subnet,
                MinerCommitment.version.in_(tuple(ALBEDO_PIPE_VERSIONS)),
            )
        )
        published_uids = {r[0] for r in commits_result.all() if r[0] is not None}
        source = "db"

    unpublished = sorted(all_uids - published_uids)
    return {
        "subnet": subnet,
        "source": source,
        "total_registered": len(all_uids),
        "published_count": len(published_uids),
        "unpublished_count": len(unpublished),
        "unpublished_uids": unpublished,
        "detection_rule": "registered miner with no v6/v7 pipe in active CommitmentOf ∪ latest revealed pipe",
    }


@router.get("/onchain")
async def onchain_v6_count(subnet: int = Query(default=97, ge=0)) -> dict:
    """Debug: v6 model commits on chain right now."""
    from bittensor.core.async_subtensor import AsyncSubtensor

    from app.chain_reader.commitment_scanner import _neuron_index, scan_v6_active_fast

    async with AsyncSubtensor(network=settings.bittensor_network) as st:
        neurons = await _neuron_index(st, subnet)
        commits = await scan_v6_active_fast(st, subnet, neurons)

    return {
        "subnet": subnet,
        "onchain_v6_count": len(commits),
        "uids": sorted({c.uid for c in commits if c.uid is not None}),
        "hotkeys": [c.hotkey for c in commits],
        "repos": [c.commit_payload.get("repo") for c in commits],
    }
