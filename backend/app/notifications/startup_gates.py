"""Notification startup gate helpers (HTTP probes — independent of DB repo track sync)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings


def hub_probe_gate_satisfied(
    *,
    settings: Settings,
    probes: int,
    collector_started_at: datetime,
) -> bool:
    """True when enough lightweight Hippius hub HTTP probes completed, or gate disabled."""
    required = settings.notification_min_hub_index_probes
    if required <= 0:
        return True
    if probes >= required:
        return True
    max_wait = settings.notification_startup_max_seconds
    if max_wait <= 0:
        return False
    age = (datetime.now(timezone.utc) - collector_started_at).total_seconds()
    return age >= max_wait


def startup_ready_for_live(
    *,
    settings: Settings,
    grace_elapsed: bool,
    is_live: bool,
    full_scan_done_for: set[int],
    hub_probes_by_subnet: dict[int, int],
    collector_started_at: datetime,
) -> bool:
    if is_live or not grace_elapsed:
        return False
    for netuid in settings.dashboard_subnets:
        if netuid not in full_scan_done_for:
            return False
        if not hub_probe_gate_satisfied(
            settings=settings,
            probes=hub_probes_by_subnet.get(netuid, 0),
            collector_started_at=collector_started_at,
        ):
            return False
    return True
