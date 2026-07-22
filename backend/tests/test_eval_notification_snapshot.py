"""Tests for eval notification snapshot helper."""

import asyncio
from unittest.mock import patch

from app.notifications.eval_snapshot import fetch_eval_notification_snapshot
from app.services.albedo_eval_queue_service import AlbedoEvalFail, AlbedoPipelineBucket


def test_fetch_eval_notification_snapshot_counts_pipeline():
    dashboard = {
        "current_eval": {"eval_run_id": "e1"},
        "fails": [
            {"submission_id": "s1", "state": "TERMINAL_INVALID"},
            {"submission_id": "s2", "state": "TERMINAL_INFRA_FAILED"},
            {"submission_id": "s3", "state": "SOME_OTHER"},
        ],
    }
    validate_bucket = AlbedoPipelineBucket(
        stage="hippius_validate",
        label="Hippius validate",
        running_count=1,
        queued_count=2,
        running=[],
        queued=[],
    )

    with (
        patch(
            "app.notifications.eval_snapshot.fetch_dashboard",
            return_value=dashboard,
        ),
        patch(
            "app.notifications.eval_snapshot.fetch_state",
            return_value={"stages": {}},
        ),
        patch(
            "app.notifications.eval_snapshot._parse_pipeline_buckets",
            return_value=[validate_bucket],
        ),
        patch(
            "app.notifications.eval_snapshot.parse_dashboard_fails",
            return_value=[
                AlbedoEvalFail(submission_id="s1", state="TERMINAL_INVALID"),
                AlbedoEvalFail(submission_id="s2", state="TERMINAL_INFRA_FAILED"),
                AlbedoEvalFail(submission_id="s3", state="SOME_OTHER"),
            ],
        ),
    ):
        snap = asyncio.run(fetch_eval_notification_snapshot())

    assert snap["dashboard_ok"] is True
    assert snap["state_ok"] is True
    assert snap["current_eval"] is True
    assert snap["hippius_validate_queued"] == 2
    assert snap["hippius_validate_running"] == 1
    assert snap["eval_fail_count"] == 2
