"""Tests for human-readable Slack formatting."""

from app.notifications.kinds import SLACK_EMOJI
from app.notifications.slack_format import (
    build_slack_payload,
    hippius_repo_url,
    taostats_subnet_url,
)


def _full_text(payload: dict) -> str:
    return payload["blocks"][0]["text"]["text"]


def test_duel_one_link_uid_title():
    payload = build_slack_payload(
        kind="duel_new",
        title="[duel_new]",
        message="duel",
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
    text = _full_text(payload)
    assert text.count(SLACK_EMOJI["duel_new"]) == 1
    assert "*UID 176 started a duel on SN97*" in text
    assert "evernear/albedo-qwen3.6-35b-v9 (UID 176)" in text
    assert text.count("https://") == 1
    assert hippius_repo_url("evernear/albedo-qwen3.6-35b-v9") in text
    assert "huggingface.co" not in text
    assert taostats_subnet_url(97) not in text


def test_commit_updated_title():
    payload = build_slack_payload(
        kind="commit_updated",
        title="[commit_updated]",
        message="updated",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "uid": 166,
            "commit_block": 8520068,
        },
        subnet=97,
    )
    text = _full_text(payload)
    assert "*UID 166 updated commit for foremost/albedo-qwen3.6-35b-albedo-12*" in text
    assert "changed their on-chain model commitment" in text
    assert text.count("https://") == 1


def test_commit_new_title():
    payload = build_slack_payload(
        kind="commit_new",
        title="[commit_new]",
        message="new",
        detail={"repo": "cyantest/model", "uid": 12},
        subnet=97,
    )
    text = _full_text(payload)
    assert "*UID 12 committed cyantest/model*" in text


def test_king_defended_one_link():
    payload = build_slack_payload(
        kind="king_defended",
        title="[king_defended]",
        message="defended",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "uid": 166,
            "king_version": 42,
            "win_margin": -0.039,
            "score_challenger": 0.48,
            "score_king": 0.52,
        },
        subnet=97,
    )
    text = _full_text(payload)
    assert "*UID 166 lost the duel — king defended on SN97*" in text
    assert text.count("https://") == 1
    assert hippius_repo_url("foremost/albedo-qwen3.6-35b-albedo-12") in text


def test_reg_fee_links_taostats_only():
    payload = build_slack_payload(
        kind="reg_fee_low",
        title="[reg_fee_low]",
        message="fee",
        detail={"registration_burn_tao": 0.52, "threshold_tao": 0.75},
        subnet=97,
    )
    text = _full_text(payload)
    assert "*SN97 registration fee below 0.75 τ*" in text
    assert text.count("https://") == 1
    assert taostats_subnet_url(97) in text
