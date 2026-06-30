"""Tests for alert notification dispatcher and watcher."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.watcher import NotificationWatcher


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
async def test_dispatcher_dedupes_by_source_key():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = 42
    session.execute.return_value = result

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
async def test_dispatcher_persists_without_slack():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    session = _mock_session_no_existing()

    with patch("app.notifications.dispatcher.send_slack_alert", new_callable=AsyncMock) as slack:
        sent = await dispatcher.notify(
            session,
            kind="reg_fee_low",
            title="Low reg fee",
            message="below threshold",
            source_key="reg_fee_low:sn97:0.5",
            detail={"registration_burn_tao": 0.5},
            subnet=97,
        )

    assert sent is True
    session.add.assert_called_once()
    session.flush.assert_awaited()
    slack.assert_not_awaited()


@pytest.mark.asyncio
async def test_watcher_emits_crown_won():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.notify = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)

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
    with patch("app.notifications.watcher.fetch_dashboard", return_value=dashboard):
        sent = await watcher.poll_subnet(session, 97)

    assert sent >= 1
    dispatcher.notify.assert_awaited()
    call_kwargs = dispatcher.notify.await_args.kwargs
    assert call_kwargs["kind"] == "crown_won"


@pytest.mark.asyncio
async def test_watcher_reg_fee_below_threshold():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_threshold_tao=0.75,
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.notify = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
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
    reg_calls = [c for c in dispatcher.notify.await_args_list if c.kwargs.get("kind") == "reg_fee_low"]
    assert len(reg_calls) == 1
    assert reg_calls[0].kwargs["detail"]["registration_burn_tao"] == 0.5


@pytest.mark.asyncio
async def test_watcher_reg_fee_skips_above_threshold():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_threshold_tao=0.75,
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.notify = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
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
    dispatcher.notify.assert_not_awaited()
