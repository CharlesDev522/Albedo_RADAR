"""Tests for compact Slack block formatting."""

from app.notifications.slack_format import build_slack_payload, hippius_repo_url


def test_build_slack_payload_duel_clean_section():
    payload = build_slack_payload(
        kind="duel_new",
        title="[duel_new] k/albedo-qwen3.6-35b-k03",
        message="SN97 new duel started — vs king v42",
        detail={
            "repo": "k/albedo-qwen3.6-35b-k03",
            "uid": 163,
            "king_version": 42,
            "king_repo": "moon/albedo-qwen3.6-35b-well",
            "eval_run_id": "8537377b-7830-4cf2-a2c3-43202e8beefd",
        },
        subnet=97,
    )
    blocks = payload["blocks"]
    assert blocks[0]["type"] == "section"
    assert "header" not in {b["type"] for b in blocks}
    text = blocks[0]["text"]["text"]
    assert "*Duel Started*" in text
    assert "SN97" in text
    assert "`k/albedo-qwen3.6-35b-k03`" in text
    assert "king v42" in text
    context = blocks[-1]["elements"][0]["text"]
    assert hippius_repo_url("k/albedo-qwen3.6-35b-k03") in context
    assert "SN97" in context


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
    assert "*New King*" in text
    assert "`org/new-king`" in text
    assert "v2" in text and "v1" in text
    assert "margin +0.200" in text
    assert "0.600 vs 0.400" in text


def test_build_slack_payload_king_defended():
    payload = build_slack_payload(
        kind="king_defended",
        title="[king_defended] other/challenger",
        message="SN97 duel finished — king defended",
        detail={
            "repo": "other/challenger",
            "king_version": 2,
            "win_margin": -0.1,
            "score_challenger": 0.45,
            "score_king": 0.55,
            "uid": 20,
        },
        subnet=97,
    )
    text = payload["blocks"][0]["text"]["text"]
    assert "*King Defended*" in text
    assert "`other/challenger`" in text
    assert "king v2 held" in text
    assert "margin -0.100" in text


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
    assert "uid *166*" in text
    assert "foremost/albedo" in payload["text"]
