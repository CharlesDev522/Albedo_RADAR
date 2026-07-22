"""Tests for new hub repo Slack notifications."""

import asyncio
from unittest.mock import AsyncMock

from app.notifications.messages import build_repo_new_alert
from app.notifications.repo_alerts import hub_repo_new_source_key, notify_new_hub_repo


def test_hub_repo_new_source_key_is_per_repo():
    assert hub_repo_new_source_key(host="hippius", repo="miner/albedo-qwen3.6-35b-a") == (
        "repo_new:hippius:miner/albedo-qwen3.6-35b-a"
    )
    assert hub_repo_new_source_key(host="huggingface", repo="owner/repo") == (
        "repo_new:huggingface:owner/repo"
    )


def test_build_repo_new_alert_includes_host():
    alert = build_repo_new_alert(
        netuid=97,
        repo="owner/albedo-qwen3.6-35b-x",
        event_type="hub_repo_added",
        source_key="repo_new:huggingface:owner/albedo-qwen3.6-35b-x",
        model_family="qwen3.6-35b",
        meta={"host": "huggingface"},
        host_label="Hugging Face",
    )
    assert alert.kind == "repo_new"
    assert "Hugging Face" in alert.title
    assert alert.detail["host"] == "huggingface"
    assert alert.source_key == "repo_new:huggingface:owner/albedo-qwen3.6-35b-x"


def test_notify_new_hub_repo_dispatches_when_live():
    from app.config import Settings
    from app.notifications.dispatcher import NotificationDispatcher

    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.mark_startup_finalized()
    dispatcher.notify_content = AsyncMock(return_value=True)

    sent = asyncio.run(
        notify_new_hub_repo(
            AsyncMock(),
            dispatcher,
            netuid=97,
            repo="miner/albedo-qwen3-4b-new",
            host="huggingface",
            model_family="qwen3-4b",
            hub_digest="revision:abc",
        )
    )
    assert sent is True
    dispatcher.notify_content.assert_awaited_once()
    alert = dispatcher.notify_content.await_args.args[1]
    assert alert.kind == "repo_new"
    assert alert.source_key == "repo_new:huggingface:miner/albedo-qwen3-4b-new"


def test_notify_new_hub_repo_skips_before_live():
    from app.config import Settings
    from app.notifications.dispatcher import NotificationDispatcher

    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)

    sent = asyncio.run(
        notify_new_hub_repo(
            AsyncMock(),
            dispatcher,
            netuid=97,
            repo="miner/albedo-qwen3-4b-new",
            host="hippius",
        )
    )
    assert sent is False
