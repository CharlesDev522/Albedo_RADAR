"""Tests for alert notification dispatcher, messages, and watcher."""

from datetime import datetime, timezone
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
async def test_dispatcher_suppressed_during_grace():
    settings = Settings(
        notifications_enabled=True,
        slack_webhook_url=None,
        notification_grace_seconds=60,
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.begin_startup_grace(60)
    session = _mock_session_no_existing()

    sent = await dispatcher.notify(
        session,
        kind="repo_new",
        title="[repo_new] test/repo",
        message="should not send",
        source_key="alert:hub:hippius:test/repo:digest",
    )

    assert sent is False
    assert dispatcher.should_finalize_startup() is False
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_hydrated_keys_still_require_finalize():
    """Prior alert keys in cache must not bypass grace — only mark_startup_finalized does."""
    settings = Settings(
        notifications_enabled=True,
        slack_webhook_url=None,
        notification_grace_seconds=60,
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.begin_startup_grace(60)
    dispatcher.mark_seen("alert:hub:hippius:old/repo:digest")
    session = _mock_session_no_existing()

    sent = await dispatcher.notify(
        session,
        kind="repo_new",
        title="[repo_new] new/repo",
        message="should not send during grace",
        source_key="alert:hub:hippius:new/repo:digest",
    )

    assert sent is False
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_sends_after_startup_finalized():
    settings = Settings(notifications_enabled=True, slack_webhook_url=None)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
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
    dispatcher.enable_resume_mode()
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
    dispatcher.enable_resume_mode()
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
async def test_watcher_skips_crown_lost_when_crown_won_same_poll():
    """Avoid duplicate crown_lost + crown_won on the same king transition."""
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True
    watcher._last_king_version = 1
    watcher._last_king_uri = "org/old-king@sha256:2"

    dashboard = {
        "reign": {"members": [{"king_version": 2, "model_uri": "org/new-king@sha256:1"}]},
        "current_eval": None,
        "eval_runs": [
            {
                "coronated": True,
                "eval_run_id": "r1",
                "model_uri": "org/new-king@sha256:1",
                "king_version": 2,
                "defeated_king_version": 1,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "challenger_won": True,
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

    kinds = [c.args[1].kind for c in dispatcher.notify_content.await_args_list]
    assert "crown_won" in kinds
    assert "crown_lost" not in kinds
    assert sent == 1


@pytest.mark.asyncio
async def test_watcher_king_defended_requires_explicit_loss():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True

    dashboard = {
        "reign": {"members": [{"king_version": 2, "model_uri": "cyantest/king@v2"}]},
        "current_eval": None,
        "eval_runs": [
            {
                "eval_run_id": "r-pending",
                "finished_at": "2026-06-14T13:00:00Z",
                "challenger_won": None,
                "coronated": False,
                "model_uri": "other/challenger@v1",
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

    assert sent == 0
    dispatcher.notify_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_watcher_poll_uses_fresh_dashboard():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True

    session = _mock_session_no_existing()
    with (
        patch(
            "app.notifications.watcher.fetch_dashboard",
            new_callable=AsyncMock,
            return_value={
                "reign": {"members": [{"king_version": 1, "model_uri": "cyantest/model@v1"}]},
                "eval_runs": [],
            },
        ) as fetch_mock,
        patch(
            "app.notifications.watcher.fetch_subnet_economics",
            return_value={"registration_burn_tao": 1.5},
        ),
    ):
        await watcher.poll_subnet(session, 97)

    fetch_mock.assert_awaited_once()
    assert fetch_mock.await_args.kwargs.get("fresh") is True


@pytest.mark.asyncio
async def test_watcher_emits_king_defended():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True

    dashboard = {
        "reign": {"members": [{"king_version": 2, "model_uri": "cyantest/king@v2"}]},
        "current_eval": None,
        "eval_runs": [
            {
                "eval_run_id": "r-defend",
                "challenger_won": False,
                "coronated": False,
                "finished_at": "2026-06-14T13:00:00Z",
                "model_uri": "other/challenger@v1",
                "hotkey": "hk_chal",
                "uid": 20,
                "win_margin": -0.1,
                "king": {"king_version": 2, "model_uri": "cyantest/king@v2"},
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
    kinds = [c.args[1].kind for c in dispatcher.notify_content.await_args_list]
    assert "king_defended" in kinds


@pytest.mark.asyncio
async def test_watcher_emits_duel_new():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True

    dashboard = {
        "reign": {"members": [{"king_version": 2, "model_uri": "cyantest/king@v2"}]},
        "current_eval": {
            "eval_run_id": "eval-live-1",
            "state": "GENERATING",
            "model_uri": "other/challenger@v1",
            "uid": 42,
            "hotkey": "hk_chal",
        },
        "eval_runs": [],
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
    alert = dispatcher.notify_content.await_args.args[1]
    assert alert.kind == "duel_new"


@pytest.mark.asyncio
async def test_watcher_reg_fee_skips_already_below_at_bootstrap():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_thresholds_tao=[1.0, 0.75, 0.6],
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)

    dashboard = {
        "reign": {"members": [{"king_version": 1, "model_uri": "cyantest/model@v1"}]},
        "current_eval": None,
        "eval_runs": [],
    }
    session = _mock_session_no_existing()
    with (
        patch("app.notifications.watcher.fetch_dashboard", return_value=dashboard),
        patch(
            "app.notifications.watcher.fetch_subnet_economics",
            return_value={"registration_burn_tao": 0.5},
        ),
    ):
        await watcher.bootstrap(session)
        sent = await watcher.poll_subnet(session, 97)

    assert watcher._reg_fee_alerted_tiers == {1.0, 0.75, 0.6}
    assert sent == 0
    dispatcher.notify_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_watcher_emits_crown_won():
    settings = Settings(notifications_enabled=True, default_subnet=97)
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
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
async def test_watcher_hub_index_seed_marks_albedo_repos():
    settings = Settings(notifications_enabled=True)
    dispatcher = NotificationDispatcher(settings)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    hub_index = {
        "cyantest/albedo-qwen3-4b-test": type(
            "M",
            (),
            {"digest": "sha256:abc123def456789012345678901234567890123456789012345678901234"},
        )(),
        "other/random-model": type(
            "M",
            (),
            {"digest": "sha256:deadbeef"},
        )(),
    }
    with patch(
        "app.notifications.watcher.HippiusHubClient.fetch_albedo_index",
        new_callable=AsyncMock,
        return_value=hub_index,
    ):
        marked = await watcher._seed_hub_index_keys()

    assert marked == 1
    assert dispatcher.is_seen(
        "alert:hub:hippius:cyantest/albedo-qwen3-4b-test:sha256:abc123def456789012345678901234567890123456789012345678901234"
    )


def test_poller_hub_probe_gate_falls_back_after_max_wait():
    from datetime import timedelta

    from app.collectors.commitment_poller import CommitmentPoller

    poller = CommitmentPoller()
    poller.settings = Settings(
        notification_min_hub_index_probes=2,
        notification_startup_max_seconds=600,
        dashboard_subnets=[97],
    )
    poller._collector_started_at = datetime.now(timezone.utc) - timedelta(seconds=700)
    poller._startup_full_scan_done.add(97)
    poller._startup_hub_probes[97] = 0

    assert poller._startup_ready_for_live() is True


def test_poller_hub_probe_gate_requires_probe_before_max_wait():
    from app.collectors.commitment_poller import CommitmentPoller

    poller = CommitmentPoller()
    poller.settings = Settings(
        notification_min_hub_index_probes=2,
        notification_startup_max_seconds=600,
        dashboard_subnets=[97],
    )
    poller._collector_started_at = datetime.now(timezone.utc)
    poller._startup_full_scan_done.add(97)
    poller._startup_hub_probes[97] = 1

    assert poller._startup_ready_for_live() is False

    poller._startup_hub_probes[97] = 2
    poller.notifier.begin_startup_grace(0)
    assert poller._startup_ready_for_live() is True


@pytest.mark.asyncio
async def test_watcher_probe_hub_index_counts_albedo_repos():
    settings = Settings(notifications_enabled=True)
    watcher = NotificationWatcher(dispatcher=NotificationDispatcher(settings), settings=settings)
    hub_index = {
        "cyantest/albedo-qwen3-4b-test": type("M", (), {"digest": "sha256:abc"})(),
        "other/random-model": type("M", (), {"digest": "sha256:dead"})(),
    }
    with patch(
        "app.notifications.watcher.HippiusHubClient.fetch_albedo_index",
        new_callable=AsyncMock,
        return_value=hub_index,
    ):
        count = await watcher.probe_hub_index()
    assert count == 1


@pytest.mark.asyncio
async def test_watcher_reg_fee_alerts_each_tier_once():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_thresholds_tao=[1.0, 0.75, 0.6],
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
    dispatcher.notify_content = AsyncMock(return_value=True)
    watcher = NotificationWatcher(dispatcher=dispatcher, settings=settings)
    watcher._bootstrapped = True

    session = _mock_session_no_existing()
    empty_dashboard = {
        "reign": {"members": [{"king_version": 1, "model_uri": "cyantest/model@v1"}]},
        "eval_runs": [],
    }
    with (
        patch("app.notifications.watcher.fetch_dashboard", return_value=empty_dashboard),
        patch(
            "app.notifications.watcher.fetch_subnet_economics",
            return_value={"registration_burn_tao": 0.55, "alpha_price_tao": 0.03},
        ),
    ):
        sent = await watcher.poll_subnet(session, 97)

    assert sent == 3
    keys = [call.args[1].source_key for call in dispatcher.notify_content.await_args_list]
    assert "reg_fee_low:sn97:tier_1" in keys
    assert "reg_fee_low:sn97:tier_0.75" in keys
    assert "reg_fee_low:sn97:tier_0.6" in keys


@pytest.mark.asyncio
async def test_watcher_reg_fee_below_threshold():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_thresholds_tao=[1.0, 0.75, 0.6],
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
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

    assert sent == 3
    alert = dispatcher.notify_content.await_args.args[1]
    assert alert.kind == "reg_fee_low"
    assert alert.title.startswith("[reg_fee_low]")


@pytest.mark.asyncio
async def test_watcher_reg_fee_skips_above_threshold():
    settings = Settings(
        notifications_enabled=True,
        default_subnet=97,
        notification_reg_fee_thresholds_tao=[1.0, 0.75, 0.6],
    )
    dispatcher = NotificationDispatcher(settings)
    dispatcher.enable_resume_mode()
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
