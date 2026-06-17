"""Map every miner UID slot to its on-chain commitment status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.chain_reader.chain_snapshot import ChainSnapshot
from app.chain_reader.commitment_classifier import (
    ClassifiedCommitment,
    CommitmentType,
    classify_commitment_raw,
    classify_plaintext_reveal,
)
from app.chain_reader.commitment_scanner import _neuron_index, parse_subnet_model_commit
from app.chain_reader.subnet_commit_rules import is_published_slot_type

logger = logging.getLogger(__name__)


def _latest_revealed_per_hotkey(
    entries: list[tuple[str, int, str]],
    netuid: int,
) -> dict[str, ClassifiedCommitment]:
    """Highest-block valid reveal per hotkey from RevealedCommitments history."""
    latest: dict[str, ClassifiedCommitment] = {}
    for hotkey, block, payload in entries:
        classified = classify_plaintext_reveal(payload, block, 0, hotkey)
        if classified.commitment_type not in (
            CommitmentType.V5,
            CommitmentType.V6,
            CommitmentType.JSON,
        ):
            continue
        prev = latest.get(hotkey)
        if prev is None or block > prev.commit_block:
            latest[hotkey] = classified
    return latest


def _published_v6_per_hotkey(
    entries: list[tuple[str, int, str]],
    netuid: int,
) -> dict[str, tuple[int, str]]:
    """Latest v6 pipe reveal per hotkey (subnet rules applied)."""
    latest: dict[str, tuple[int, str]] = {}
    for hotkey, block, payload in entries:
        if parse_subnet_model_commit(payload, hotkey, netuid) is None:
            continue
        prev = latest.get(hotkey)
        if prev is None or block > prev[0]:
            latest[hotkey] = (block, payload)
    return latest


def _merge_slot_classifications(
    active: dict[str, ClassifiedCommitment],
    revealed: dict[str, ClassifiedCommitment],
) -> dict[str, ClassifiedCommitment]:
    merged = dict(active)
    for hotkey, rev in revealed.items():
        act = merged.get(hotkey)
        if act is None:
            merged[hotkey] = rev
            continue
        if act.commitment_type in (CommitmentType.TIMELOCK_ENCRYPTED, CommitmentType.BINARY):
            continue
        if rev.reveal_string and act.reveal_string and rev.reveal_string == act.reveal_string:
            if rev.commit_block >= act.commit_block:
                merged[hotkey] = rev
            continue
        # Active CommitmentOf wins — do not replace with older revealed payload.
    return merged


@dataclass(frozen=True)
class SlotStatus:
    netuid: int
    uid: int
    hotkey: str
    coldkey: str | None
    registered_at_block: int | None
    commitment_type: CommitmentType
    commit_block: int | None
    deposit: int | None
    reveal_round: int | None
    detail: str | None
    reveal_string: str | None
    payload_hash: str | None
    encrypted_hash: str | None
    is_published: bool = False


def scan_slots_from_snapshot(
    snapshot: ChainSnapshot,
    neurons: dict[str, dict[str, Any]],
) -> list[SlotStatus]:
    """Build slot statuses from a pre-loaded chain snapshot."""
    netuid = snapshot.netuid
    uid_to_neuron: dict[int, dict[str, Any]] = {}
    for hotkey, info in neurons.items():
        uid_to_neuron[int(info["uid"])] = {
            "hotkey": hotkey,
            "coldkey": info.get("coldkey"),
            "registered_at_block": info.get("registered_at_block"),
        }

    commitments_by_hotkey: dict[str, ClassifiedCommitment] = {}
    for hotkey, raw in snapshot.commitment_of.items():
        classified = classify_commitment_raw(raw, hotkey)
        if classified is not None:
            commitments_by_hotkey[hotkey] = classified

    if snapshot.revealed is not None:
        revealed_by_hotkey = _latest_revealed_per_hotkey(snapshot.revealed, netuid)
        commitments_by_hotkey = _merge_slot_classifications(commitments_by_hotkey, revealed_by_hotkey)

    published_hotkeys: set[str] = set()
    for hotkey, classified in commitments_by_hotkey.items():
        if is_published_slot_type(classified.commitment_type.value, netuid):
            published_hotkeys.add(hotkey)
    if snapshot.revealed is not None:
        for hotkey in _published_v6_per_hotkey(snapshot.revealed, netuid):
            published_hotkeys.add(hotkey)
    for hotkey, raw in snapshot.commitment_of.items():
        classified = classify_commitment_raw(raw, hotkey)
        if classified and is_published_slot_type(classified.commitment_type.value, netuid):
            published_hotkeys.add(hotkey)

    slots: list[SlotStatus] = []
    for uid in sorted(uid_to_neuron.keys()):
        neuron = uid_to_neuron[uid]
        hotkey = neuron["hotkey"]
        classified = commitments_by_hotkey.get(hotkey)

        if classified is None:
            slots.append(
                SlotStatus(
                    netuid=netuid,
                    uid=uid,
                    hotkey=hotkey,
                    coldkey=neuron.get("coldkey"),
                    registered_at_block=neuron.get("registered_at_block"),
                    commitment_type=CommitmentType.NONE,
                    commit_block=None,
                    deposit=None,
                    reveal_round=None,
                    detail=None,
                    reveal_string=None,
                    payload_hash=None,
                    encrypted_hash=None,
                    is_published=False,
                )
            )
        else:
            slots.append(
                SlotStatus(
                    netuid=netuid,
                    uid=uid,
                    hotkey=hotkey,
                    coldkey=neuron.get("coldkey"),
                    registered_at_block=neuron.get("registered_at_block"),
                    commitment_type=classified.commitment_type,
                    commit_block=classified.commit_block,
                    deposit=classified.deposit,
                    reveal_round=classified.reveal_round,
                    detail=classified.detail,
                    reveal_string=classified.reveal_string,
                    payload_hash=classified.payload_hash,
                    encrypted_hash=classified.encrypted_hash,
                    is_published=hotkey in published_hotkeys,
                )
            )

    counts: dict[str, int] = {}
    for s in slots:
        k = s.commitment_type.value
        counts[k] = counts.get(k, 0) + 1
    logger.info("slot scan netuid=%d slots=%d breakdown=%s", netuid, len(slots), counts)
    return slots


async def scan_slot_statuses(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]] | None = None,
    snapshot: ChainSnapshot | None = None,
) -> list[SlotStatus]:
    """Return one SlotStatus per registered neuron (typically 256 UIDs)."""
    from app.chain_reader.chain_snapshot import load_chain_snapshot

    if neurons is None:
        neurons = await _neuron_index(subtensor, netuid)
    if snapshot is None:
        snapshot = await load_chain_snapshot(subtensor, netuid, include_revealed=True)
    elif snapshot.revealed is None:
        from app.chain_reader.commitment_scanner import _iter_revealed

        snapshot.revealed = await _iter_revealed(subtensor, netuid)
    return scan_slots_from_snapshot(snapshot, neurons)
