"""Tests for SN97 merge advisor."""

import pytest

from app.services.albedo_merge_advisor_service import (
    bradley_terry_strengths,
    build_merge_advisor_recommendation,
    mergekit_model_ref,
)


def test_mergekit_model_ref_strips_protocol():
    assert mergekit_model_ref("hf://org/model@revision:abc") == "org/model@revision:abc"
    assert mergekit_model_ref("org/king@sha256:dead") == "org/king@sha256:dead"


def test_bradley_terry_prefers_frequent_winner():
    outcomes = [
        ("challenger", "king", 0.9),
        ("challenger", "king", 0.85),
        ("other", "king", 0.2),
    ]
    strengths = bradley_terry_strengths(outcomes)
    assert strengths["challenger"] > strengths["other"]
    assert strengths["challenger"] > strengths["king"]


def test_build_merge_advisor_nuslerp_for_single_donor():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 3,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk_king",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [
            {
                "eval_run_id": "r1",
                "challenger_won": True,
                "coronated": False,
                "win_margin": 0.12,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/donor@sha256:2",
                "uid": 2,
                "scoring_mode": "binary",
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.7, "qwen/qwen3.5-397b-a17b": 0.65},
                    "by_judge_king": {"z-ai/glm-5.1": 0.3, "qwen/qwen3.5-397b-a17b": 0.35},
                },
                "king": {
                    "king_version": 3,
                    "model_uri": "org/king@sha256:1",
                    "uid": 1,
                },
            },
            {
                "eval_run_id": "r2",
                "challenger_won": False,
                "coronated": False,
                "win_margin": -0.05,
                "finished_at": "2026-06-27T11:00:00+00:00",
                "model_uri": "org/weak@sha256:3",
                "uid": 3,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.4, "qwen/qwen3.5-397b-a17b": 0.45},
                    "by_judge_king": {"z-ai/glm-5.1": 0.6, "qwen/qwen3.5-397b-a17b": 0.55},
                },
                "king": {
                    "king_version": 3,
                    "model_uri": "org/king@sha256:1",
                    "uid": 1,
                },
            },
        ],
    }

    rec = build_merge_advisor_recommendation(
        dashboard,
        sample_mass_by_uri={"org/donor@sha256:2": 0.62},
        min_duels=1,
        mode="current_king",
    )

    assert rec.base_model_uri == "org/king@sha256:1"
    assert len(rec.donors) >= 1
    assert rec.donors[0].model_uri == "org/donor@sha256:2"
    assert rec.method.method in ("nuslerp", "ties", "task_arithmetic", "dare_ties")
    assert "merge_method:" in rec.mergekit_yaml
    assert rec.base_mergekit_ref in rec.mergekit_yaml
    assert rec.duels_analyzed == 2
    assert rec.sample_mass_duels == 0
    assert rec.donors[0].sample_mass == 0.62


def test_nuslerp_yaml_uses_weights_not_base_model():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 1,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [
            {
                "eval_run_id": "r1",
                "challenger_won": True,
                "win_margin": 0.2,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/donor@sha256:2",
                "uid": 2,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.8, "qwen/qwen3.5-397b-a17b": 0.75},
                    "by_judge_king": {"z-ai/glm-5.1": 0.2, "qwen/qwen3.5-397b-a17b": 0.25},
                },
                "king": {"model_uri": "org/king@sha256:1", "uid": 1},
            }
        ],
    }
    rec = build_merge_advisor_recommendation(dashboard, min_duels=1, mode="current_king")
    if rec.method.method == "nuslerp":
        assert "base_model:" not in rec.mergekit_yaml
        assert "weight:" in rec.mergekit_yaml
        assert "org/king@sha256:1" in rec.mergekit_yaml
        assert "org/donor@sha256:2" in rec.mergekit_yaml


def test_ties_yaml_lists_donors_only_with_king_as_base():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 1,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [],
    }
    for idx, donor in enumerate(("donor-a", "donor-b"), start=1):
        dashboard["eval_runs"].append(
            {
                "eval_run_id": f"r{idx}",
                "challenger_won": True,
                "win_margin": 0.1,
                "finished_at": f"2026-06-27T1{idx}:00:00+00:00",
                "model_uri": f"org/{donor}@sha256:{idx}",
                "uid": idx + 1,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.7, "qwen/qwen3.5-397b-a17b": 0.68},
                    "by_judge_king": {"z-ai/glm-5.1": 0.3, "qwen/qwen3.5-397b-a17b": 0.32},
                },
                "king": {"model_uri": "org/king@sha256:1", "uid": 1},
            }
        )
    rec = build_merge_advisor_recommendation(dashboard, max_donors=2, min_duels=1, mode="current_king")
    if rec.method.method in ("ties", "dare_ties", "task_arithmetic"):
        assert "base_model: org/king@sha256:1" in rec.mergekit_yaml
        assert rec.mergekit_yaml.count("org/king@sha256:1") == 1


