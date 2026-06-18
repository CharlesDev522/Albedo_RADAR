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


def test_sn97_ignores_json_and_v5_accepts_v6_v7():
    json_data = '{"model": "divinequest/m9n2", "revision": "cca9b0d"}'
    assert parse_subnet_model_commit(json_data, "5Hotkey", netuid=97) is None
    v5_data = "v5|owner/repo|sha256:abc123deadbeef"
    assert parse_subnet_model_commit(v5_data, "5Hotkey", netuid=97) is None
    v7_data = "v7|owner/repo|sha256:abc123deadbeef"
    parsed = parse_subnet_model_commit(v7_data, "5Hotkey", netuid=97)
    assert parsed is not None
    assert parsed["version"] == "v7"


def test_sn97_accepts_v6():
    data = "v6|owner/my-model|sha256:abc123deadbeef"
    parsed = parse_subnet_model_commit(data, "5Hotkey", netuid=97)
    assert parsed is not None
    assert parsed["version"] == "v6"


def test_parse_json_invalid():
    assert parse_json_model_commit("not json", "5Hotkey") is None
    assert parse_json_model_commit('{"model": "no-slash"}', "5Hotkey") is None


def test_parse_any_prefers_v6_over_json():
    data = "v6|owner/my-model|sha256:abc123deadbeef"
    parsed = parse_any_model_commit(data, "5Hotkey")
    assert parsed is not None
    assert parsed["version"] == "v6"
