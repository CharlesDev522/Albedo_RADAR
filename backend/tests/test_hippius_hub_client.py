"""Tests for Hippius Hub API client."""

from app.integrations.hippius_hub_client import HippiusHubModel, _parse_model_row


def test_parse_model_row():
    row = {
        "project": "cyantest",
        "repo": "albedo-qwen3.6-35b-7777",
        "digest": "sha256:abc123",
        "primary_tag": "main",
        "indexed_at": "2026-06-29T11:48:29.740336Z",
        "file_count": 24,
        "total_size_bytes": 70234593907,
    }
    parsed = _parse_model_row(row)
    assert parsed is not None
    assert parsed.repo == "cyantest/albedo-qwen3.6-35b-7777"
    assert parsed.digest == "sha256:abc123"
    assert parsed.primary_tag == "main"
    assert parsed.indexed_at is not None


def test_parse_model_row_rejects_invalid():
    assert _parse_model_row({"project": "", "repo": "x"}) is None
    assert _parse_model_row({"project": "a", "repo": "b"}) is None
