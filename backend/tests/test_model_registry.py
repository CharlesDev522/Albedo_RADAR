"""Tests for unified model registry routing."""

from app.integrations.model_registry import infer_repo_host, remote_digests_match


def test_infer_repo_host():
    assert infer_repo_host("sha256:abc") == "hippius"
    assert infer_repo_host("revision:deadbeef") == "huggingface"
    assert infer_repo_host("hf:deadbeef") == "huggingface"


def test_remote_digests_match_revision():
    assert remote_digests_match("revision:abc123", "revision:abc123") is True
    assert remote_digests_match("revision:abc", "revision:def") is False


def test_remote_digests_match_sha256():
    assert remote_digests_match("sha256:abc", "sha256:abc") is True
