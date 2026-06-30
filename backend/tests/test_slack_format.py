"""Tests for compact Slack block formatting."""

import re

from app.notifications.kinds import SLACK_EMOJI
from app.notifications.slack_format import build_slack_payload, hippius_repo_url


def _emoji_count(text: str, emoji: str) -> int:
    return text.count(emoji)


def test_build_slack_payload_duel_single_emoji_structured():
    payload = build_slack_payload(
        kind="duel_new",
        title="[duel_new] evernear/albedo-qwen3.6-35b-v9",
        message="SN97 new duel started — vs king v42",
        detail={
            "repo": "evernear/albedo-qwen3.6-35b-v9",
            "uid": 176,
            "state": "DISPATCHED",
            "sample_count": 128,
            "king_version": 42,
            "king_repo": "moon/albedo-qwen3.6-35b-well",
            "eval_run_id": "2e3516d1-7830-4cf2-a2c3-43202e8beefd",
        },
        subnet=97,
    )
    blocks = payload["blocks"]
    assert blocks[0]["type"] == "section"
    assert "header" not in {b["type"] for b in blocks}
    assert "fields" not in str(blocks)
    text = blocks[0]["text"]["text"]
    emoji = SLACK_EMOJI["duel_new"]
    assert _emoji_count(text, emoji) == 1
    assert "*Duel Started*" in text
    assert "*Challenger*" in text
    assert "`evernear/albedo-qwen3.6-35b-v9`" in text
    assert "*King*" in text and "v42" in text
    assert "`moon/albedo-qwen3.6-35b-well`" in text
    assert "UID 176" in text
    assert "DISPATCHED" in text
    assert "128 samples" in text
    context = blocks[-1]["elements"][0]["text"]
    assert hippius_repo_url("evernear/albedo-qwen3.6-35b-v9") in context


def test_build_slack_payload_king_defended_single_emoji():
    payload = build_slack_payload(
        kind="king_defended",
        title="[king_defended] foremost/albedo-qwen3.6-35b-albedo-12",
        message="SN97 duel finished — king defended",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "king_version": 42,
            "king_repo": "moon/albedo-qwen3.6-35b-well",
            "win_margin": 0.039,
            "score_challenger": 0.48,
            "score_king": 0.52,
            "uid": 166,
            "eval_run_id": "85c6f11f-7830-4cf2-a2c3-43202e8beefd",
        },
        subnet=97,
    )
    text = payload["blocks"][0]["text"]["text"]
    emoji = SLACK_EMOJI["king_defended"]
    assert _emoji_count(text, emoji) == 1
    assert "*King Defended*" in text
    assert "`foremost/albedo-qwen3.6-35b-albedo-12`" in text
    assert "Margin +0.039" in text
    assert "Scores 0.480 vs 0.520" in text
    assert "UID 166" in text


def test_build_slack_payload_crown_won_scores():
    payload = build_slack_payload(
        kind="crown_won",
        title="[crown_won] org/new-king",
        message="SN97 crowned king v2 (defeated v1)",
        detail={
            "repo": "org/new-king",
            "king_version": 2,
            "defeated_king_version": 1,
            "win_margin": 0.2,
            "score_challenger": 0.6,
            "score_king": 0.4,
            "uid": 10,
            "eval_run_id": "r1",
        },
        subnet=97,
    )
    text = payload["blocks"][0]["text"]["text"]
    assert _emoji_count(text, SLACK_EMOJI["crown_won"]) == 1
    assert "*New King*" in text
    assert "*Champion*" in text
    assert "`org/new-king`" in text
    assert "v2" in text and "v1" in text
    assert "Margin +0.200" in text
    assert "0.600 vs 0.400" in text


def test_build_slack_payload_reg_fee_tier_emoji():
    payload = build_slack_payload(
        kind="reg_fee_low",
        title="[reg_fee_low] SN97 · below 0.75 τ",
        message="Registration burn crossed below tier",
        detail={"registration_burn_tao": 0.52, "threshold_tao": 0.75},
        subnet=97,
    )
    text = payload["blocks"][0]["text"]["text"]
    assert ":money_with_wings:" in text
    assert text.count(":money_with_wings:") == 1
    assert "*Reg Fee Drop*" in text
    assert "0.52" in text
    assert "0.75" in text


def test_build_slack_payload_commit_compact():
    payload = build_slack_payload(
        kind="commit_new",
        title="[commit_new] uid 166 — foremost/albedo-qwen3.6-35b-albedo-12",
        message="SN97 new v6 commit at block 8520068",
        detail={
            "repo": "foremost/albedo-qwen3.6-35b-albedo-12",
            "uid": 166,
            "commit_block": 8520068,
            "digest": "sha256:c5b1d55bc2eec6969952b6b74c18499b432f46186293e2b76d5e4bc97a393ead",
        },
        subnet=97,
    )
    text = payload["blocks"][0]["text"]["text"]
    assert "UID 166" in text
    assert "foremost/albedo" in payload["text"]
    assert not re.search(r"UID\s*\n\s*166", text)  # no broken field grid
