"""Tests for compact Slack block formatting."""

from app.notifications.slack_format import build_slack_payload, hippius_repo_url


def test_build_slack_payload_has_header_fields_and_links():
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
    assert blocks[0]["type"] == "header"
    assert "New Duel" in blocks[0]["text"]["text"]
    section = blocks[1]["text"]["text"]
    assert "k/albedo-qwen3.6-35b-k03" in section
    context = blocks[-1]["elements"][0]["text"]
    assert hippius_repo_url("k/albedo-qwen3.6-35b-k03") in context
    assert "SN97" in context


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
    assert "uid *166*" in payload["blocks"][1]["text"]["text"]
    assert "foremost/albedo" in payload["text"]
