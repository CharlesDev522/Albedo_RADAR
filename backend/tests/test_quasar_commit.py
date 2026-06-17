"""Tests for Quasar JSON commitment parsing."""

from app.chain_reader.commitment_scanner import (
    parse_any_model_commit,
    parse_quasar_commit,
)


def test_parse_quasar_json_commit():
    data = '{"model": "user/quasar-model", "revision": "abc123deadbeef"}'
    parsed = parse_quasar_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["version"] == "quasar"
    assert parsed["repo"] == "user/quasar-model"
    assert parsed["digest"] == "revision:abc123deadbeef"
    assert parsed["revision"] == "abc123deadbeef"


def test_parse_quasar_hf_repo_alias():
    data = '{"hf_repo": "org/model", "revision": "deadbeef"}'
    parsed = parse_quasar_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["repo"] == "org/model"


def test_parse_quasar_invalid_json():
    assert parse_quasar_commit("not json", "5Hotkey") is None
    assert parse_quasar_commit('{"model": "no-slash"}', "5Hotkey") is None


def test_parse_any_prefers_v6_over_json():
    data = "v6|owner/my-model|sha256:abc123deadbeef"
    parsed = parse_any_model_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["version"] == "v6"
