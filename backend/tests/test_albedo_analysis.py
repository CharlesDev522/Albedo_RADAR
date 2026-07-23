"""Tests for Albedo duel analysis service."""

from app.services.albedo_analysis_service import build_analysis_overview, judge_short_name, parse_model_uri


def test_parse_model_uri():
    ns, name, uri = parse_model_uri(
        "arboshelper/albedo-qwen3.6-35b-1-3-final@sha256:abc"
    )
    assert ns == "arboshelper"
    assert name == "albedo-qwen3.6-35b-1-3-final"
    assert uri.startswith("arboshelper/")


def test_judge_short_name_normalizes_glm_versions():
    assert judge_short_name("z-ai/glm-5.1") == "glm"
    assert judge_short_name("z-ai/glm-5.2") == "glm"
    assert judge_short_name("qwen/qwen3.5-397b-a17b") == "qwen3.5-397b-a17b"


def test_build_analysis_overview_counts_and_history():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "chain": {"judge_models": ["z-ai/glm-5.1", "qwen/qwen3.5-397b-a17b"]},
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
                    "by_judge": {"z-ai/glm-5.1": 0.6, "qwen/qwen3.5-397b-a17b": 0.55},
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
                "finished_at": "2026-06-27T11:00:00+00:00",
                "model_uri": "other/challenger@sha256:3",
                "hotkey": "hk_chal",
                "uid": 20,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.45, "qwen/qwen3.5-397b-a17b": 0.4},
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
    assert overview.current_king is not None
    assert overview.current_king.king_version == 2
    assert len(overview.king_history) == 1
    assert overview.recent_duels[0].judge_votes
    assert len(overview.recent_duels[0].judge_votes) == 2
    assert len(overview.judge_models) == 2
    assert len(overview.king_tenures) == 2
    current = next(t for t in overview.king_tenures if t.is_current_king)
    assert current.defenses == 1
    assert current.attacks_faced == 1
    assert current.defense_pct == 100.0
    assert len(overview.reign_slot_holders) == 2
    assert overview.recent_duels[0].judge_scores

def test_binary_rubric_scoring_uses_by_judge_king_pairs():
    """Binary rubric uses paired ch/k scores; judge pick is ch > k, not ch > 0.5."""
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "chain": {"judge_models": ["org/judge-a", "org/judge-b"]},
        "reign": {"members": []},
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "binary-1",
                "challenger_won": False,
                "coronated": False,
                "king_version": 1,
                "score_challenger": 0.515,
                "score_king": 0.485,
                "win_margin": 0.0059,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/challenger@sha256:1",
                "hotkey": "hk_ch",
                "uid": 2,
                "scoring_mode": "binary",
                "required_win_margin": 0.06,
                "scored_sample_count": 120,
                "judge_errors": 1,
                "score_breakdown": {
                    "by_judge": {"org/judge-a": 0.52, "org/judge-b": 0.51},
                    "by_judge_king": {"org/judge-a": 0.48, "org/judge-b": 0.52},
                    "by_metric": {"cat_01": 0.515},
                    "by_category": {"cat_01": 0.515},
                },
                "artifacts": {"EVAL_VERDICT": "https://example.com/verdict.json"},
                "king": {
                    "king_version": 1,
                    "model_uri": "org/king@sha256:0",
                    "uid": 1,
                    "hotkey": "hk_k",
                },
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
    )

    assert overview.binary_scoring_duels == 1
    assert overview.required_win_margin == 0.06

    duel = overview.recent_duels[0]
    assert duel.scoring_mode == "binary"
    assert duel.required_win_margin == 0.06
    assert duel.margin_cleared is False
    assert duel.scored_sample_count == 120
    assert duel.judge_errors == 1
    assert duel.artifacts["EVAL_VERDICT"] == "https://example.com/verdict.json"
    assert duel.category_breakdown["cat_01"] == 0.515

    by_short = {v.short_name: v for v in duel.judge_votes}
    assert by_short["judge-a"].challenger_score == 0.52
    assert by_short["judge-a"].king_score == 0.48
    assert by_short["judge-a"].pick_challenger is True
    assert by_short["judge-a"].margin_from_neutral == 0.04

    # Legacy fallback (1 - ch) would give k=0.49 and pick challenger — wrong.
    assert by_short["judge-b"].king_score == 0.52
    assert by_short["judge-b"].pick_challenger is False
    assert by_short["judge-b"].margin_from_neutral == -0.01


