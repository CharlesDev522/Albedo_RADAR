"""Tests for eval queue, pipeline stages, and DQ failures."""

from app.services.albedo_eval_queue_service import build_eval_queue_overview
from app.services.albedo_miner_lookup import MinerIdentity, MinerLookup


def _lookup() -> MinerLookup:
    return MinerLookup(
        by_hotkey={
            "hk_wait": MinerIdentity(
                coldkey="ck1",
                repo="org/waiting-model",
                uid=10,
                commit_block=8_520_100,
            ),
            "hk_fail": MinerIdentity(
                coldkey="ck2",
                repo="org/failed-model",
                uid=20,
                commit_block=8_520_200,
            ),
        },
        by_uid={
            10: MinerIdentity(
                coldkey="ck1",
                repo="org/waiting-model",
                uid=10,
                commit_block=8_520_100,
            ),
            20: MinerIdentity(
                coldkey="ck2",
                repo="org/failed-model",
                uid=20,
                commit_block=8_520_200,
            ),
        },
    )


def test_build_eval_queue_overview_queue_pipeline_fails():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "queue": [
            {
                "uid": 10,
                "hotkey": "hk_wait",
                "model_uri": "org/waiting-model@sha256:abc",
                "state": "QUEUED",
            },
            {
                "uid": 11,
                "hotkey": "hk_unknown",
                "model_uri": "other/ns@sha256:def",
            },
        ],
        "fails": [
            {
                "submission_id": "sub-fail-1",
                "eval_run_id": "eval-fail-1",
                "uid": 20,
                "hotkey": "hk_fail",
                "model_uri": "org/failed-model@sha256:bad",
                "state": "TERMINAL_INVALID",
                "fault_class": "MINER_FAULT",
                "fault_code": "INVALID_MODEL",
                "fault_message": "Model failed validation",
                "updated_at": "2026-06-27T11:30:00+00:00",
            },
            {
                "submission_id": "sub-fail-2",
                "uid": 99,
                "state": "TERMINAL_INVALID",
                "fault_class": "INFRA_FAULT",
                "fault_code": "TIMEOUT",
                "updated_at": "2026-06-27T10:00:00+00:00",
            },
        ],
        "current_eval": None,
    }
    state = {
        "updated_at": "2026-06-27T12:01:00+00:00",
        "counts": {
            "hippius_validate": {"running": 1, "queued": 0},
            "pre_eval": {"running": 0, "queued": 1},
            "eval": {"running": 1, "queued": 2},
        },
        "stages": {
            "hippius_validate": {
                "running": [{"uid": 1, "hotkey": "hk_a", "model_uri": "a/b@sha256:1"}],
                "queued": [],
            },
            "pre_eval": {
                "running": [],
                "queued": [{"uid": 2, "hotkey": "hk_b", "model_uri": "c/d@sha256:2"}],
            },
            "eval": {
                "running": [{"uid": 3, "hotkey": "hk_c", "model_uri": "e/f@sha256:3", "state": "GENERATING"}],
                "queued": [
                    {"uid": 4, "hotkey": "hk_d", "model_uri": "g/h@sha256:4"},
                    {"uid": 5, "hotkey": "hk_e", "model_uri": "i/j@sha256:5"},
                ],
            },
        },
    }

    overview = build_eval_queue_overview(
        dashboard,
        state=state,
        subnet=97,
        source_url="https://example.com/data/dashboard.json",
        miner_lookup=_lookup(),
        fail_limit=50,
    )

    assert overview.queue_length == 2
    assert overview.queue[0].position == 1
    assert overview.queue[0].repo == "org/waiting-model"
    assert overview.queue[0].commit_block == 8_520_100
    assert overview.queue[1].repo == "other/ns"

    assert len(overview.pipeline) == 3
    assert overview.pipeline[0].stage == "hippius_validate"
    assert overview.pipeline[0].label == "Hippius validate"
    assert overview.pipeline[0].running_count == 1
    assert overview.pipeline[2].queued_count == 2
    assert overview.pipeline[2].running[0].state == "GENERATING"
    assert overview.pipeline[2].queued[0].position == 1

    assert overview.fail_count == 2
    assert overview.fails[0].fault_class == "MINER_FAULT"
    assert overview.fails[0].repo == "org/failed-model"
    assert overview.fail_counts_by_class == {"MINER_FAULT": 1, "INFRA_FAULT": 1}
    assert overview.updated_at == "2026-06-27T12:01:00+00:00"


def test_build_eval_queue_overview_empty_state():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "queue": [],
        "fails": [],
    }

    overview = build_eval_queue_overview(
        dashboard,
        state=None,
        subnet=97,
        source_url="https://example.com/data/dashboard.json",
    )

    assert overview.queue_length == 0
    assert overview.pipeline == []
    assert overview.fail_count == 0
    assert overview.updated_at == "2026-06-27T12:00:00+00:00"
