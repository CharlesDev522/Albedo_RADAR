"""Tests for live duel detection."""

from app.services.albedo_live_duel_service import build_live_duel


def test_build_live_duel_from_current_eval():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "reign": {
            "members": [
                {
                    "king_version": 31,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk_king",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "current_eval": {
            "eval_run_id": "eval-1",
            "submission_id": "sub-1",
            "state": "GENERATING",
            "sample_count": 128,
            "generated_sample_count": 64,
            "started_at": "2026-06-27T11:00:00+00:00",
            "model_uri": "org/challenger@sha256:2",
            "hotkey": "hk_chal",
            "uid": 42,
        },
        "queue": [],
    }

    live = build_live_duel(
        dashboard,
        state=None,
        subnet=97,
        dashboard_base_url="https://example.com/albedo",
    )

    assert live.is_active is True
    assert live.status == "duel"
    assert live.eval_run_id == "eval-1"
    assert live.progress_pct == 50.0
    assert live.challenger is not None
    assert live.challenger.uid == 42
    assert live.king is not None
    assert live.king.king_version == 31


def test_build_live_duel_idle():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "reign": {"members": []},
        "current_eval": None,
        "queue": [],
    }
    state = {
        "counts": {"eval": {"running": 0, "queued": 0}},
        "stages": {"eval": {"running": [], "queued": []}},
    }

    live = build_live_duel(
        dashboard,
        state=state,
        subnet=97,
        dashboard_base_url="https://example.com/albedo",
    )

    assert live.is_active is False
    assert live.status == "idle"
