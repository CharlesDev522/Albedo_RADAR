"""Tests for notification preference storage and dispatcher gating."""

from app.config import Settings
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.preferences import (
    DEFAULT_KIND_ENABLED,
    NotificationPreferencesStore,
    build_settings_response,
    effective_kind_enabled,
    merge_preferences,
)


def test_repo_new_disabled_by_default():
    payload = merge_preferences(None)
    assert effective_kind_enabled(payload, "repo_new") is False
    assert effective_kind_enabled(payload, "eval_dq") is True


def test_merge_preferences_partial_update():
    stored = merge_preferences(None, kinds={"repo_new": True})
    updated = merge_preferences(stored, kinds={"eval_dq": False})
    assert effective_kind_enabled(updated, "repo_new") is True
    assert effective_kind_enabled(updated, "eval_dq") is False


def test_build_settings_response_respects_env_master_toggle():
    settings = Settings(notifications_enabled=False)
    payload = build_settings_response(
        settings=settings,
        stored=None,
        webhook_configured=True,
    )
    assert payload["notifications_enabled"] is False
    assert payload["env_notifications_enabled"] is False


def test_build_settings_response_stored_master_override():
    settings = Settings(notifications_enabled=True)
    stored = merge_preferences(None, notifications_enabled=False)
    payload = build_settings_response(
        settings=settings,
        stored=stored,
        webhook_configured=False,
    )
    assert payload["notifications_enabled"] is False
    assert payload["stored_notifications_enabled"] is False


def test_dispatcher_skips_disabled_kind():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    store = NotificationPreferencesStore(settings)
    store._payload = merge_preferences(None)
    dispatcher = NotificationDispatcher(settings, preferences=store)
    dispatcher.enable_resume_mode()

    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    import asyncio

    sent = asyncio.run(
        dispatcher.notify(
            session,
            kind="repo_new",
            title="[repo_new] test/repo",
            message="should not send",
            source_key="repo_new:hippius:test/repo",
        )
    )

    assert sent is False
    session.add.assert_not_called()


def test_dispatcher_sends_enabled_kind():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    store = NotificationPreferencesStore(settings)
    store._payload = merge_preferences(None, kinds={"repo_new": True})
    dispatcher = NotificationDispatcher(settings, preferences=store)
    dispatcher.enable_resume_mode()

    from unittest.mock import AsyncMock, MagicMock, patch

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    import asyncio

    with patch("app.notifications.dispatcher.send_slack_alert", new_callable=AsyncMock):
        sent = asyncio.run(
            dispatcher.notify(
                session,
                kind="repo_new",
                title="[repo_new] test/repo",
                message="live event",
                source_key="repo_new:hippius:test/repo:enabled",
            )
        )

    assert sent is True
    session.add.assert_called_once()


def test_default_kind_map_covers_all_notification_kinds():
    from app.notifications.preferences import ALL_NOTIFICATION_KINDS

    for kind in ALL_NOTIFICATION_KINDS:
        assert kind in DEFAULT_KIND_ENABLED
