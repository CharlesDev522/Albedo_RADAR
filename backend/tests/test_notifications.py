"""Tests for alert notification dispatcher, messages, and watcher."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.messages import build_commit_new_alert, format_alert_body
from app.notifications.watcher import NotificationWatcher
from app.chain_reader.commitment_scanner import Commit


def _mock_commit() -> Commit:
    return Commit(
        netuid=97,
        block_number=1000,
        block_hash=None,
        uid=12,
        hotkey="hk1",
        coldkey="ck1",
        registered_at_block=900,
        commit_payload={
            "repo": "cyantest/model",
            "digest": "sha256:abc123def456",
            "version": "v6",
        },
        reveal_string="repo/ns@digest",
        model_uri="cyantest/model@sha256:abc123def456",
        payload_hash="hash1",
        commit_source="active",
    )


def _mock_session_no_existing() -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_dispatcher_skips_when_disabled():
    settings = Settings(notifications_enabled=False)
    dispatcher = NotificationDispatcher(settings)
    session = _mock_session_no_existing()

    sent = await dispatcher.notify(
        session,
        kind="commit_new",
        title="test",
        message="msg",
        source_key="commit_new:97:hk:hash",
    )

    assert sent is False
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_suppressed_until_armed():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    session = _mock_session_no_existing()

    sent = await dispatcher.notify(
        session,
        kind="repo_new",
        title="[repo_new] test/repo",
        message="should not send",
        source_key="alert:hub:hippius:test/repo:digest",
    )

    assert sent is False
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_sends_after_armed():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.arm()
    session = _mock_session_no_existing()

    with patch("app.notifications.dispatcher.send_slack_alert", new_callable=AsyncMock):
        sent = await dispatcher.notify(
            session,
            kind="repo_new",
            title="[repo_new] test/repo",
            message="live event",
            source_key="alert:hub:hippius:test/repo:digest2",
        )

    assert sent is True
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_dispatcher_memory_dedupe():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.arm()
    dispatcher.mark_seen("commit_new:97:hk:hash")
    session = _mock_session_no_existing()

    sent = await dispatcher.notify(
        session,
        kind="commit_new",
        title="test",
        message="msg",
        source_key="commit_new:97:hk:hash",
    )

    assert sent is False
    session.execute.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_persists_without_slack():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.arm()
    session = _mock_session_no_existing()

    with patch("app.notifications.dispatcher.send_slack_alert", new_callable=AsyncMock) as slack:
        sent = await dispatcher.notify(
            session,
            kind="reg_fee_low",
            title="[reg_fee_low] SN97",
            message="below threshold",
            source_key="reg_fee_low:sn97:0.5",
            detail={"registration_burn_tao": 0.5},
            subnet=97,
        )

    assert sent is True
    session.add.assert_called_once()
    session.flush.assert_awaited()
    slack.assert_not_awaited()
    assert dispatcher.is_seen("reg_fee_low:sn97:0.5")


def test_commit_new_alert_kind_tag():
    alert = build_commit_new_alert(_mock_commit())
    assert alert.kind == "commit_new"
    assert alert.title.startswith("[commit_new]")
    assert "uid 12" in alert.title
    assert "digest" in alert.message.lower()


def test_format_alert_body_orders_detail():
    body = format_alert_body(
        "crown_won",
        "SN97 crowned",
        {"repo": "cyantest/m", "uid": 5, "hotkey": "hk"},
    )
    assert "SN97 crowned" in body
    assert "*Repo:* cyantest/m" in body
    assert body.index("*Repo:*") < body.index("*Uid:*")


@pytest.mark.asyncio
async def test_watcher_emits_crown_won():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True

    dashboard = {
        "reign": {"members": [{"king_version": 2, "model_uri": "cyantest/model@v2"}]},
        "eval_runs": [
            {
                "coronated": True,
                "eval_run_id": "ev1",
                "model_uri": "cyantest/model@v2",
                "king_version": 2,
                "defeated_king_version": 1,
                "finished_at": "2026-06-14T12:00:00Z",
            }
        ],
    }

    session = _mock_session_no_existing()
    with (
        patch("app.notifications.watcher.fetch_dashboard", return_value=dashboard),
        patch(
            "app.notifications.watcher.fetch_subnet_economics",
            return_value={"registration_burn_tao": 1.5},
        ),
    ):
        sent = await watcher.poll_subnet(session, 97)

    assert sent >= 1
    dispatcher.notify_content.assert_awaited()
    alert = dispatcher.notify_content.await_args.args[1]
    assert alert.kind == "crown_won"
    assert alert.title.startswith("[crown_won]")


@pytest.mark.asyncio
async def test_watcher_bootstrap_marks_historical_crown():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)

    dashboard = {
        "reign": {"members": [{"king_version": 2, "model_uri": "cyantest/model@v2"}]},
        "eval_runs": [
            {
                "coronated": True,
                "eval_run_id": "ev-old",
                "model_uri": "cyantest/model@v2",
            }
        ],
    }
    session = _mock_session_no_existing()
    with patch("app.notifications.watcher.fetch_dashboard", return_value=dashboard):
        await watcher.bootstrap(session)

    assert watcher._bootstrapped is True
    assert dispatcher.is_seen("crown_won:ev-old:cyantest/model@v2")


@pytest.mark.asyncio
async def test_watcher_reg_fee_below_threshold():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_threshold_tao=0.75,
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True
    watcher._last_king_version = 1
    watcher._last_king_uri = "cyantest/model@v1"

    session = _mock_session_no_existing()
    empty_dashboard = {
        "reign": {"members": [{"king_version": 1, "model_uri": "cyantest/model@v1"}]},
        "eval_runs": [],
    }
    with (
        patch("app.notifications.watcher.fetch_dashboard", return_value=empty_dashboard),
        patch(
            "app.notifications.watcher.fetch_subnet_economics",
            return_value={"registration_burn_tao": 0.5, "alpha_price_tao": 0.03},
        ),
    ):
        sent = await watcher.poll_subnet(session, 97)

    assert sent == 1
    alert = dispatcher.notify_content.await_args.args[1]
    assert alert.kind == "reg_fee_low"
    assert alert.title.startswith("[reg_fee_low]")


@pytest.mark.asyncio
async def test_watcher_reg_fee_skips_above_threshold():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_threshold_tao=0.75,
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True
    watcher._last_king_version = 1
    watcher._last_king_uri = "cyantest/model@v1"

    session = _mock_session_no_existing()
    empty_dashboard = {
        "reign": {"members": [{"king_version": 1, "model_uri": "cyantest/model@v1"}]},
        "eval_runs": [],
    }
    with (
        patch("app.notifications.watcher.fetch_dashboard", return_value=empty_dashboard),
        patch(
            "app.notifications.watcher.fetch_subnet_economics",
            return_value={"registration_burn_tao": 1.2},
        ),
    ):
        sent = await watcher.poll_subnet(session, 97)

    assert sent == 0
    dispatcher.notify_content.assert_not_awaited()
