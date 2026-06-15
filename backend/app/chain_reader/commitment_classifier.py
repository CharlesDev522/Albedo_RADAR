"""Classify any CommitmentOf entry — v5, v4, json, TimelockEncrypted, other, none."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from bittensor.core.chain_data.utils import decode_metadata

from app.chain_reader.encrypted_commitment_scanner import parse_timelock_encrypted


class CommitmentType(str, Enum):
    NONE = "none"
    V5 = "v5"
    V4 = "v4"
    JSON = "json"
    TIMELOCK_ENCRYPTED = "timelock_encrypted"
    BINARY = "binary"  # non-printable Raw bytes (opaque / ciphertext-like)
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedCommitment:
    commitment_type: CommitmentType
    commit_block: int
    deposit: int
    reveal_string: str | None
    detail: str | None  # repo, json preview, cipher hash prefix, etc.
    reveal_round: int | None = None
    encrypted_hash: str | None = None
    payload_hash: str | None = None


def _payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _extract_repo(text: str) -> str | None:
    if "|" in text:
        parts = text.split("|")
        if len(parts) >= 2 and "/" in parts[1]:
            return parts[1]
    return None


def _raw_payload_text(f0: Any) -> str | None:
    if not isinstance(f0, dict):
        return None
    for key, val in f0.items():
        if str(key).startswith("Raw") and isinstance(val, str):
            try:
                return bytes.fromhex(val.removeprefix("0x")).decode("utf-8", errors="ignore")
            except Exception:
                return None
    return None


def _is_mostly_binary(data: bytes) -> bool:
    if not data:
        return True
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(data) < 0.75


def classify_commitment_raw(raw: dict[str, Any], hotkey: str = "") -> ClassifiedCommitment | None:
    """Classify a raw CommitmentOf record. Returns None if empty."""
    fields = raw.get("info", {}).get("fields", [])
    if not fields:
        return None

    commit_block = int(raw.get("block") or 0)
    deposit = int(raw.get("deposit") or 0)
    f0 = fields[0]

    timelock = parse_timelock_encrypted(f0)
    if timelock is not None:
        encrypted_hex, reveal_round = timelock
        enc_hash = hashlib.sha256(f"{encrypted_hex}|{reveal_round}".encode()).hexdigest()
        return ClassifiedCommitment(
            commitment_type=CommitmentType.TIMELOCK_ENCRYPTED,
            commit_block=commit_block,
            deposit=deposit,
            reveal_string=None,
            detail=f"round:{reveal_round}",
            reveal_round=reveal_round,
            encrypted_hash=enc_hash,
            payload_hash=enc_hash,
        )

    try:
        decoded = decode_metadata(raw)
    except Exception:
        # TimelockEncrypted and other dict payloads make decode_metadata fail
        raw_text = _raw_payload_text(f0)
        if raw_text and raw_text.startswith(("v5|", "v4|", "{")):
            decoded = raw_text
        else:
            timelock = parse_timelock_encrypted(f0)
            if timelock is not None:
                encrypted_hex, reveal_round = timelock
                enc_hash = hashlib.sha256(f"{encrypted_hex}|{reveal_round}".encode()).hexdigest()
                return ClassifiedCommitment(
                    commitment_type=CommitmentType.TIMELOCK_ENCRYPTED,
                    commit_block=commit_block,
                    deposit=deposit,
                    reveal_string=None,
                    detail=f"round:{reveal_round}",
                    reveal_round=reveal_round,
                    encrypted_hash=enc_hash,
                    payload_hash=enc_hash,
                )
            if isinstance(f0, dict):
                for key, val in f0.items():
                    if str(key).startswith("Raw") and isinstance(val, str):
                        try:
                            blob = bytes.fromhex(val.removeprefix("0x"))
                            if _is_mostly_binary(blob):
                                h = hashlib.sha256(blob).hexdigest()
                                return ClassifiedCommitment(
                                    commitment_type=CommitmentType.BINARY,
                                    commit_block=commit_block,
                                    deposit=deposit,
                                    reveal_string=None,
                                    detail=f"opaque:{h[:12]}",
                                    encrypted_hash=h,
                                    payload_hash=h,
                                )
                        except Exception:
                            pass
            return ClassifiedCommitment(
                commitment_type=CommitmentType.UNKNOWN,
                commit_block=commit_block,
                deposit=deposit,
                reveal_string=None,
                detail=str(list(f0.keys()) if isinstance(f0, dict) else f0)[:120],
                payload_hash=_payload_hash(str(f0)),
            )

    if not decoded or not decoded.strip():
        return ClassifiedCommitment(
            commitment_type=CommitmentType.UNKNOWN,
            commit_block=commit_block,
            deposit=deposit,
            reveal_string=None,
            detail="empty decode",
            payload_hash=_payload_hash("empty"),
        )

    if decoded.startswith("v5|"):
        repo = _extract_repo(decoded)
        return ClassifiedCommitment(
            commitment_type=CommitmentType.V5,
            commit_block=commit_block,
            deposit=deposit,
            reveal_string=decoded,
            detail=repo,
            payload_hash=_payload_hash(decoded),
        )

    if decoded.startswith("v4|"):
        repo = _extract_repo(decoded)
        return ClassifiedCommitment(
            commitment_type=CommitmentType.V4,
            commit_block=commit_block,
            deposit=deposit,
            reveal_string=decoded,
            detail=repo,
            payload_hash=_payload_hash(decoded),
        )

    if decoded.startswith("{"):
        preview = decoded[:80]
        try:
            obj = json.loads(decoded)
            detail = obj.get("model") or obj.get("hf_repo_id") or preview
        except json.JSONDecodeError:
            detail = preview
        return ClassifiedCommitment(
            commitment_type=CommitmentType.JSON,
            commit_block=commit_block,
            deposit=deposit,
            reveal_string=decoded,
            detail=str(detail)[:120],
            payload_hash=_payload_hash(decoded),
        )

    return ClassifiedCommitment(
        commitment_type=CommitmentType.OTHER,
        commit_block=commit_block,
        deposit=deposit,
        reveal_string=decoded,
        detail=decoded[:120],
        payload_hash=_payload_hash(decoded),
    )


def commitment_type_label(ct: CommitmentType) -> str:
    return {
        CommitmentType.NONE: "no commit",
        CommitmentType.V5: "v5",
        CommitmentType.V4: "v4",
        CommitmentType.JSON: "json",
        CommitmentType.TIMELOCK_ENCRYPTED: "encrypted",
        CommitmentType.BINARY: "binary",
        CommitmentType.OTHER: "other",
        CommitmentType.UNKNOWN: "unknown",
    }[ct]
