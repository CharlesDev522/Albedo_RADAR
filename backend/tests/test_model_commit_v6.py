"""Tests for v6 model commitment parsing."""

from app.chain_reader.commitment_classifier import classify_commitment_raw
from app.chain_reader.commitment_scanner import parse_model_commit, parse_v6


def test_parse_v6_commit():
    data = "v6|owner/my-model|sha256:abc123deadbeef"
    parsed = parse_model_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["version"] == "v6"
    assert parsed["repo"] == "owner/my-model"
    assert parse_v6(data, "5Hotkey") is not None


def test_v5_not_detected():
    data = "v5|owner/my-model|sha256:abc123deadbeef"
    assert parse_model_commit(data, "5Hotkey") is None
    assert parse_v6(data, "5Hotkey") is None


def test_v4_not_detected():
    data = "v4|owner/my-model|sha256:abc123deadbeef"
    assert parse_model_commit(data, "5Hotkey") is None


def test_classify_v6_on_chain_shape():
    raw = {
        "block": 42,
        "deposit": 0,
        "info": {
            "fields": [
                {
                    "Raw120": (
                        "0x76367c6f776e65722f6d792d6d6f64656c7c7368613235363a6162633132336465616462656566"
                    )
                }
            ]
        },
    }
    classified = classify_commitment_raw(raw, "5Hotkey")
    assert classified is not None
    assert classified.commitment_type.value == "v6"
    assert classified.reveal_string.startswith("v6|")


def test_classify_v5_as_other():
    raw = {
        "block": 42,
        "deposit": 0,
        "info": {
            "fields": [
                {
                    "Raw120": (
                        "0x76357c6f776e65722f6d792d6d6f64656c7c7368613235363a6162633132336465616462656566"
                    )
                }
            ]
        },
    }
    classified = classify_commitment_raw(raw, "5Hotkey")
    assert classified is not None
    assert classified.commitment_type.value == "other"
