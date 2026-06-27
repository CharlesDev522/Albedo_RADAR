"""Tests for Albedo duel analysis service."""

from app.services.albedo_analysis_service import build_analysis_overview, parse_model_uri


def test_parse_model_uri():
    ns, name, uri = parse_model_uri(
        "arboshelper/albedo-qwen3.6-35b-1-3-final@sha256:abc"
    )
    assert ns == "arboshelper"
    assert name == "albedo-qwen3.6-35b-1-3-final"
    assert uri.startswith("arboshelper/")


def test_build_analysis_overview_counts_and_history():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "chain": {"judge_models": ["judge/a", "judge/b"]},
        "reign": {
            "members": [
                {
                    "king_version": 2,
                    "model_uri": "org/new-king@sha256:1",
                    "hotkey": "hk_new",
                    "uid": 10,
                    "weight_bps": 2000,
                },
                {
                    "king_version": 1,
                    "model_uri": "org/old-king@sha256:2",
                    "hotkey": "hk_old",
                    "uid": 5,
                    "weight_bps": 2000,
                },
            ]
        },
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "r1",
                "challenger_won": True,
                "coronated": True,
                "king_version": 2,
                "score_challenger": 0.6,
                "score_king": 0.4,
                "win_margin": 0.2,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/new-king@sha256:1",
                "hotkey": "hk_new",
                "uid": 10,
                "score_breakdown": {
                    "by_judge": {"judge/a": 0.6},
                    "by_metric": {"correctness": 0.55},
                },
                "king": {
                    "king_version": 1,
                    "model_uri": "org/old-king@sha256:2",
                    "uid": 5,
                    "hotkey": "hk_old",
                },
            },
            {
                "eval_run_id": "r2",
                "challenger_won": False,
                "coronated": False,
                "king_version": None,
                "score_challenger": 0.45,
                "score_king": 0.55,
                "win_margin": -0.1,
                "finished_at": "2026-06-26T10:00:00+00:00",
                "model_uri": "other/challenger@sha256:3",
                "hotkey": "hk_chal",
                "uid": 20,
                "score_breakdown": {
                    "by_judge": {"judge/a": 0.45},
                    "by_metric": {"correctness": 0.4},
                },
                "king": {
                    "king_version": 2,
                    "model_uri": "org/new-king@sha256:1",
                    "uid": 10,
                    "hotkey": "hk_new",
                },
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        state={"eval": {"state": "idle"}},
        subnet=97,
        source_url="https://example.com/dashboard.json",
    )

    assert overview.total_duels == 2
    assert overview.challenger_wins == 1
    assert overview.king_wins == 1
    assert overview.coronations == 1
    assert overview.challenger_win_pct == 50.0
    assert overview.current_king is not None
    assert overview.current_king.king_version == 2
    assert len(overview.king_history) == 1
    assert overview.king_history[0].defeated_king_version == 1
    assert len(overview.recent_duels) == 2
    assert overview.recent_duels[0].eval_run_id == "r1"
    assert len(overview.judge_aggregates) == 1
    assert len(overview.metric_aggregates) == 1
    assert len(overview.timeline) == 2
    assert overview.pipeline
