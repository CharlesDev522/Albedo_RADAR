"""Tests for category / requires scoring-results analysis."""

import pytest

from app.scoring.albedo_judge_scoring import (
    aggregate_decomposed_metric,
    decompose_judge_yes_rate,
    requires_weight,
)
from app.services.albedo_scoring_analysis_service import (
    analyze_scoring_results_category_requires,
)


def _questions() -> list[dict]:
    return [
        {"id": "q_01", "category": "tests", "requires": "action", "text": "Runs tests?"},
        {"id": "q_02", "category": "docs", "requires": "read", "text": "Reads README?"},
        {"id": "q_03", "category": "tests", "requires": "neutral", "text": "Neutral check?"},
    ]


def _sample_row(
    *,
    sample_id: str = "s1",
    action_ch: str = "1",
    action_k: str = "0",
    read_ch: str = "1",
    read_k: str = "1",
    neutral_ch: str = "0",
    neutral_k: str = "0",
    ch_score: float = 0.36,
    k_score: float = 0.30,
) -> dict:
    questions = _questions()
    return {
        "sample_id": sample_id,
        "scored": True,
        "challenger_score": ch_score,
        "king_score": k_score,
        "questions": questions,
        "judge_results": [
            {
                "judge_model": "z-ai/glm-5.2",
                "side": "challenger",
                "parse_ok": True,
                "yes_rate": ch_score,
                "answers": {"q_01": action_ch, "q_02": read_ch, "q_03": neutral_ch},
            },
            {
                "judge_model": "z-ai/glm-5.2",
                "side": "previous_king",
                "parse_ok": True,
                "yes_rate": k_score,
                "answers": {"q_01": action_k, "q_02": read_k, "q_03": neutral_k},
            },
        ],
    }


def test_requires_weight_mapping():
    assert requires_weight("action") == 2.0
    assert requires_weight("read") == 0.75
    assert requires_weight("neutral") == 0.25


def test_decompose_requires_contributions_sum_to_final():
    questions = _questions()
    answers = {"q_01": "1", "q_02": "1", "q_03": "0"}
    dec = decompose_judge_yes_rate(answers, questions, group_by="requires")
    contrib_sum = sum(part["contribution"] for part in dec["buckets"].values())
    assert dec["final_rate"] == pytest.approx(contrib_sum, abs=1e-6)
    assert dec["final_rate"] == dec["base_rate"]


def test_decompose_with_size_multiplier():
    questions = [
        {"id": "q_01", "category": "work", "requires": "action"},
        {"id": "q_sz", "category": "size", "requires": "neutral"},
    ]
    answers = {"q_01": "1", "q_sz": "0"}
    dec = decompose_judge_yes_rate(answers, questions, group_by="requires")
    contrib_sum = sum(part["contribution"] for part in dec["buckets"].values())
    assert dec["base_rate"] == 1.0
    assert dec["size_multiplier"] == pytest.approx(0.6, abs=1e-6)
    assert dec["final_rate"] == pytest.approx(0.6, abs=1e-6)
    assert dec["final_rate"] == pytest.approx(contrib_sum, abs=1e-6)


def test_analyze_replicates_dashboard_scores():
    dashboard = {
        "score_challenger": 0.36,
        "score_king": 0.30,
        "win_margin": 0.06,
    }
    analysis = analyze_scoring_results_category_requires(
        [_sample_row()],
        eval_run_id="eval-1",
        dashboard_run=dashboard,
    )

    assert analysis.overall.jsonl_matches_dashboard is True
    assert analysis.overall.weighted_challenger_score_pct == pytest.approx(36.0, abs=0.01)
    assert analysis.overall.requires_contrib_matches_duel is True

    requires = {row.key: row for row in analysis.requires}
    assert "_total" in requires
    assert requires["_total"].weighted_challenger_score == pytest.approx(36.0, abs=0.1)

    body_sum_ch = sum(
        requires[k].weighted_challenger_score
        for k in requires
        if k not in {"size", "_total"}
    )
    assert body_sum_ch == pytest.approx(requires["_total"].weighted_challenger_score, abs=0.1)


def test_analyze_requires_buckets():
    analysis = analyze_scoring_results_category_requires([_sample_row()])
    by_req = {row.key: row for row in analysis.requires if row.key not in {"_total", "size"}}
    assert by_req["action"].weight_multiplier == 2.0
    assert by_req["action"].challenger_yes_rate == pytest.approx(100.0, abs=0.1)
    assert by_req["action"].king_yes_rate == pytest.approx(0.0, abs=0.1)
    assert by_req["action"].weighted_challenger_score > by_req["action"].weighted_king_score


