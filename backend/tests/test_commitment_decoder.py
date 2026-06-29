"""Unit tests for commitment decode pipeline (timelock before plaintext)."""

from app.chain_reader.commitment_classifier import classify_commitment_raw
from app.chain_reader.commitment_decoder import (
    CommitmentKind,
    decode_commitment_of_raw,
    decode_revealed_payload,
    parse_timelock_encrypted,
)

USER_TIMELOCK_FIELD = {
    "__kind": "TimelockEncrypted",
    "encrypted": "0xb7b6452b97ff46810e2ca2807395cc58a3a4c47a67138422047c677fd6992713",
    "revealRound": "29468415",
}

V4_RAW_FIELD = {
    "Raw113": (
        "0x76347c6e65776a616e612f616c6265646f2d7177656e332d34622d6b696e6772657374322d30363037"
        "7c7368613235363a616263"
    )
}


def test_parse_timelock_explorer_shape():
    result = parse_timelock_encrypted(USER_TIMELOCK_FIELD)
    assert result is not None
    assert result[1] == 29468415
    assert result[0].startswith("0x")


def test_decode_commitment_of_timelock_first():
    raw = {
        "block": 100,
        "deposit": 0,
        "info": {"fields": [USER_TIMELOCK_FIELD]},
    }
    decoded = decode_commitment_of_raw(raw)
    assert decoded.kind == CommitmentKind.TIMELOCK_ENCRYPTED
    assert decoded.reveal_round == 29468415
    assert decoded.reveal_string is None


def test_classify_timelock_encrypted():
    raw = {
        "block": 100,
        "deposit": 0,
        "info": {"fields": [USER_TIMELOCK_FIELD]},
    }
    classified = classify_commitment_raw(raw, "5Hotkey")
    assert classified is not None
    assert classified.commitment_type.value == "timelock_encrypted"
    assert classified.reveal_round == 29468415


def test_decode_commitment_of_v4_plaintext():
    raw = {
        "block": 200,
        "deposit": 0,
        "info": {"fields": [V4_RAW_FIELD]},
    }
    decoded = decode_commitment_of_raw(raw)
    assert decoded.kind == CommitmentKind.PLAINTEXT
    assert decoded.reveal_string is not None
    assert decoded.reveal_string.startswith("v4|")


def test_decode_revealed_payload_skips_scale_prefix():
    # compact length mode 0: 1-byte prefix
    text = "v5|owner/repo|sha256:abc"
    raw = bytes([len(text)]) + text.encode()
    assert decode_revealed_payload("0x" + raw.hex()) == text
