"""Tests for category / requires scoring-results analysis."""

import pytest

from app.services.albedo_scoring_analysis_service import (
    analyze_scoring_results_category_requires,
    requires_weight,
    weighted_observation_margin,
    weighted_side_score,
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
) -> dict:
    return {
        "sample_id": sample_id,
        "questions": _questions(),
        "judge_results": [
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "challenger",
                "answers": {"q_01": action_ch, "q_02": read_ch, "q_03": neutral_ch},
            },
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "previous_king",
                "answers": {"q_01": action_k, "q_02": read_k, "q_03": neutral_k},
            },
        ],
    }


def test_requires_weight_mapping():
    assert requires_weight("action") == 1.5
    assert requires_weight("read") == 1.0
    assert requires_weight("neutral") == 0.5
    assert requires_weight("netural") == 0.5


def test_weighted_side_score_formula():
    questions = _questions()
    ch_answers = {"q_01": "1", "q_02": "1", "q_03": "0"}
    # (1*1.5 + 1*1.0 + 0*0.5) / (1.5 + 1.0 + 0.5) = 2.5 / 3.0
    assert weighted_side_score(ch_answers, questions) == 5.0 / 6.0


def test_weighted_observation_margin_formula():
    questions = _questions()
    ch_answers = {"q_01": "1", "q_02": "1", "q_03": "0"}
    k_answers = {"q_01": "0", "q_02": "1", "q_03": "0"}
    ch, k, margin = weighted_observation_margin(ch_answers, k_answers, questions)
    assert ch == 5.0 / 6.0
    assert k == 1.0 / 3.0
    assert margin == ch - k


def test_analyze_category_and_requires_buckets():
    analysis = analyze_scoring_results_category_requires(
        [_sample_row()],
        eval_run_id="eval-1",
        challenger_label="org/challenger",
        king_label="org/king",
        dashboard_run={
            "score_challenger": 5.0 / 6.0,
            "score_king": 1.0 / 3.0,
            "win_margin": 5.0 / 6.0 - 1.0 / 3.0,
        },
    )

    assert analysis.total_samples == 1
    assert analysis.judge_observations == 1
    assert analysis.question_slots == 3
    assert analysis.overall.observation_count == 1
    assert abs(analysis.overall.weighted_challenger_score_pct - (5.0 / 6.0) * 100.0) < 0.01
    assert abs(analysis.overall.weighted_king_score_pct - (1.0 / 3.0) * 100.0) < 0.01
    assert analysis.overall.dashboard_score_challenger == pytest.approx(5.0 / 6.0)

    by_cat = {row.key: row for row in analysis.categories}
    assert by_cat["tests"].question_slots == 2
    assert by_cat["docs"].question_slots == 1
    # tests bucket: q_01 (ch=1,k=0,w=1.5) + q_03 (ch=0,k=0,w=0.5)
    # weighted margin = (1.5 + 0) / 2.0 * 100 = 75%
    assert by_cat["tests"].weighted_margin == 75.0

    by_req = {row.key: row for row in analysis.requires}
    assert by_req["action"].weight_multiplier == 1.5
    assert by_req["action"].weighted_margin == 100.0
    assert by_req["read"].weighted_margin == 0.0


def test_analyze_aggregates_multiple_observations():
    rows = [
        _sample_row(sample_id="s1"),
        _sample_row(sample_id="s2", action_ch="0", action_k="1"),
    ]
    analysis = analyze_scoring_results_category_requires(rows)
    assert analysis.total_samples == 2
    assert analysis.judge_observations == 2
    assert analysis.question_slots == 6
    action = next(row for row in analysis.requires if row.key == "action")
    assert action.question_slots == 2
    assert action.challenger_yes_rate == 50.0
    assert action.king_yes_rate == 50.0
    assert analysis.overall.observation_count == 2