def test_sample_challenger_win_mass_from_answers_dict():
    from app.services.albedo_merge_advisor_service import _sample_challenger_win_mass

    rows = [
        {
            "sample_id": "s1",
            "questions": [{"id": "q_01"}, {"id": "q_02"}],
            "judge_results": [
                {
                    "judge_model": "z-ai/glm-5.1",
                    "side": "challenger",
                    "answers": {"q_01": "1", "q_02": "1"},
                },
                {
                    "judge_model": "z-ai/glm-5.1",
                    "side": "previous_king",
                    "answers": {"q_01": "0", "q_02": "0"},
                },
            ],
        },
        {
            "sample_id": "s2",
            "questions": [{"id": "q_01"}],
            "judge_results": [
                {
                    "judge_model": "z-ai/glm-5.1",
                    "side": "challenger",
                    "answers": {"q_01": "0"},
                },
                {
                    "judge_model": "z-ai/glm-5.1",
                    "side": "previous_king",
                    "answers": {"q_01": "1"},
                },
            ],
        },
    ]
    assert _sample_challenger_win_mass(rows) == 0.5


def test_build_merge_advisor_ties_for_multiple_donors():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 2,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk_king",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [],
    }
    for idx, donor in enumerate(("donor-a", "donor-b", "donor-c"), start=1):
        dashboard["eval_runs"].append(
            {
                "eval_run_id": f"r{idx}",
                "challenger_won": True,
                "coronated": idx == 1,
                "win_margin": 0.08 + idx * 0.01,
                "finished_at": f"2026-06-27T1{idx}:00:00+00:00",
                "model_uri": f"org/{donor}@sha256:{idx}",
                "uid": idx + 1,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.7, "qwen/qwen3.5-397b-a17b": 0.68},
                    "by_judge_king": {"z-ai/glm-5.1": 0.3, "qwen/qwen3.5-397b-a17b": 0.32},
                },
                "king": {
                    "king_version": 2,
                    "model_uri": "org/king@sha256:1",
                    "uid": 1,
                },
            }
        )

    rec = build_merge_advisor_recommendation(dashboard, max_donors=3, min_duels=1, mode="current_king")

    assert len(rec.donors) == 3
    assert rec.method.method in ("ties", "dare_ties", "nuslerp", "karcher")
    assert sum(d.merge_weight for d in rec.donors) == pytest.approx(1.0, rel=1e-3)


def test_consensus_only_filters_split_duels():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 1,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [
            {
                "eval_run_id": "split",
                "challenger_won": True,
                "win_margin": 0.02,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/split@sha256:2",
                "uid": 2,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.9, "qwen/qwen3.5-397b-a17b": 0.1},
                    "by_judge_king": {"z-ai/glm-5.1": 0.1, "qwen/qwen3.5-397b-a17b": 0.9},
                },
                "king": {"model_uri": "org/king@sha256:1", "uid": 1},
            },
            {
                "eval_run_id": "unanimous",
                "challenger_won": True,
                "win_margin": 0.15,
                "finished_at": "2026-06-27T11:00:00+00:00",
                "model_uri": "org/strong@sha256:3",
                "uid": 3,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.8, "qwen/qwen3.5-397b-a17b": 0.75},
                    "by_judge_king": {"z-ai/glm-5.1": 0.2, "qwen/qwen3.5-397b-a17b": 0.25},
                },
                "king": {"model_uri": "org/king@sha256:1", "uid": 1},
            },
        ],
    }

    all_rec = build_merge_advisor_recommendation(dashboard, consensus_only=False, min_duels=1, mode="current_king")
    consensus_rec = build_merge_advisor_recommendation(dashboard, consensus_only=True, min_duels=1, mode="current_king")

    assert all_rec.judge_consensus_duels == 1
    assert len(consensus_rec.donors) <= len(all_rec.donors)
    assert any(d.model_uri.endswith("strong@sha256:3") for d in consensus_rec.donors)


