"""V5 commitment tracking API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.get("", response_model=CommitmentListResponse)
async def list_commitments(
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="commit_block", pattern="^(commit_block|uid|last_updated)$"),
    db: AsyncSession = Depends(get_db),
) -> CommitmentListResponse:
    """List latest v5 commitments on a subnet, newest commits first."""
    order_col = {
        "commit_block": MinerCommitment.commit_block.desc(),
        "uid": MinerCommitment.uid.asc().nullslast(),
        "last_updated": MinerCommitment.last_updated.desc(),
    }[sort]

    total = (
        await db.execute(
            select(func.count()).select_from(MinerCommitment).where(MinerCommitment.subnet == subnet)
        )
    ).scalar() or 0

    result = await db.execute(
        select(MinerCommitment)
        .where(MinerCommitment.subnet == subnet)
        .order_by(order_col)
        .limit(limit)
        .offset(offset)
    )
    commitments = list(result.scalars().all())

    # UIDs registered but without a v5 commitment
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
            select(func.count()).select_from(MinerCommitment).where(MinerCommitment.subnet == subnet)
        )
    ).scalar() or 0

    latest_block = (
        await db.execute(
            select(func.max(MinerCommitment.commit_block)).where(MinerCommitment.subnet == subnet)
        )
    ).scalar()

    last_scan = (
        await db.execute(
            select(func.max(MinerCommitment.last_updated)).where(MinerCommitment.subnet == subnet)
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


@router.get("/uid/{uid}", response_model=CommitmentResponse)
async def get_commitment_by_uid(
    uid: int,
    subnet: int = Query(default=97),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    result = await db.execute(
        select(MinerCommitment).where(MinerCommitment.subnet == subnet, MinerCommitment.uid == uid)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No v5 commitment for this UID")
    return CommitmentResponse.model_validate(row)


@router.get("/hotkey/{hotkey}", response_model=CommitmentResponse)
async def get_commitment_by_hotkey(
    hotkey: str,
    subnet: int = Query(default=97),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    result = await db.execute(
        select(MinerCommitment).where(MinerCommitment.subnet == subnet, MinerCommitment.hotkey == hotkey)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No v5 commitment for this hotkey")
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
    return [CommitmentHistoryResponse.model_validate(h) for h in result.scalars().all()]


@router.get("/registry", response_model=MinerRegistryResponse)
async def miner_registry(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> MinerRegistryResponse:
    """Full miner list with v5 commitment status — committed miners first."""
    miners_result = await db.execute(
        select(Miner).where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
            Miner.is_validator == False,  # noqa: E712
        ).order_by(Miner.uid.asc())
    )
    miners = list(miners_result.scalars().all())

    commits_result = await db.execute(
        select(MinerCommitment).where(MinerCommitment.subnet == subnet)
    )
    commits_by_uid = {c.uid: c for c in commits_result.scalars().all() if c.uid is not None}

    entries: list[MinerRegistryEntry] = []
    v5_count = 0

    for m in miners:
        c = commits_by_uid.get(m.uid)
        has_v5 = c is not None
        if has_v5:
            v5_count += 1
        entries.append(
            MinerRegistryEntry(
                uid=m.uid,
                hotkey=m.hotkey,
                coldkey=m.coldkey,
                registered_at_block=m.registered_at_block,
                has_v5=has_v5,
                commit_block=c.commit_block if c else None,
                repo=c.repo if c else None,
                model_uri=c.model_uri if c else None,
                commit_source=c.commit_source if c else None,
                last_updated=c.last_updated if c else None,
            )
        )

    # Sort: v5 committed first (newest commit block), then uncommitted by uid
    entries.sort(key=lambda e: (not e.has_v5, -(e.commit_block or 0), e.uid))

    return MinerRegistryResponse(
        subnet=subnet,
        miners=entries,
        total=len(entries),
        v5_count=v5_count,
        uncommitted_count=len(entries) - v5_count,
    )
