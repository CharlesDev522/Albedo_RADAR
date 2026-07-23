"""Tests for category / requires scoring-results analysis."""

import pytest

from app.services.albedo_scoring_analysis_service import (
    analyze_scoring_results_category_requires,
)
from app.scoring.albedo_judge_scoring import requires_weight


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
    assert analysis.overall.weighted_king_score_pct == pytest.approx(30.0, abs=0.01)
    assert analysis.overall.weighted_margin_pct == pytest.approx(6.0, abs=0.01)


def test_analyze_category_and_requires_buckets_use_observation_means():
    analysis = analyze_scoring_results_category_requires([_sample_row()])

    by_cat = {row.key: row for row in analysis.categories}
    assert by_cat["tests"].question_slots == 1
    assert by_cat["docs"].question_slots == 1

    by_req = {row.key: row for row in analysis.requires}
    assert by_req["action"].weight_multiplier == 2.0
    assert by_req["read"].weight_multiplier == 0.75
    assert by_req["neutral"].weight_multiplier == 0.25
  # action: ch=1, k=0 on single observation
    assert by_req["action"].challenger_yes_rate == pytest.approx(100.0, abs=0.1)
    assert by_req["action"].king_yes_rate == pytest.approx(0.0, abs=0.1)


def test_slot_pool_can_disagree_with_duel_when_samples_differ():
    """More slot observations can favor challenger while per-sample means favor king."""
    questions = [
        {"id": "q_a1", "category": "work", "requires": "action"},
        {"id": "q_a2", "category": "work", "requires": "action"},
        {"id": "q_sz", "category": "size", "requires": "neutral"},
    ]

    def row(sample_id: str, *, ch_score: float, k_score: float, ch_answers: dict, k_answers: dict) -> dict:
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
                    "answers": ch_answers,
                },
                {
                    "judge_model": "z-ai/glm-5.2",
                    "side": "previous_king",
                    "parse_ok": True,
                    "yes_rate": k_score,
                    "answers": k_answers,
                },
            ],
        }

    win = row(
        "win",
        ch_score=0.72,
        k_score=0.28,
        ch_answers={"q_a1": "1", "q_a2": "1", "q_sz": "1"},
        k_answers={"q_a1": "0", "q_a2": "0", "q_sz": "1"},
    )
    win2 = row(
        "win2",
        ch_score=0.72,
        k_score=0.28,
        ch_answers={"q_a1": "1", "q_a2": "1", "q_sz": "1"},
        k_answers={"q_a1": "0", "q_a2": "0", "q_sz": "1"},
    )
    loss = row(
        "loss",
        ch_score=0.05,
        k_score=0.95,
        ch_answers={"q_a1": "0", "q_a2": "0", "q_sz": "0"},
        k_answers={"q_a1": "1", "q_a2": "1", "q_sz": "1"},
    )

    analysis = analyze_scoring_results_category_requires(
        [win, win2, loss],
        dashboard_run={"score_challenger": 0.496667, "score_king": 0.503333, "win_margin": -0.006666},
    )

    assert analysis.overall.jsonl_matches_dashboard is True
    assert analysis.overall.weighted_margin_pct < 0
    assert analysis.overall.slot_pooled_margin_pct is not None
    assert analysis.overall.slot_pooled_margin_pct > 0
    assert analysis.overall.bucket_margin_matches_duel is False
    by_req = {row.key: row for row in analysis.requires}
    assert by_req["action"].weighted_margin > 0
