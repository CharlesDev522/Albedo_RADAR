"""Tests for JSON / pipe model commitment parsing."""

from app.chain_reader.commitment_scanner import (
    JSON_MODEL_VERSION,
    parse_any_model_commit,
    parse_json_model_commit,
    parse_subnet_model_commit,
)


def test_parse_json_model_commit():
    data = '{"model": "user/quasar-model", "revision": "abc123deadbeef"}'
    parsed = parse_json_model_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["version"] == JSON_MODEL_VERSION
    assert parsed["repo"] == "user/quasar-model"
    assert parsed["digest"] == "revision:abc123deadbeef"
    assert parsed["revision"] == "abc123deadbeef"


def test_parse_json_hf_repo_alias():
    data = '{"hf_repo": "org/model", "revision": "deadbeef"}'
    parsed = parse_json_model_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["repo"] == "org/model"
    assert parsed["version"] == "json"


def test_sn97_json_not_labeled_quasar():
    data = '{"model": "divinequest/m9n2", "revision": "cca9b0d216cd9c838b1f8ac7be5fd7bb9d4c2be6"}'
    parsed = parse_subnet_model_commit(data, "5Hotkey", netuid=97)
    assert parsed is not None
    assert parsed["version"] == "json"


def test_parse_json_invalid():
    assert parse_json_model_commit("not json", "5Hotkey") is None
    assert parse_json_model_commit('{"model": "no-slash"}', "5Hotkey") is None


def test_parse_any_prefers_v6_over_json():
    data = "v6|owner/my-model|sha256:abc123deadbeef"
    parsed = parse_any_model_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["version"] == "v6"
