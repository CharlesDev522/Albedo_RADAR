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

def test_repo_crown_analysis_multi_owner_and_links():
    from app.services.albedo_miner_lookup import MinerIdentity, MinerLookup

    lookup = MinerLookup(
        by_hotkey={
            "hk_a": MinerIdentity(coldkey="ck_owner1", repo="org/model-a", uid=1),
            "hk_b": MinerIdentity(coldkey="ck_owner2", repo="org/model-a", uid=2),
        },
        by_uid={
            1: MinerIdentity(coldkey="ck_owner1", repo="org/model-a", uid=1),
            2: MinerIdentity(coldkey="ck_owner2", repo="org/model-a", uid=2),
        },
    )

    dashboard = {
        "updated_at": "2026-06-27T14:00:00+00:00",
        "chain": {"judge_models": []},
        "reign": {
            "members": [
                {
                    "king_version": 2,
                    "model_uri": "org/model-a@sha256:2",
                    "hotkey": "hk_b",
                    "uid": 2,
                    "weight_bps": 2000,
                },
            ]
        },
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "c1",
                "challenger_won": True,
                "coronated": True,
                "king_version": 1,
                "score_challenger": 0.6,
                "score_king": 0.4,
                "win_margin": 0.2,
                "finished_at": "2026-06-26T10:00:00+00:00",
                "model_uri": "org/model-a@sha256:1",
                "hotkey": "hk_a",
                "uid": 1,
                "score_breakdown": {"by_judge": {}, "by_metric": {}},
                "king": {"king_version": 0, "model_uri": "org/other@sha256:0", "uid": 99, "hotkey": "hk_old"},
            },
            {
                "eval_run_id": "c2",
                "challenger_won": True,
                "coronated": True,
                "king_version": 2,
                "score_challenger": 0.55,
                "score_king": 0.45,
                "win_margin": 0.1,
                "finished_at": "2026-06-27T12:00:00+00:00",
                "model_uri": "org/model-a@sha256:2",
                "hotkey": "hk_b",
                "uid": 2,
                "score_breakdown": {"by_judge": {}, "by_metric": {}},
                "king": {"king_version": 1, "model_uri": "org/model-a@sha256:1", "uid": 1, "hotkey": "hk_a"},
            },
            {
                "eval_run_id": "d1",
                "challenger_won": False,
                "coronated": False,
                "king_version": None,
                "score_challenger": 0.4,
                "score_king": 0.6,
                "win_margin": -0.2,
                "finished_at": "2026-06-27T13:00:00+00:00",
                "model_uri": "org/model-a@sha256:3",
                "hotkey": "hk_a",
                "uid": 1,
                "score_breakdown": {"by_judge": {}, "by_metric": {}},
                "king": {"king_version": 2, "model_uri": "org/model-a@sha256:2", "uid": 2, "hotkey": "hk_b"},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
        miner_lookup=lookup,
    )

    analysis = overview.repo_crown_analysis
    assert analysis.total_repos_crowned == 1
    assert analysis.total_unique_coldkeys == 2
    assert "org/model-a" in analysis.multi_owner_repos

    repo_row = analysis.crowns_by_repo[0]
    assert repo_row.key == "org/model-a"
    assert repo_row.coronations == 2
    assert repo_row.multi_owner is True
    assert repo_row.owner_count == 2
    assert len(repo_row.coldkeys) == 2
    assert repo_row.duel_count == 3
    assert repo_row.challenger_wins == 2

    assert len(analysis.repo_coldkey_links) == 2
    link_coldkeys = {link.coldkey for link in analysis.repo_coldkey_links}
    assert link_coldkeys == {"ck_owner1", "ck_owner2"}
    reign_link = next(link for link in analysis.repo_coldkey_links if link.coldkey == "ck_owner2")
    assert reign_link.in_reign is True
    assert reign_link.coronations == 1


def test_repo_crown_reward_estimates_with_basis():
    from app.schemas.albedo_analysis import AlbedoRewardBasis
    from app.services.albedo_miner_lookup import MinerIdentity, MinerLookup

    lookup = MinerLookup(
        by_hotkey={
            "hk_a": MinerIdentity(coldkey="ck1", repo="org/model-a", uid=1),
        },
        by_uid={1: MinerIdentity(coldkey="ck1", repo="org/model-a", uid=1)},
    )
    basis = AlbedoRewardBasis(
        daily_subnet_alpha=240.0,
        alpha_price_tao=0.05,
        calculation_source="test",
        default_weight_bps=2000,
    )
    dashboard = {
        "updated_at": "2026-06-27T14:00:00+00:00",
        "chain": {"judge_models": []},
        "reign": {
            "members": [
                {
                    "king_version": 1,
                    "model_uri": "org/model-a@sha256:1",
                    "hotkey": "hk_a",
                    "uid": 1,
                    "weight_bps": 2000,
                },
            ]
        },
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "c1",
                "challenger_won": True,
                "coronated": True,
                "king_version": 1,
                "score_challenger": 0.6,
                "score_king": 0.4,
                "win_margin": 0.2,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/model-a@sha256:1",
                "hotkey": "hk_a",
                "uid": 1,
                "score_breakdown": {"by_judge": {}, "by_metric": {}},
                "king": {"king_version": 0, "model_uri": "org/other@sha256:0", "uid": 99, "hotkey": "hk_old"},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
        miner_lookup=lookup,
        reward_basis=basis,
    )

    analysis = overview.repo_crown_analysis
    assert analysis.reward_basis.daily_subnet_alpha == 240.0
    repo_row = analysis.crowns_by_repo[0]
    assert repo_row.total_estimated_alpha is not None
    assert repo_row.total_estimated_alpha > 0
    assert repo_row.total_estimated_tao is not None
    assert repo_row.ongoing_daily_alpha == 48.0  # 20% of 240
    coldkey_row = analysis.crowns_by_coldkey[0]
    assert coldkey_row.total_estimated_alpha == repo_row.total_estimated_alpha
    assert analysis.grand_total_estimated_alpha == repo_row.total_estimated_alpha


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
