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
    assert len(overview.judge_details) == 2
    assert overview.recent_duels[0].judge_votes
    assert len(overview.recent_duels[0].judge_votes) == 2
    assert overview.judge_details[0].short_name
    assert overview.judge_consensus
    assert len(overview.king_tenures) == 2
    current = next(t for t in overview.king_tenures if t.is_current_king)
    assert current.defenses == 1
    assert current.attacks_faced == 1
    assert current.defense_pct == 100.0
    assert len(overview.reign_slot_holders) == 2
    assert overview.recent_duels[0].judge_scores

    analytics = overview.judge_analytics
    assert analytics.total_submissions == 2
    assert len(analytics.by_repo) >= 2
    assert len(analytics.by_challenger) == 2
    assert len(analytics.pairwise) == 1
    assert analytics.pairwise[0].duels == 2
    assert len(analytics.by_outcome) == 2
    assert analytics.spread_summary.avg_spread is not None


def test_judge_analytics_three_judge_panel():
    dashboard = {
        "updated_at": "2026-06-27T12:00:00+00:00",
        "chain": {
            "judge_models": [
                "z-ai/glm-5.1",
                "qwen/qwen3.5-397b-a17b",
                "deepseek/deepseek-v3.2",
            ]
        },
        "reign": {"members": []},
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "r1",
                "challenger_won": True,
                "coronated": False,
                "score_challenger": 0.6,
                "score_king": 0.4,
                "win_margin": 0.2,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/repo-a@sha256:1",
                "hotkey": "hk_a",
                "uid": 1,
                "score_breakdown": {
                    "by_judge": {
                        "z-ai/glm-5.1": 0.7,
                        "qwen/qwen3.5-397b-a17b": 0.65,
                        "deepseek/deepseek-v3.2": 0.45,
                    }
                },
                "king": {"king_version": 1, "model_uri": "org/king@sha256:0", "uid": 9, "hotkey": "hk_k"},
            },
            {
                "eval_run_id": "r2",
                "challenger_won": False,
                "coronated": False,
                "score_challenger": 0.4,
                "score_king": 0.6,
                "win_margin": -0.2,
                "finished_at": "2026-06-27T11:00:00+00:00",
                "model_uri": "org/repo-b@sha256:2",
                "hotkey": "hk_b",
                "uid": 2,
                "score_breakdown": {
                    "by_judge": {
                        "z-ai/glm-5.1": 0.35,
                        "qwen/qwen3.5-397b-a17b": 0.4,
                        "deepseek/deepseek-v3.2": 0.55,
                    }
                },
                "king": {"king_version": 1, "model_uri": "org/king@sha256:0", "uid": 9, "hotkey": "hk_k"},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
    )
    analytics = overview.judge_analytics

    assert analytics.total_submissions == 2
    assert len(analytics.judge_models) == 3
    assert len(analytics.pairwise) == 3
    repo_a = next(r for r in analytics.by_repo if r.key == "org/repo-a")
    assert repo_a.duels == 1
    assert repo_a.wins == 1
    assert len(repo_a.judges) == 3
    assert analytics.spread_summary.split_duels == 2

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
