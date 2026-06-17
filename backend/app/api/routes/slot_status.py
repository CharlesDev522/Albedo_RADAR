"""Per-UID commitment slot status — all types on one screen."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.subnet_commit_rules import is_published_slot_type
from app.config import get_settings
from app.db.models import MinerSlotStatus
from app.db.session import get_db
from app.schemas.slot_status import SlotStatusEntry, SlotStatusResponse, SlotStatusSummary

router = APIRouter(prefix="/slot-status", tags=["slot-status"])
settings = get_settings()

VALID_FILTERS = {
    "all",
    "v6",
    "json",
    "timelock_encrypted",
    "encrypted",
    "other",
    "unknown",
    "none",
    "committed",
    "unpublished",
    "legacy",
    "binary",
}

VALID_SORTS = {
    "uid_asc",
    "uid_desc",
    "reg_asc",
    "reg_desc",
    "commit_asc",
    "commit_desc",
    "coldkey_asc",
    "coldkey_desc",
    "type",
}


@router.get("", response_model=SlotStatusResponse)
async def list_slot_status(
    subnet: int = Query(default=97, ge=0),
    filter_type: str = Query(default="all", alias="filter"),
    sort: str = Query(default="uid_asc"),
    live: bool = Query(default=False, description="Force live chain scan"),
    db: AsyncSession = Depends(get_db),
) -> SlotStatusResponse:
    """All miner UID slots with commitment type — v6, encrypted, json, none, etc."""
    _ = filter_type  # filter applied client-side; kept for API compat

    all_rows = await _load_slot_rows(db, subnet, force_live=live)
    summary = _summary_from_rows(subnet, all_rows)
    # Return full slot set — client applies filter/sort (avoids re-scan on sort change).
    ordered = sorted(all_rows, key=lambda r: r.uid)

    return SlotStatusResponse(
        subnet=subnet,
        slots=[_entry_from_row(r, subnet) for r in ordered],
        summary=summary,
        filter=filter_type,
        sort=sort,
        source="chain" if live else "db",
    )


async def _load_slot_rows(db: AsyncSession, subnet: int, force_live: bool = False) -> list:
    result = await db.execute(
        select(MinerSlotStatus)
        .where(MinerSlotStatus.subnet == subnet)
        .order_by(MinerSlotStatus.uid.asc())
    )
    db_rows = list(result.scalars().all())

    use_live = force_live

    if use_live:
        try:
            return await _live_slot_rows(subnet)
        except Exception:
            if db_rows:
                return db_rows
            raise

    return db_rows


def _entry_from_row(row, subnet: int) -> SlotStatusEntry:
    published = getattr(row, "is_published", None)
    if published is None:
        published = is_published_slot_type(
            row.commitment_type if isinstance(row.commitment_type, str) else row.commitment_type,
            subnet,
        )
    return SlotStatusEntry.model_validate({
        "uid": row.uid,
        "hotkey": row.hotkey,
        "coldkey": row.coldkey,
        "registered_at_block": row.registered_at_block,
        "commitment_type": row.commitment_type,
        "commit_block": row.commit_block,
        "deposit": row.deposit,
        "reveal_round": row.reveal_round,
        "detail": row.detail,
        "last_updated": getattr(row, "last_updated", None),
        "is_published": published,
    })


def _sort_rows(rows: list, sort: str) -> list:
    if sort not in VALID_SORTS:
        sort = "uid_asc"

    def reg_key(r, asc: bool):
        if r.registered_at_block is None:
            return float("inf") if asc else float("-inf")
        return r.registered_at_block

    def commit_key(r, asc: bool):
        if r.commit_block is None:
            return float("inf") if asc else float("-inf")
        return r.commit_block

    def coldkey_key(r):
        return (r.coldkey or "").lower()

    if sort == "uid_asc":
        return sorted(rows, key=lambda r: r.uid)
    if sort == "uid_desc":
        return sorted(rows, key=lambda r: r.uid, reverse=True)
    if sort == "reg_asc":
        return sorted(rows, key=lambda r: (reg_key(r, True), r.uid))
    if sort == "reg_desc":
        return sorted(rows, key=lambda r: (reg_key(r, False), r.uid), reverse=True)
    if sort == "commit_asc":
        return sorted(rows, key=lambda r: (commit_key(r, True), r.uid))
    if sort == "commit_desc":
        return sorted(rows, key=lambda r: (commit_key(r, False), r.uid), reverse=True)
    if sort == "coldkey_asc":
        return sorted(rows, key=lambda r: (coldkey_key(r) or "\uffff", r.uid))
    if sort == "coldkey_desc":
        return sorted(rows, key=lambda r: (coldkey_key(r) or "", r.uid), reverse=True)
    if sort == "type":
        return sorted(rows, key=lambda r: (r.commitment_type, r.uid))
    return rows


def _filter_rows(rows: list, filt: str, subnet: int = 97) -> list:
    if filt == "all":
        return rows
    if filt == "committed":
        return [r for r in rows if r.commitment_type != "none"]
    if filt == "unpublished":
        return [
            r for r in rows
            if not is_published_slot_type(
                r.commitment_type if isinstance(r.commitment_type, str) else r.commitment_type,
                subnet,
            )
        ]
    if filt == "timelock_encrypted":
        return [r for r in rows if r.commitment_type in ("timelock_encrypted", "binary")]
    if filt in VALID_FILTERS:
        return [r for r in rows if r.commitment_type == filt]
    return rows


async def _live_slot_rows(subnet: int) -> list:
    from bittensor.core.async_subtensor import AsyncSubtensor

    from app.chain_reader.commitment_scanner import _neuron_index
    from app.chain_reader.slot_commitment_scanner import scan_slot_statuses

    async with AsyncSubtensor(network=settings.bittensor_network) as st:
        neurons = await _neuron_index(st, subnet)
        live_slots = await scan_slot_statuses(st, subnet, neurons)

    return [
        MinerSlotStatus(
            subnet=subnet,
            uid=s.uid,
            hotkey=s.hotkey,
            coldkey=s.coldkey,
            registered_at_block=s.registered_at_block,
            commitment_type=s.commitment_type.value,
            commit_block=s.commit_block,
            deposit=s.deposit,
            reveal_round=s.reveal_round,
            detail=s.detail,
            payload_hash=s.payload_hash,
            encrypted_hash=s.encrypted_hash,
        )
        for s in live_slots
    ]


@router.get("/summary", response_model=SlotStatusSummary)
async def slot_summary(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SlotStatusSummary:
    return await _build_summary(db, subnet)


@router.get("/onchain")
async def onchain_slots(subnet: int = Query(default=97, ge=0)) -> dict:
    """Live chain scan — all slot statuses without DB."""
    from bittensor.core.async_subtensor import AsyncSubtensor

    from app.chain_reader.commitment_scanner import _neuron_index
    from app.chain_reader.slot_commitment_scanner import scan_slot_statuses

    async with AsyncSubtensor(network=settings.bittensor_network) as st:
        neurons = await _neuron_index(st, subnet)
        slots = await scan_slot_statuses(st, subnet, neurons)

    counts: dict[str, int] = {}
    for s in slots:
        k = s.commitment_type.value
        counts[k] = counts.get(k, 0) + 1

    return {
        "subnet": subnet,
        "total_slots": len(slots),
        "breakdown": counts,
        "v6_uids": sorted(s.uid for s in slots if s.commitment_type.value == "v6"),
        "encrypted_uids": sorted(
            s.uid for s in slots if s.commitment_type.value == "timelock_encrypted"
        ),
        "none_count": counts.get("none", 0),
    }


async def _build_summary(db: AsyncSession, subnet: int) -> SlotStatusSummary:
    result = await db.execute(
        select(MinerSlotStatus).where(MinerSlotStatus.subnet == subnet)
    )
    rows = list(result.scalars().all())
    return _summary_from_rows(subnet, rows)


def _summary_from_rows(subnet: int, rows: list) -> SlotStatusSummary:
    if not rows:
        return SlotStatusSummary(subnet=subnet, total_slots=0)

    counts: dict[str, int] = {}
    for r in rows:
        ct = r.commitment_type if isinstance(r.commitment_type, str) else r.commitment_type
        counts[ct] = counts.get(ct, 0) + 1

    last_scan = None
    for r in rows:
        if getattr(r, "last_updated", None):
            last_scan = r.last_updated if last_scan is None else max(last_scan, r.last_updated)

    return SlotStatusSummary(
        subnet=subnet,
        total_slots=len(rows),
        v6=counts.get("v6", 0),
        json=counts.get("json", 0),
        timelock_encrypted=counts.get("timelock_encrypted", 0),
        binary=counts.get("binary", 0),
        other=counts.get("other", 0),
        unknown=counts.get("unknown", 0),
        none=counts.get("none", 0),
        committed=len(rows) - counts.get("none", 0),
        unpublished=sum(
            1 for r in rows
            if not is_published_slot_type(
                r.commitment_type if isinstance(r.commitment_type, str) else r.commitment_type,
                subnet,
            )
        ),
        last_scan_at=last_scan or datetime.now(timezone.utc),
    )
