"""Tests for Bittensor-accurate Slack formatting."""

from app.notifications.kinds import SLACK_EMOJI
from app.notifications.slack_format import (
    build_slack_payload,
    hippius_repo_url,
    taostats_subnet_url,
)


def _text(payload: dict) -> str:
    return payload["blocks"][0]["text"]["text"]


def test_commit_new_revealed_commitmentof():
    payload = build_slack_payload(
        kind="commit_new",
        title="[commit_new]",
        message="",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "uid": 166,
            "version": "v6",
            "commit_block": 8520068,
            "digest": "sha256:abc",
        },
        subnet=97,
    )
    text = _text(payload)
    assert "revealed v6 commitment" in text
    assert "CommitmentOf" in text
    assert "bought" not in text.lower()
    assert "updated commit" not in text.lower()


def test_commit_updated_changed_commitmentof():
    payload = build_slack_payload(
        kind="commit_updated",
        title="[commit_updated]",
        message="",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "uid": 166,
            "commit_block": 8520100,
            "digest": "sha256:def",
        },
        subnet=97,
    )
    text = _text(payload)
    assert "changed CommitmentOf" in text
    assert "changed their CommitmentOf" in text
    assert "updated commit for" not in text


def test_slot_published_pipe_not_bought():
    payload = build_slack_payload(
        kind="slot_new",
        title="[slot_new]",
        message="",
        detail={
            "uid": 42,
            "commitment_type": "v7",
            "commit_block": 8520068,
            "detail": "cyantest/albedo-qwen3-4b-test",
        },
        subnet=97,
    )
    text = _text(payload)
    assert "published v7 commitment" in text
    assert "no published commitment before" in text
    assert "bought" not in text.lower()
    assert "block slot" not in text.lower()


def test_duel_albedo_eval():
    payload = build_slack_payload(
        kind="duel_new",
        title="[duel_new]",
        message="",
        detail={
            "repo": "evernear/albedo-qwen3.6-35b-v9",
            "uid": 176,
            "state": "DISPATCHED",
            "sample_count": 128,
            "king_version": 42,
            "king_repo": "moon/albedo-qwen3.6-35b-well",
        },
        subnet=97,
    )
    text = _text(payload)
    assert "Albedo eval started" in text
    assert "Albedo evaluation duel" in text
    assert text.count(SLACK_EMOJI["duel_new"]) == 1
    assert text.count("https://") == 1
    assert hippius_repo_url("evernear/albedo-qwen3.6-35b-v9") in text


def test_reg_fee_registration_burn():
    payload = build_slack_payload(
        kind="reg_fee_low",
        title="[reg_fee_low]",
        message="",
        detail={"registration_burn_tao": 0.52, "threshold_tao": 0.75},
        subnet=97,
    )
    text = _text(payload)
    assert "registration burn" in text.lower()
    assert "register a new neuron UID" in text
    assert taostats_subnet_url(97) in text
