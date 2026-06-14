"""Detect TimelockEncrypted commitments on CommitmentOf (pre-reveal, ciphertext on chain)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from app.chain_reader.commitment_scanner import _neuron_index, parse_v5

logger = logging.getLogger(__name__)

TIMELOCK_KIND = "TimelockEncrypted"


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


def _field_kind_and_payload(field: Any) -> tuple[str, dict[str, Any]] | None:
    """Parse the first CommitmentOf metadata field into (kind, payload)."""
    if not isinstance(field, dict):
        return None

    # SCALE decode: {"TimelockEncrypted": {"encrypted": "0x...", "reveal_round": N}}
    if TIMELOCK_KIND in field:
        payload = field[TIMELOCK_KIND]
        return TIMELOCK_KIND, payload if isinstance(payload, dict) else {}

    # Some explorers decode as {"__kind": "TimelockEncrypted", "encrypted": ..., "revealRound": ...}
    kind = field.get("__kind")
    if kind == TIMELOCK_KIND:
        return TIMELOCK_KIND, field

    for key in field:
        if "Timelock" in str(key):
            payload = field[key]
            return str(key), payload if isinstance(payload, dict) else {}

    return None


def parse_timelock_encrypted(field: Any) -> tuple[str, int] | None:
    """Return (encrypted_hex, reveal_round) for a TimelockEncrypted field, else None."""
    parsed = _field_kind_and_payload(field)
    if parsed is None:
        return None
    kind, payload = parsed
    if TIMELOCK_KIND not in kind:
        return None

    encrypted = payload.get("encrypted") or payload.get("Encrypted")
    if not encrypted:
        return None

    reveal_raw = payload.get("reveal_round") or payload.get("revealRound") or payload.get("RevealRound")
    try:
        reveal_round = int(reveal_raw) if reveal_raw is not None else 0
    except (TypeError, ValueError):
        reveal_round = 0

    return str(encrypted), reveal_round


def encrypted_payload_hash(encrypted_hex: str, reveal_round: int) -> str:
    canonical = f"{encrypted_hex}|{reveal_round}"
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _iter_commitment_of_raw(subtensor: Any, netuid: int):
    """Yield (hotkey, raw CommitmentOf record) without plaintext decoding."""
    query = await subtensor.query_map(
        module="Commitments",
        name="CommitmentOf",
        params=[netuid],
    )
    async for hotkey, value in query:
        raw = getattr(value, "value", value)
        if raw is not None:
            yield str(hotkey), raw


async def scan_encrypted_commitments(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]] | None = None,
) -> list[EncryptedCommit]:
    """Return active TimelockEncrypted commitments (excludes revealed v5/v4 plaintext)."""
    if neurons is None:
        neurons = await _neuron_index(subtensor, netuid)

    commits: list[EncryptedCommit] = []

    async for hotkey, raw in _iter_commitment_of_raw(subtensor, netuid):
        fields = raw.get("info", {}).get("fields", [])
        if not fields:
            continue

        timelock = parse_timelock_encrypted(fields[0])
        if timelock is None:
            continue

        encrypted_hex, reveal_round = timelock
        commit_block = int(raw.get("block") or 0)
        deposit = int(raw.get("deposit") or 0)

        neuron = neurons.get(hotkey)
        uid = neuron["uid"] if neuron else None
        coldkey = neuron["coldkey"] if neuron else None
        reg_block = neuron["registered_at_block"] if neuron else None

        if uid is None:
            logger.info("encrypted commit for hotkey without uid mapping: %s", hotkey)

        commits.append(
            EncryptedCommit(
                netuid=netuid,
                block_number=commit_block,
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                registered_at_block=reg_block,
                deposit=deposit,
                reveal_round=reveal_round,
                encrypted_hex=encrypted_hex,
                payload_hash=encrypted_payload_hash(encrypted_hex, reveal_round),
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
    v5_plain = 0
    other_plain = 0
    async for hotkey, raw in _iter_commitment_of_raw(subtensor, netuid):
        fields = raw.get("info", {}).get("fields", [])
        if not fields:
            continue
        if parse_timelock_encrypted(fields[0]) is not None:
            timelock += 1
            continue
        f0 = fields[0]
        if isinstance(f0, dict):
            for _key, val in f0.items():
                if str(_key).startswith("Raw") and isinstance(val, str):
                    try:
                        text = bytes.fromhex(val.removeprefix("0x")).decode("utf-8", errors="ignore")
                    except Exception:
                        text = ""
                    if parse_v5(text, hotkey):
                        v5_plain += 1
                    elif text:
                        other_plain += 1
                    break
    return {
        "subnet": netuid,
        "timelock_encrypted": timelock,
        "plaintext_v5": v5_plain,
        "plaintext_other": other_plain,
    }
