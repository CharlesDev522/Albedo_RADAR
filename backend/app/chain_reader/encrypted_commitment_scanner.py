"""Detect TimelockEncrypted commitments on CommitmentOf (pre-reveal, ciphertext on chain)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.chain_reader.commitment_decoder import (
    CommitmentKind,
    decode_commitment_of_raw,
    encrypted_payload_hash,
    iter_commitment_of_raw,
    parse_timelock_encrypted,
)
from app.chain_reader.commitment_scanner import _neuron_index, parse_model_commit

logger = logging.getLogger(__name__)

TIMELOCK_KIND = "TimelockEncrypted"

# Re-export for callers that imported from here previously.
_iter_commitment_of_raw = iter_commitment_of_raw


@dataclass(frozen=True)
class EncryptedCommit:
    netuid: int
    block_number: int
    uid: int | None
    hotkey: str
    coldkey: str | None
    registered_at_block: int | None
    deposit: int
    reveal_round: int
    encrypted_hex: str
    payload_hash: str
    commitment_kind: str = TIMELOCK_KIND


def is_plaintext_commitment(field: Any, hotkey: str = "") -> bool:
    """True if field decodes to readable JSON/other text (not TimelockEncrypted)."""
    if parse_timelock_encrypted(field) is not None:
        return False
    if not isinstance(field, dict):
        return False
    for key, val in field.items():
        if not str(key).startswith("Raw") or not isinstance(val, str):
            continue
        try:
            text = bytes.fromhex(val.removeprefix("0x")).decode("utf-8", errors="ignore")
        except Exception:
            return False
        return bool(text.strip())
    return False


async def scan_encrypted_commitments(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]] | None = None,
) -> list[EncryptedCommit]:
    """Return active TimelockEncrypted commitments (parsed from raw CommitmentOf first)."""
    if neurons is None:
        neurons = await _neuron_index(subtensor, netuid)

    commits: list[EncryptedCommit] = []

    async for hotkey, raw in iter_commitment_of_raw(subtensor, netuid):
        decoded = decode_commitment_of_raw(raw)
        if decoded.kind != CommitmentKind.TIMELOCK_ENCRYPTED:
            continue
        if not decoded.encrypted_hex or decoded.reveal_round is None:
            continue

        neuron = neurons.get(hotkey)
        uid = neuron["uid"] if neuron else None
        coldkey = neuron["coldkey"] if neuron else None
        reg_block = neuron["registered_at_block"] if neuron else None

        if uid is None:
            logger.info("encrypted commit for hotkey without uid mapping: %s", hotkey)

        commits.append(
            EncryptedCommit(
                netuid=netuid,
                block_number=decoded.commit_block,
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                registered_at_block=reg_block,
                deposit=decoded.deposit,
                reveal_round=decoded.reveal_round,
                encrypted_hex=decoded.encrypted_hex,
                payload_hash=encrypted_payload_hash(decoded.encrypted_hex, decoded.reveal_round),
            )
        )

    logger.info(
        "encrypted scan netuid=%d: timelock=%d uids=%s",
        netuid,
        len(commits),
        sorted({c.uid for c in commits if c.uid is not None}),
    )
    return commits


async def scan_encrypted_onchain_debug(subtensor: Any, netuid: int) -> dict[str, Any]:
    """Debug helper: count TimelockEncrypted vs plaintext kinds on CommitmentOf."""
    timelock = 0
    v6_plain = 0
    other_plain = 0
    async for hotkey, raw in iter_commitment_of_raw(subtensor, netuid):
        decoded = decode_commitment_of_raw(raw)
        if decoded.kind == CommitmentKind.TIMELOCK_ENCRYPTED:
            timelock += 1
            continue
        if decoded.kind == CommitmentKind.PLAINTEXT and decoded.reveal_string:
            parsed = parse_model_commit(decoded.reveal_string, hotkey)
            if parsed and parsed.get("version") == "v6":
                v6_plain += 1
            else:
                other_plain += 1
    return {
        "subnet": netuid,
        "timelock_encrypted": timelock,
        "plaintext_v6": v6_plain,
        "plaintext_other": other_plain,
    }
