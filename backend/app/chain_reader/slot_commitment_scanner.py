"""Map every miner UID slot to its on-chain commitment status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.chain_reader.commitment_classifier import (
    ClassifiedCommitment,
    CommitmentType,
    classify_commitment_raw,
)
from app.chain_reader.commitment_scanner import _neuron_index
from app.chain_reader.encrypted_commitment_scanner import _iter_commitment_of_raw

logger = logging.getLogger(__name__)


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


async def scan_slot_statuses(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]] | None = None,
) -> list[SlotStatus]:
    """Return one SlotStatus per registered neuron (typically 256 UIDs)."""
    if neurons is None:
        neurons = await _neuron_index(subtensor, netuid)

    uid_to_neuron: dict[int, dict[str, Any]] = {}
    for hotkey, info in neurons.items():
        uid_to_neuron[int(info["uid"])] = {
            "hotkey": hotkey,
            "coldkey": info.get("coldkey"),
            "registered_at_block": info.get("registered_at_block"),
        }

    commitments_by_hotkey: dict[str, ClassifiedCommitment] = {}
    async for hotkey, raw in _iter_commitment_of_raw(subtensor, netuid):
        classified = classify_commitment_raw(raw, hotkey)
        if classified is not None:
            commitments_by_hotkey[hotkey] = classified

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
                )
            )

    counts = {}
    for s in slots:
        k = s.commitment_type.value
        counts[k] = counts.get(k, 0) + 1

    logger.info("slot scan netuid=%d slots=%d breakdown=%s", netuid, len(slots), counts)
    return slots
