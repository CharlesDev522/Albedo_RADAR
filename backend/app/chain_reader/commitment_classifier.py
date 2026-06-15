"""Classify any CommitmentOf entry — v5, v4, json, TimelockEncrypted, other, none."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.chain_reader.commitment_decoder import (
    CommitmentKind,
    decode_commitment_of_raw,
    encrypted_payload_hash,
)


class CommitmentType(str, Enum):
    NONE = "none"
    V5 = "v5"
    V4 = "v4"
    JSON = "json"
    TIMELOCK_ENCRYPTED = "timelock_encrypted"
    BINARY = "binary"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedCommitment:
    commitment_type: CommitmentType
    commit_block: int
    deposit: int
    reveal_string: str | None
    detail: str | None
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


def _classify_plaintext(
    decoded: str,
    commit_block: int,
    deposit: int,
) -> ClassifiedCommitment:
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


def classify_commitment_raw(raw: dict[str, Any], hotkey: str = "") -> ClassifiedCommitment | None:
    """Classify a raw CommitmentOf record. TimelockEncrypted is parsed before plaintext."""
    decoded_of = decode_commitment_of_raw(raw)
    if decoded_of.kind == CommitmentKind.EMPTY:
        return None

    if decoded_of.kind == CommitmentKind.TIMELOCK_ENCRYPTED:
        assert decoded_of.encrypted_hex is not None and decoded_of.reveal_round is not None
        enc_hash = encrypted_payload_hash(decoded_of.encrypted_hex, decoded_of.reveal_round)
        return ClassifiedCommitment(
            commitment_type=CommitmentType.TIMELOCK_ENCRYPTED,
            commit_block=decoded_of.commit_block,
            deposit=decoded_of.deposit,
            reveal_string=None,
            detail=f"round:{decoded_of.reveal_round}",
            reveal_round=decoded_of.reveal_round,
            encrypted_hash=enc_hash,
            payload_hash=enc_hash,
        )

    if decoded_of.kind == CommitmentKind.BINARY:
        h = hashlib.sha256(str(decoded_of.raw_field_keys).encode()).hexdigest()
        fields = raw.get("info", {}).get("fields", [])
        if fields and isinstance(fields[0], dict):
            for _key, val in fields[0].items():
                if str(_key).startswith("Raw") and isinstance(val, str):
                    try:
                        h = hashlib.sha256(bytes.fromhex(val.removeprefix("0x"))).hexdigest()
                    except Exception:
                        pass
                    break
        return ClassifiedCommitment(
            commitment_type=CommitmentType.BINARY,
            commit_block=decoded_of.commit_block,
            deposit=decoded_of.deposit,
            reveal_string=None,
            detail=f"opaque:{h[:12]}",
            encrypted_hash=h,
            payload_hash=h,
        )

    if decoded_of.kind == CommitmentKind.PLAINTEXT and decoded_of.reveal_string:
        return _classify_plaintext(decoded_of.reveal_string, decoded_of.commit_block, decoded_of.deposit)

    return ClassifiedCommitment(
        commitment_type=CommitmentType.UNKNOWN,
        commit_block=decoded_of.commit_block,
        deposit=decoded_of.deposit,
        reveal_string=None,
        detail=str(decoded_of.raw_field_keys)[:120] or "unknown",
        payload_hash=_payload_hash(str(decoded_of.raw_field_keys)),
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
