"""Decode Bittensor commitment storage — TimelockEncrypted first, then plaintext.

Two on-chain sources:
  - ``CommitmentOf`` — active commitment per hotkey (TimelockEncrypted lives here pre-reveal)
  - ``RevealedCommitments`` — historical reveals (only plaintext after timelock reveals)

Parsing order for ``CommitmentOf`` (must not skip encrypted hotkeys):
  1. Detect ``TimelockEncrypted`` on ``fields[0]`` via raw SCALE dict
  2. Else decode ``Raw*`` / metadata to a UTF-8 reveal string (v5, v4, json, …)

``RevealedCommitments`` entries are SCALE length-prefixed byte blobs; timelock ciphertext
never appears there until revealed, so plaintext decode is safe.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

TIMELOCK_KIND = "TimelockEncrypted"


class CommitmentKind(str, Enum):
    EMPTY = "empty"
    TIMELOCK_ENCRYPTED = "timelock_encrypted"
    PLAINTEXT = "plaintext"
    BINARY = "binary"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DecodedCommitmentOf:
    """Parsed ``CommitmentOf`` record — discriminated by ``kind``."""

    kind: CommitmentKind
    commit_block: int
    deposit: int
    reveal_string: str | None = None
    encrypted_hex: str | None = None
    reveal_round: int | None = None
    raw_field_keys: tuple[str, ...] = ()


def _field_kind_and_payload(field: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(field, dict):
        return None

    if TIMELOCK_KIND in field:
        payload = field[TIMELOCK_KIND]
        return TIMELOCK_KIND, payload if isinstance(payload, dict) else {}

    kind = field.get("__kind")
    if kind == TIMELOCK_KIND:
        return TIMELOCK_KIND, field

    for key in field:
        if "Timelock" in str(key):
            payload = field[key]
            return str(key), payload if isinstance(payload, dict) else {}

    return None


def parse_timelock_encrypted(field: Any) -> tuple[str, int] | None:
    """Return ``(encrypted_hex, reveal_round)`` or None if not TimelockEncrypted."""
    parsed = _field_kind_and_payload(field)
    if parsed is not None:
        kind, payload = parsed
        if TIMELOCK_KIND in kind:
            encrypted = payload.get("encrypted") or payload.get("Encrypted")
            reveal_raw = (
                payload.get("reveal_round")
                or payload.get("revealRound")
                or payload.get("RevealRound")
            )
            if encrypted:
                try:
                    reveal_round = int(reveal_raw) if reveal_raw is not None else 0
                except (TypeError, ValueError):
                    reveal_round = 0
                return str(encrypted), reveal_round

    if isinstance(field, dict):
        encrypted = field.get("encrypted") or field.get("Encrypted")
        reveal_raw = field.get("reveal_round") or field.get("revealRound") or field.get("RevealRound")
        if encrypted and str(encrypted).startswith("0x"):
            try:
                reveal_round = int(reveal_raw) if reveal_raw is not None else 0
            except (TypeError, ValueError):
                reveal_round = 0
            return str(encrypted), reveal_round

    return None


def _raw_field_bytes(field: Any) -> bytes | None:
    if not isinstance(field, dict):
        return None
    for key, val in field.items():
        if not str(key).startswith("Raw") or not isinstance(val, str):
            continue
        try:
            return bytes.fromhex(val.removeprefix("0x"))
        except Exception:
            return None
    return None


def _is_mostly_binary(data: bytes) -> bool:
    if not data:
        return True
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(data) < 0.75


def decode_revealed_payload(text: str) -> str:
    """Decode one ``RevealedCommitments`` payload (hex or latin-1 + SCALE compact length)."""
    if text.startswith(("0x", "0X")):
        raw = bytes.fromhex(text[2:])
    else:
        raw = text.encode("latin-1")
    if not raw:
        return ""
    mode = raw[0] & 0b11
    offset = 1 if mode == 0 else 2 if mode == 1 else 4
    return raw[offset:].decode("utf-8", errors="ignore")


def decode_commitment_of_raw(raw: dict[str, Any]) -> DecodedCommitmentOf:
    """Parse raw ``CommitmentOf`` — TimelockEncrypted checked before any plaintext decode."""
    commit_block = int(raw.get("block") or 0)
    deposit = int(raw.get("deposit") or 0)
    fields = raw.get("info", {}).get("fields", [])
    if not fields:
        return DecodedCommitmentOf(kind=CommitmentKind.EMPTY, commit_block=commit_block, deposit=deposit)

    f0 = fields[0]
    field_keys = tuple(str(k) for k in f0.keys()) if isinstance(f0, dict) else ()

    timelock = parse_timelock_encrypted(f0)
    if timelock is not None:
        encrypted_hex, reveal_round = timelock
        return DecodedCommitmentOf(
            kind=CommitmentKind.TIMELOCK_ENCRYPTED,
            commit_block=commit_block,
            deposit=deposit,
            encrypted_hex=encrypted_hex,
            reveal_round=reveal_round,
            raw_field_keys=field_keys,
        )

    reveal_string: str | None = None
    try:
        from bittensor.core.chain_data.utils import decode_metadata

        decoded = decode_metadata(raw)
        if decoded and decoded.strip():
            reveal_string = decoded.strip()
    except Exception:
        blob = _raw_field_bytes(f0)
        if blob is not None:
            if _is_mostly_binary(blob):
                return DecodedCommitmentOf(
                    kind=CommitmentKind.BINARY,
                    commit_block=commit_block,
                    deposit=deposit,
                    raw_field_keys=field_keys,
                )
            text = blob.decode("utf-8", errors="ignore").strip()
            if text:
                reveal_string = text

    if reveal_string:
        return DecodedCommitmentOf(
            kind=CommitmentKind.PLAINTEXT,
            commit_block=commit_block,
            deposit=deposit,
            reveal_string=reveal_string,
            raw_field_keys=field_keys,
        )

    return DecodedCommitmentOf(
        kind=CommitmentKind.UNKNOWN,
        commit_block=commit_block,
        deposit=deposit,
        raw_field_keys=field_keys,
    )


def encrypted_payload_hash(encrypted_hex: str, reveal_round: int) -> str:
    return hashlib.sha256(f"{encrypted_hex}|{reveal_round}".encode()).hexdigest()


async def iter_commitment_of_raw(subtensor: Any, netuid: int) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield ``(hotkey, raw CommitmentOf record)`` without assuming plaintext."""
    query = await subtensor.query_map(
        module="Commitments",
        name="CommitmentOf",
        params=[netuid],
    )
    async for hotkey, value in query:
        raw = getattr(value, "value", value)
        if raw is not None:
            yield str(hotkey), raw


async def iter_active_plaintext(subtensor: Any, netuid: int) -> dict[str, str]:
    """Active ``CommitmentOf`` reveal strings — skips TimelockEncrypted hotkeys."""
    out: dict[str, str] = {}
    async for hotkey, raw in iter_commitment_of_raw(subtensor, netuid):
        decoded = decode_commitment_of_raw(raw)
        if decoded.kind == CommitmentKind.PLAINTEXT and decoded.reveal_string:
            out[hotkey] = decoded.reveal_string
    return out