def test_multi_king_includes_historical_reign_donor():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 3,
                    "model_uri": "org/king-v3@sha256:1",
                    "hotkey": "hk",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [
            {
                "eval_run_id": "cor_v2",
                "challenger_won": True,
                "coronated": True,
                "king_version": 2,
                "win_margin": 0.2,
                "finished_at": "2026-06-20T10:00:00+00:00",
                "model_uri": "org/king-v2@sha256:2",
                "uid": 2,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.8, "qwen/qwen3.5-397b-a17b": 0.75},
                    "by_judge_king": {"z-ai/glm-5.1": 0.2, "qwen/qwen3.5-397b-a17b": 0.25},
                },
                "king": {"king_version": 1, "model_uri": "org/king-v1@sha256:9", "uid": 9},
            },
            {
                "eval_run_id": "hist",
                "challenger_won": True,
                "coronated": False,
                "win_margin": 0.15,
                "finished_at": "2026-06-21T10:00:00+00:00",
                "model_uri": "org/strong-hist@sha256:3",
                "uid": 3,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.7, "qwen/qwen3.5-397b-a17b": 0.68},
                    "by_judge_king": {"z-ai/glm-5.1": 0.3, "qwen/qwen3.5-397b-a17b": 0.32},
                },
                "king": {"king_version": 2, "model_uri": "org/king-v2@sha256:2", "uid": 2},
            },
            {
                "eval_run_id": "current",
                "challenger_won": False,
                "coronated": False,
                "win_margin": -0.05,
                "finished_at": "2026-06-27T10:00:00+00:00",
                "model_uri": "org/weak@sha256:4",
                "uid": 4,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.4, "qwen/qwen3.5-397b-a17b": 0.45},
                    "by_judge_king": {"z-ai/glm-5.1": 0.6, "qwen/qwen3.5-397b-a17b": 0.55},
                },
                "king": {"king_version": 3, "model_uri": "org/king-v3@sha256:1", "uid": 1},
            },
        ],
    }

    current_only = build_merge_advisor_recommendation(
        dashboard, mode="current_king", min_duels=1, include_past_kings=False
    )
    multi = build_merge_advisor_recommendation(
        dashboard,
        mode="multi_king",
        king_versions=[2],
        include_past_kings=True,
        min_duels=1,
    )

    assert not any(d.model_uri.endswith("strong-hist@sha256:3") for d in current_only.donors)
    assert any(d.model_uri.endswith("strong-hist@sha256:3") for d in multi.donors)
    hist = next(d for d in multi.donors if d.model_uri.endswith("strong-hist@sha256:3"))
    assert hist.historical_duels >= 1
    assert "king_v2_reign" in hist.sources


def test_export_all_methods_yamls():
    dashboard = {
        "reign": {
            "members": [
                {
                    "king_version": 1,
                    "model_uri": "org/king@sha256:1",
                    "hotkey": "hk",
                    "uid": 1,
                    "weight_bps": 2000,
                }
            ]
        },
        "eval_runs": [],
    }
    for idx, donor in enumerate(("donor-a", "donor-b", "donor-c"), start=1):
        dashboard["eval_runs"].append(
            {
                "eval_run_id": f"r{idx}",
                "challenger_won": True,
                "coronated": False,
                "win_margin": 0.08 + idx * 0.01,
                "finished_at": f"2026-06-27T1{idx}:00:00+00:00",
                "model_uri": f"org/{donor}@sha256:{idx}",
                "uid": idx + 1,
                "score_breakdown": {
                    "by_judge": {"z-ai/glm-5.1": 0.7, "qwen/qwen3.5-397b-a17b": 0.68},
                    "by_judge_king": {"z-ai/glm-5.1": 0.3, "qwen/qwen3.5-397b-a17b": 0.32},
                },
                "king": {"model_uri": "org/king@sha256:1", "uid": 1},
            }
        )

    rec = build_merge_advisor_recommendation(
        dashboard, max_donors=3, min_duels=1, export_all_methods=True, mode="current_king"
    )
    assert len(rec.method_yamls) >= 2
    methods = {row.method for row in rec.method_yamls}
    assert rec.method.method in methods
    assert all("merge_method:" in row.yaml for row in rec.method_yamls)