def test_score_timeline_includes_all_finished_duels():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "chain": {"judge_models": []},
        "reign": {"members": []},
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "recent",
                "challenger_won": True,
                "coronated": False,
                "score_challenger": 0.62,
                "score_king": 0.38,
                "win_margin": 0.24,
                "finished_at": "2026-06-27T10:30:00+00:00",
                "model_uri": "org/ch@sha256:1",
                "hotkey": "hk1",
                "uid": 1,
                "king": {"model_uri": "org/k@sha256:0", "uid": 2, "hotkey": "hk2"},
            },
            {
                "eval_run_id": "older",
                "challenger_won": False,
                "coronated": False,
                "score_challenger": 0.4,
                "score_king": 0.6,
                "win_margin": -0.2,
                "finished_at": "2026-06-25T10:00:00+00:00",
                "model_uri": "org/old@sha256:2",
                "hotkey": "hk3",
                "uid": 3,
                "king": {"model_uri": "org/k@sha256:0", "uid": 2, "hotkey": "hk2"},
            },
            {
                "eval_run_id": "recent-2",
                "challenger_won": False,
                "coronated": True,
                "score_challenger": 0.45,
                "score_king": 0.55,
                "win_margin": -0.1,
                "finished_at": "2026-06-27T11:45:00+00:00",
                "model_uri": "org/ch2@sha256:3",
                "hotkey": "hk4",
                "uid": 4,
                "king": {"model_uri": "org/k@sha256:0", "uid": 2, "hotkey": "hk2"},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
    )

    assert len(overview.score_timeline) == 3
    assert [p.eval_run_id for p in overview.score_timeline] == ["older", "recent", "recent-2"]
    assert overview.score_timeline[1].score_challenger == 0.62
    assert overview.score_timeline[2].coronated is True


def test_build_analysis_overview_excludes_voided_kings_from_history_and_rewards():
    dashboard = {
        "updated_at": "2026-07-21T20:00:00+00:00",
        "chain": {"judge_models": []},
        "reign": {
            "members": [
                {
                    "king_version": 84,
                    "model_uri": "foremost/albedo@sha256:84",
                    "hotkey": "hk84",
                    "uid": 84,
                    "weight_bps": 2500,
                },
                {
                    "king_version": 83,
                    "model_uri": "everking/albedo@sha256:83",
                    "hotkey": "hk83",
                    "uid": 83,
                    "weight_bps": 2500,
                },
            ]
        },
        "eval_runs": [
            {
                "eval_run_id": "v89",
                "challenger_won": True,
                "coronated": True,
                "king_version": 89,
                "score_challenger": 0.9,
                "score_king": 0.8,
                "win_margin": 0.1,
                "finished_at": "2026-07-18T21:05:06+00:00",
                "model_uri": "voided/albedo@sha256:89",
                "hotkey": "hk89",
                "uid": 89,
                "king": {"king_version": 88, "model_uri": "voided/albedo@sha256:88", "uid": 88, "hotkey": "hk88"},
            },
            {
                "eval_run_id": "v84",
                "challenger_won": True,
                "coronated": True,
                "king_version": 84,
                "score_challenger": 0.9,
                "score_king": 0.8,
                "win_margin": 0.1,
                "finished_at": "2026-07-15T01:03:37+00:00",
                "model_uri": "foremost/albedo@sha256:84",
                "hotkey": "hk84",
                "uid": 84,
                "king": {"king_version": 83, "model_uri": "everking/albedo@sha256:83", "uid": 83, "hotkey": "hk83"},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
    )

    assert overview.coronations == 1
    assert [k.king_version for k in overview.king_history] == [84]
    assert overview.voided_king_versions == [89]
    assert "v89" in overview.crown_history_coverage_note
    assert len(overview.king_tenures) == 2
    assert overview.king_tenures[0].king_version == 84
    assert overview.king_tenures[0].is_current_king is True


def test_reign_kings_keep_slot_tenure_past_rollover_during_voided_window():
    """v80 in reign should not stop earning when +5 rollover fired before voided kings."""
    dashboard = {
        "updated_at": "2026-07-21T20:00:00+00:00",
        "chain": {"judge_models": []},
        "reign": {
            "members": [
                {"king_version": 84, "model_uri": "a/84@sha", "hotkey": "hk84", "uid": 84, "weight_bps": 2500},
                {"king_version": 80, "model_uri": "a/80@sha", "hotkey": "hk80", "uid": 80, "weight_bps": 2500},
            ]
        },
        "eval_runs": [
            {
                "eval_run_id": "v89",
                "challenger_won": True,
                "coronated": True,
                "king_version": 89,
                "finished_at": "2026-07-18T21:00:00+00:00",
                "model_uri": "void/89@sha",
                "hotkey": "hk89",
                "uid": 89,
                "king": {"king_version": 88},
            },
            {
                "eval_run_id": "v85",
                "challenger_won": True,
                "coronated": True,
                "king_version": 85,
                "finished_at": "2026-07-16T14:00:00+00:00",
                "model_uri": "void/85@sha",
                "hotkey": "hk85",
                "uid": 85,
                "king": {"king_version": 84},
            },
            *[
                {
                    "eval_run_id": f"v{v}",
                    "challenger_won": True,
                    "coronated": True,
                    "king_version": v,
                    "finished_at": f"2026-07-{10+v:02d}T12:00:00+00:00",
                    "model_uri": f"a/{v}@sha",
                    "hotkey": f"hk{v}",
                    "uid": v,
                    "king": {"king_version": v - 1},
                }
                for v in range(76, 85)
            ],
            {
                "eval_run_id": "v80",
                "challenger_won": True,
                "coronated": True,
                "king_version": 80,
                "finished_at": "2026-07-13T18:00:00+00:00",
                "model_uri": "a/80@sha",
                "hotkey": "hk80",
                "uid": 80,
                "king": {"king_version": 79},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
    )

    v80 = next(t for t in overview.king_tenures if t.king_version == 80)
    assert v80.slot_tenure_hours is not None
    assert v80.slot_tenure_hours > 48
    assert v80.voided_bridge_hours is not None
    assert v80.voided_bridge_hours > 0
    assert v80.slot_until is None
