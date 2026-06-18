"""Subnet-specific commit parsing rules."""

from app.chain_reader.commitment_scanner import parse_subnet_model_commit
from app.chain_reader.subnet_commit_rules import (
    ALBEDO_PIPE_VERSIONS,
    is_published_slot_type,
    model_versions_for_subnet,
    normalize_stored_version,
    is_albedo_pipe_history_row,
    pipe_version_from_reveal,
)


def test_sn97_model_versions_v6_v7():
    assert model_versions_for_subnet(97) == frozenset({"v6", "v7"})


def test_sn24_model_versions_json():
    assert model_versions_for_subnet(24) == frozenset({"quasar", "json"})


def test_sn97_ignores_v5():
    data = "v5|owner/repo|sha256:abc123deadbeef"
    assert parse_subnet_model_commit(data, "5Hotkey", netuid=97) is None


def test_sn97_accepts_v6():
    data = "v6|owner/repo|sha256:abc123deadbeef"
    parsed = parse_subnet_model_commit(data, "5Hotkey", netuid=97)
    assert parsed is not None
    assert parsed["version"] == "v6"


def test_sn97_accepts_v7():
    data = "v7|owner/repo|sha256:deadbeefcafebabe"
    parsed = parse_subnet_model_commit(data, "5Hotkey", netuid=97)
    assert parsed is not None
    assert parsed["version"] == "v7"


def test_sn97_ignores_legacy_json():
    data = '{"model": "divinequest/m9n2", "revision": "cca9b0d"}'
    assert parse_subnet_model_commit(data, "5Hotkey", netuid=97) is None


def test_sn24_accepts_json():
    data = '{"model": "user/quasar-model", "revision": "abc123"}'
    parsed = parse_subnet_model_commit(data, "5Hotkey", netuid=24)
    assert parsed is not None
    assert parsed["version"] == "json"


def test_normalize_sn97_accepts_v6_v7():
    assert normalize_stored_version("v5", 97) is None
    assert normalize_stored_version("json", 97) is None
    assert normalize_stored_version("v6", 97) == "v6"
    assert normalize_stored_version("v7", 97) == "v7"


def test_sn97_published_slot_v6_v7():
    assert is_published_slot_type("v6", 97) is True
    assert is_published_slot_type("v7", 97) is True
    assert is_published_slot_type("v5", 97) is False
    assert is_published_slot_type("json", 97) is False


def test_albedo_pipe_history_row():
    assert is_albedo_pipe_history_row("v6|o/r|sha256:abc", {"version": "v6"})
    assert is_albedo_pipe_history_row("v7|o/r|sha256:abc", {"version": "v7"})
    assert not is_albedo_pipe_history_row("v5|o/r|sha256:abc", {"version": "v5"})
    assert pipe_version_from_reveal("v7|owner/repo|sha256:x") == "v7"