def test_duel_margin_can_differ_from_requires_margin_when_size_hurts_challenger():
    questions = [
        {"id": "q_a1", "category": "work", "requires": "action"},
        {"id": "q_a2", "category": "work", "requires": "action"},
        {"id": "q_sz", "category": "size", "requires": "neutral"},
    ]

    def row(sample_id: str, *, ch_score: float, k_score: float, ch_ans: dict, k_ans: dict) -> dict:
        return {
            "sample_id": sample_id,
            "scored": True,
            "challenger_score": ch_score,
            "king_score": k_score,
            "questions": questions,
            "judge_results": [
                {
                    "judge_model": "z-ai/glm-5.2",
                    "side": "challenger",
                    "parse_ok": True,
                    "yes_rate": ch_score,
                    "answers": ch_ans,
                },
                {
                    "judge_model": "z-ai/glm-5.2",
                    "side": "previous_king",
                    "parse_ok": True,
                    "yes_rate": k_score,
                    "answers": k_ans,
                },
            ],
        }

    win = row(
        "win",
        ch_score=0.72,
        k_score=0.28,
        ch_ans={"q_a1": "1", "q_a2": "1", "q_sz": "1"},
        k_ans={"q_a1": "0", "q_a2": "0", "q_sz": "1"},
    )
    loss = row(
        "loss",
        ch_score=0.05,
        k_score=0.95,
        ch_ans={"q_a1": "0", "q_a2": "0", "q_sz": "0"},
        k_ans={"q_a1": "1", "q_a2": "1", "q_sz": "1"},
    )

    analysis = analyze_scoring_results_category_requires(
        [win, win, loss],
        dashboard_run={"score_challenger": 0.496667, "score_king": 0.503333, "win_margin": -0.006666},
    )

    assert analysis.overall.jsonl_matches_dashboard is True
    assert analysis.overall.requires_contrib_matches_duel is True
    requires = {row.key: row for row in analysis.requires}
    assert requires["action"].challenger_yes_rate > requires["action"].king_yes_rate
    assert analysis.overall.weighted_margin_pct < 0
    body_sum_margin = sum(
        requires[k].weighted_margin for k in requires if k not in {"size", "_total"}
    )
    assert body_sum_margin == pytest.approx(requires["_total"].weighted_margin, abs=0.2)


def test_analyze_size_row_only_on_requires_not_categories():
    questions = [
        {"id": "q_01", "category": "work", "requires": "action"},
        {"id": "q_sz", "category": "size", "requires": "neutral"},
    ]
    row = {
        "sample_id": "s1",
        "scored": True,
        "challenger_score": 0.6,
        "king_score": 0.6,
        "questions": questions,
        "judge_results": [
            {
                "judge_model": "j1",
                "side": "challenger",
                "parse_ok": True,
                "yes_rate": 0.6,
                "answers": {"q_01": "1", "q_sz": "0"},
            },
            {
                "judge_model": "j1",
                "side": "previous_king",
                "parse_ok": True,
                "yes_rate": 0.6,
                "answers": {"q_01": "1", "q_sz": "0"},
            },
        ],
    }
    analysis = analyze_scoring_results_category_requires([row])

    requires_keys = {r.key for r in analysis.requires}
    category_keys = {r.key for r in analysis.categories}
    assert "size" in requires_keys
    assert "size" not in category_keys

    size_row = next(r for r in analysis.requires if r.key == "size")
    assert size_row.weighted_challenger_score == 0.0
    assert size_row.weighted_king_score == 0.0
    assert "multiplier" in (size_row.note or "").lower()

    body_sum_ch = sum(
        r.weighted_challenger_score for r in analysis.requires if r.key not in {"size", "_total"}
    )
    assert body_sum_ch == pytest.approx(analysis.requires[-1].weighted_challenger_score, abs=0.1)
    assert analysis.overall.categories_contrib_matches_duel is True


def test_aggregate_decomposed_metric_matches_sample_then_duel_mean():
    per_sample = [[0.8, 0.6], [0.4, 0.2]]
    assert aggregate_decomposed_metric(per_sample) == pytest.approx(0.5, abs=1e-6)
