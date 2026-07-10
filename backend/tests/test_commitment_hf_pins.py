"""Tests for v7 HF pin parsing on chain commits."""

from app.chain_reader.commitment_scanner import parse_pipe_commit
from app.chain_reader.subnet_commit_rules import ALBEDO_PIPE_VERSIONS


_HF_SHA40 = "a" * 40


def test_parse_v7_accepts_hf_git_sha():
    data = f"v7|owner/my-model|{_HF_SHA40}"
    parsed = parse_pipe_commit(data, "5Hotkey", ALBEDO_PIPE_VERSIONS)
    assert parsed is not None
    assert parsed["version"] == "v7"
    assert parsed["repo"] == "owner/my-model"
    assert parsed["digest"] == _HF_SHA40


def test_parse_v6_still_requires_sha256():
    data = "v6|owner/my-model|abc123def4567890abcd1234567890abcd1234"
    assert parse_pipe_commit(data, "5Hotkey", ALBEDO_PIPE_VERSIONS) is None

    hippius = "v6|owner/my-model|sha256:" + "a" * 64
    parsed = parse_pipe_commit(hippius, "5Hotkey", ALBEDO_PIPE_VERSIONS)
    assert parsed is not None
    assert parsed["digest"].startswith("sha256:")
