"""Tests for Hippius OCI registry helpers."""

from app.integrations.hippius_registry import (
    _parse_manifest,
    diff_manifest_files,
    digests_match,
    normalize_digest,
)


SAMPLE_MANIFEST = {
    "schemaVersion": 2,
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "layers": [
        {
            "digest": "sha256:abc",
            "size": 100,
            "annotations": {"org.opencontainers.image.title": "config.json"},
        },
        {
            "digest": "sha256:def",
            "size": 200,
            "annotations": {"org.opencontainers.image.title": "model.safetensors"},
        },
    ],
    "annotations": {
        "org.hippius.commit.message": "upload example/repo",
        "org.opencontainers.image.created": "2026-06-19T09:28:36.474715+00:00",
    },
}


def test_normalize_digest():
    assert normalize_digest("sha256:abc") == "sha256:abc"
    assert normalize_digest("a" * 64) == f"sha256:{'a' * 64}"
    assert normalize_digest("short") == "short"


def test_digests_match():
    assert digests_match("sha256:abc", "SHA256:ABC") is True
    assert digests_match("sha256:abc", "sha256:def") is False


def test_parse_manifest():
    parsed = _parse_manifest("owner/repo", "main", "sha256:manifest", SAMPLE_MANIFEST)
    assert parsed.repo == "owner/repo"
    assert parsed.revision == "main"
    assert parsed.manifest_digest == "sha256:manifest"
    assert parsed.commit_message == "upload example/repo"
    assert parsed.file_count == 2
    assert parsed.files[0].name == "config.json"


def test_diff_manifest_files():
    from app.integrations.hippius_registry import HippiusManifestFile

    prev = (HippiusManifestFile("config.json", "sha256:abc", 100),)
    curr = (
        HippiusManifestFile("config.json", "sha256:xyz", 100),
        HippiusManifestFile("new.json", "sha256:new", 50),
    )
    changes = diff_manifest_files(prev, curr)
    kinds = {c["change"] for c in changes}
    assert "modified" in kinds
    assert "added" in kinds
