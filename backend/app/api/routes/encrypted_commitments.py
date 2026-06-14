"""TimelockEncrypted (pre-reveal) commitment API."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import EncryptedCommitmentStatus, EncryptedMinerCommitment
from app.db.session import get_db
from app.schemas.encrypted_commitment import (
    EncryptedCommitmentListResponse,
    EncryptedCommitmentResponse,
    EncryptedCommitmentStatsResponse,
)

router = APIRouter(prefix="/encrypted-commitments", tags=["encrypted-commitments"])
settings = get_settings()


def _to_response(row: EncryptedMinerCommitment) -> EncryptedCommitmentResponse:
    preview = row.encrypted_hex[:18] + "…" if len(row.encrypted_hex) > 18 else row.encrypted_hex
    return EncryptedCommitmentResponse(
      id=row.id,
      subnet=row.subnet,
      uid=row.uid,
      hotkey=row.hotkey,
      coldkey=row.coldkey,
      registered_at_block=row.registered_at_block,
      commit_block=row.commit_block,
      deposit=row.deposit,
      reveal_round=row.reveal_round,
      encrypted_hash=row.encrypted_hash,
      encrypted_preview=preview,
      commitment_kind=row.commitment_kind,
      status=row.status.value if hasattr(row.status, "value") else str(row.status),
      first_seen=row.first_seen,
      last_updated=row.last_updated,
  )


@router.get("", response_model=EncryptedCommitmentListResponse)
async def list_encrypted_commitments(
    subnet: int = Query(default=97, ge=0),
    status: str | None = Query(default="pending", pattern="^(pending|revealed|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> EncryptedCommitmentListResponse:
    """List TimelockEncrypted miners — ciphertext on chain, not yet readable as v5."""
    query = select(EncryptedMinerCommitment).where(EncryptedMinerCommitment.subnet == subnet)
    if status == "pending":
        query = query.where(EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING)
    elif status == "revealed":
        query = query.where(EncryptedMinerCommitment.status == EncryptedCommitmentStatus.REVEALED)

    count_query = select(func.count()).select_from(EncryptedMinerCommitment).where(
        EncryptedMinerCommitment.subnet == subnet
    )
    if status == "pending":
        count_query = count_query.where(
            EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING
        )
    elif status == "revealed":
        count_query = count_query.where(
            EncryptedMinerCommitment.status == EncryptedCommitmentStatus.REVEALED
        )
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(EncryptedMinerCommitment.commit_block.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(result.scalars().all())

    pending = (
        await db.execute(
            select(func.count())
            .select_from(EncryptedMinerCommitment)
            .where(
                EncryptedMinerCommitment.subnet == subnet,
                EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING,
            )
        )
    ).scalar() or 0

    return EncryptedCommitmentListResponse(
        commitments=[_to_response(r) for r in rows],
        total=total,
        subnet=subnet,
        pending_count=pending,
    )


@router.get("/stats", response_model=EncryptedCommitmentStatsResponse)
async def encrypted_stats(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> EncryptedCommitmentStatsResponse:
    pending = (
        await db.execute(
            select(func.count())
            .select_from(EncryptedMinerCommitment)
            .where(
                EncryptedMinerCommitment.subnet == subnet,
                EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING,
            )
        )
    ).scalar() or 0

    revealed = (
        await db.execute(
            select(func.count())
            .select_from(EncryptedMinerCommitment)
            .where(
                EncryptedMinerCommitment.subnet == subnet,
                EncryptedMinerCommitment.status == EncryptedCommitmentStatus.REVEALED,
            )
        )
    ).scalar() or 0

    latest_block = (
        await db.execute(
            select(func.max(EncryptedMinerCommitment.commit_block)).where(
                EncryptedMinerCommitment.subnet == subnet,
                EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING,
            )
        )
    ).scalar()

    latest_round = (
        await db.execute(
            select(func.max(EncryptedMinerCommitment.reveal_round)).where(
                EncryptedMinerCommitment.subnet == subnet,
                EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING,
            )
        )
    ).scalar()

    last_scan = (
        await db.execute(
            select(func.max(EncryptedMinerCommitment.last_updated)).where(
                EncryptedMinerCommitment.subnet == subnet
            )
        )
    ).scalar()

    return EncryptedCommitmentStatsResponse(
        subnet=subnet,
        pending_encrypted=pending,
        revealed_total=revealed,
        latest_commit_block=latest_block,
        latest_reveal_round=latest_round,
        last_scan_at=last_scan or datetime.now(timezone.utc),
    )


@router.get("/uid/{uid}", response_model=EncryptedCommitmentResponse)
async def get_encrypted_by_uid(
    uid: int,
    subnet: int = Query(default=97),
    db: AsyncSession = Depends(get_db),
) -> EncryptedCommitmentResponse:
    result = await db.execute(
        select(EncryptedMinerCommitment).where(
            EncryptedMinerCommitment.subnet == subnet,
            EncryptedMinerCommitment.uid == uid,
            EncryptedMinerCommitment.status == EncryptedCommitmentStatus.PENDING,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No pending encrypted commitment for this UID")
    return _to_response(row)


@router.get("/onchain")
async def onchain_encrypted(subnet: int = Query(default=97, ge=0)) -> dict:
    """Debug: TimelockEncrypted on chain right now."""
    from bittensor.core.async_subtensor import AsyncSubtensor

    from app.chain_reader.commitment_scanner import _neuron_index
    from app.chain_reader.encrypted_commitment_scanner import (
        scan_encrypted_commitments,
        scan_encrypted_onchain_debug,
    )

    async with AsyncSubtensor(network=settings.bittensor_network) as st:
        neurons = await _neuron_index(st, subnet)
        commits = await scan_encrypted_commitments(st, subnet, neurons)
        breakdown = await scan_encrypted_onchain_debug(st, subnet)

    return {
        **breakdown,
        "onchain_encrypted_count": len(commits),
        "uids": sorted({c.uid for c in commits if c.uid is not None}),
        "commit_blocks": [c.block_number for c in commits],
        "reveal_rounds": [c.reveal_round for c in commits],
    }
