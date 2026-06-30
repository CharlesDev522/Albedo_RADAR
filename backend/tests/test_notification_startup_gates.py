"""Tests for notification startup gates."""

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.notifications.startup_gates import hub_probe_gate_satisfied, startup_ready_for_live


def test_hub_probe_gate_disabled_when_zero():
    settings = Settings(notification_min_hub_index_probes=0)
    assert hub_probe_gate_satisfied(
        settings=settings,
        probes=0,
        collector_started_at=datetime.now(timezone.utc),
    )


def test_hub_probe_gate_requires_probe_before_max_wait():
    settings = Settings(
        notification_min_hub_index_probes=1,
        notification_startup_max_seconds=600,
    )
    started = datetime.now(timezone.utc)
    assert hub_probe_gate_satisfied(settings=settings, probes=0, collector_started_at=started) is False
    assert hub_probe_gate_satisfied(settings=settings, probes=1, collector_started_at=started) is True


def test_hub_probe_gate_falls_back_after_max_wait():
    settings = Settings(
        notification_min_hub_index_probes=2,
        notification_startup_max_seconds=600,
    )
    started = datetime.now(timezone.utc) - timedelta(seconds=700)
    assert hub_probe_gate_satisfied(settings=settings, probes=0, collector_started_at=started) is True


def test_startup_ready_requires_grace_only_when_hub_gate_disabled():
    settings = Settings(
        notification_grace_seconds=300,
        notification_min_hub_index_probes=0,
        dashboard_subnets=[97],
    )
    started = datetime.now(timezone.utc)
    assert startup_ready_for_live(
        settings=settings,
        grace_elapsed=False,
        is_live=False,
        hub_probes_by_subnet={97: 0},
        collector_started_at=started,
    ) is False
    assert startup_ready_for_live(
        settings=settings,
        grace_elapsed=True,
        is_live=False,
        hub_probes_by_subnet={97: 0},
        collector_started_at=started,
    ) is True
