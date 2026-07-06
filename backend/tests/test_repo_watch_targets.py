"""Tests for repo watch target discovery."""

from app.processing.repo_watch_targets import (
    hub_watch_hotkey,
    is_hub_watch_hotkey,
    parse_hub_watch_hotkey,
    repo_from_hub_watch_hotkey,
)


def test_hub_watch_hotkey_roundtrip():
    repo = "miner/albedo-qwen3.6-35b-v1"
    hk = hub_watch_hotkey(repo)
    assert hk == "hub:miner/albedo-qwen3.6-35b-v1"
    assert is_hub_watch_hotkey(hk)
    assert repo_from_hub_watch_hotkey(hk) == repo
    assert not is_hub_watch_hotkey("5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY")


def test_hub_watch_hotkey_rejects_non_hub():
    assert repo_from_hub_watch_hotkey("5GrwvaEF") is None


def test_host_specific_hub_watch_hotkey():
    repo = "cyantest/albedo-qwen3.6-35b-7777"
    hk = hub_watch_hotkey(repo, "hippius")
    assert hk == "hub:hippius:cyantest/albedo-qwen3.6-35b-7777"
    parsed_repo, host = parse_hub_watch_hotkey(hk)
    assert parsed_repo == repo
    assert host == "hippius"
    hf = hub_watch_hotkey(repo, "huggingface")
    assert parse_hub_watch_hotkey(hf) == (repo, "huggingface")
