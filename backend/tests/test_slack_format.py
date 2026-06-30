"""Tests for human-readable Slack formatting."""

from app.notifications.kinds import SLACK_EMOJI
from app.notifications.slack_format import (
    build_slack_payload,
    hippius_repo_url,
    huggingface_repo_url,
    taostats_subnet_url,
)


def _full_text(payload: dict) -> str:
    return payload["blocks"][0]["text"]["text"]


def test_duel_prose_with_full_urls():
    payload = build_slack_payload(
        kind="duel_new",
        title="[duel_new] evernear/albedo-qwen3.6-35b-v9",
        message="SN97 new duel started",
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
    assert "New duel started on Subnet 97" in text
    assert "evernear/albedo-qwen3.6-35b-v9 (UID 176)" in text
    assert "moon/albedo-qwen3.6-35b-well at king version 42" in text
    assert "status is DISPATCHED" in text
    assert "128 samples are queued" in text
    assert hippius_repo_url("evernear/albedo-qwen3.6-35b-v9") in text
    assert huggingface_repo_url("evernear/albedo-qwen3.6-35b-v9") in text
    assert hippius_repo_url("moon/albedo-qwen3.6-35b-well") in text
    assert taostats_subnet_url(97) in text
    assert "Useful links:" in text
    assert "fields" not in str(payload["blocks"])


def test_king_defended_prose():
    payload = build_slack_payload(
        kind="king_defended",
        title="[king_defended] foremost/albedo",
        message="king defended",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "king_version": 42,
            "king_repo": "moon/albedo-qwen3.6-35b-well",
            "win_margin": -0.039,
            "score_challenger": 0.48,
            "score_king": 0.52,
            "uid": 166,
        },
        subnet=97,
    )
    text = _full_text(payload)
    assert "The king defended the crown on Subnet 97" in text
    assert "foremost/albedo-qwen3.6-35b-albedo-12 (UID 166)" in text
    assert "did not take the crown" in text
    assert "challenger scored 0.480" in text
    assert "king scored 0.520" in text
    assert "king won by a margin of 0.039" in text


def test_crown_won_prose():
    payload = build_slack_payload(
        kind="crown_won",
        title="[crown_won] org/new-king",
        message="crowned",
        detail={
            "repo": "org/new-king",
            "king_version": 2,
            "defeated_king_version": 1,
            "win_margin": 0.2,
            "score_challenger": 0.6,
            "score_king": 0.4,
            "uid": 10,
        },
        subnet=97,
    )
    text = _full_text(payload)
    assert "A new king was crowned on Subnet 97" in text
    assert "org/new-king (UID 10)" in text
    assert "version 2, replacing king version 1" in text
    assert "challenger won by a margin of +0.200" in text


def test_reg_fee_friendly_copy():
    payload = build_slack_payload(
        kind="reg_fee_low",
        title="[reg_fee_low]",
        message="below threshold",
        detail={
            "registration_burn_tao": 0.52,
            "threshold_tao": 0.75,
            "alpha_price_tao": 0.03,
        },
        subnet=97,
    )
    text = _full_text(payload)
    assert "Registration fee alert on Subnet 97" in text
    assert "0.5200 τ" in text
    assert "0.75 τ alert threshold" in text
    assert "good time to register" in text
    assert taostats_subnet_url(97) in text


def test_commit_new_reads_as_sentence():
    payload = build_slack_payload(
        kind="commit_new",
        title="[commit_new]",
        message="commit",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "uid": 166,
            "commit_block": 8520068,
            "digest": "sha256:c5b1d55bc2eec6969952b6b74c18499b432f46186293e2b76d5e4bc97a393ead",
        },
        subnet=97,
    )
    text = _full_text(payload)
    assert "published a new on-chain model commitment at block 8520068" in text
    assert "Commit digest:" in text
