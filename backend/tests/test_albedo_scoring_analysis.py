"""Tests for category / requires scoring-results analysis."""

from app.services.albedo_scoring_analysis_service import (
    analyze_scoring_results_category_requires,
    requires_weight,
)


def _sample_row(
    *,
    sample_id: str = "s1",
    action_ch: str = "1",
    action_k: str = "0",
    read_ch: str = "1",
    read_k: str = "1",
) -> dict:
    return {
        "sample_id": sample_id,
        "questions": [
            {
                "id": "q_01",
                "category": "tests",
                "requires": "action",
                "text": "Runs tests?",
            },
            {
                "id": "q_02",
                "category": "docs",
                "requires": "read",
                "text": "Reads README?",
            },
            {
                "id": "q_03",
                "category": "tests",
                "requires": "neutral",
                "text": "Neutral check?",
            },
        ],
        "judge_results": [
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "challenger",
                "answers": {"q_01": action_ch, "q_02": read_ch, "q_03": "0"},
            },
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "previous_king",
                "answers": {"q_01": action_k, "q_02": read_k, "q_03": "0"},
            },
        ],
    }


def test_requires_weight_mapping():
    assert requires_weight("action") == 1.5
    assert requires_weight("read") == 1.0
    assert requires_weight("neutral") == 0.5
    assert requires_weight("netural") == 0.5


def test_analyze_category_and_requires_buckets():
    analysis = analyze_scoring_results_category_requires(
        [_sample_row()],
        eval_run_id="eval-1",
        challenger_label="org/challenger",
        king_label="org/king",
    )

    assert analysis.total_samples == 1
    assert analysis.judge_observations == 1
    assert analysis.question_slots == 3

    by_cat = {row.key: row for row in analysis.categories}
    assert "tests" in by_cat
    assert "docs" in by_cat
    assert by_cat["tests"].question_slots == 2
    assert by_cat["docs"].question_slots == 1
    assert by_cat["tests"].weighted_margin > 0

    by_req = {row.key: row for row in analysis.requires}
    assert by_req["action"].weight_multiplier == 1.5
    assert by_req["read"].weight_multiplier == 1.0
    assert by_req["neutral"].weight_multiplier == 0.5
    assert by_req["action"].challenger_yes_rate == 100.0
    assert by_req["action"].king_yes_rate == 0.0


def test_analyze_aggregates_multiple_samples_and_judges():
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
