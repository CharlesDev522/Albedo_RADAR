"""Tests for Hugging Face registry helpers."""

from app.integrations.huggingface_registry import _parse_revision

SAMPLE = {
    "sha": "abc123deadbeef",
    "lastModified": "2026-06-19T09:28:36.000Z",
    "siblings": [
        {"rfilename": "config.json", "size": 100, "oid": "oid1"},
        {"rfilename": "model.safetensors", "size": 200, "oid": "oid2"},
    ],
}


def test_parse_hf_revision():
    parsed = _parse_revision("org/model", "main", SAMPLE)
    assert parsed.repo == "org/model"
    assert parsed.revision == "main"
    assert parsed.commit_sha == "revision:abc123deadbeef"
    assert parsed.file_count == 2
