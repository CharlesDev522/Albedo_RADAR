"""Tests for Albedo judge scoring replication."""

import pytest

from app.scoring.albedo_judge_scoring import (
    CHALLENGER_WIN_MARGIN,
    REQUIRES_WEIGHTS,
    aggregate_scores_from_records,
    decompose_judge_yes_rate,
    judge_yes_rate,
    response_score,
    sample_side_scores,
)


def test_requires_weights_match_albedo_defaults():
    assert REQUIRES_WEIGHTS["action"] == 2.0
    assert REQUIRES_WEIGHTS["read"] == 0.75
    assert REQUIRES_WEIGHTS["neutral"] == 0.25
    assert CHALLENGER_WIN_MARGIN == 0.03


def test_judge_yes_rate_weighted_requires():
    questions = [
        {"id": "q_01", "category": "progress", "requires": "action"},
        {"id": "q_02", "category": "grounding", "requires": "read"},
        {"id": "q_03", "category": "protocol", "requires": "neutral"},
    ]
    answers = {"q_01": "1", "q_02": "1", "q_03": "0"}
    assert judge_yes_rate(answers, questions) == round(2.75 / 3.0, 6)


def test_judge_yes_rate_applies_size_multiplier():
    questions = [
        {"id": "q_01", "category": "progress", "requires": "action"},
        {"id": "q_02", "category": "size", "requires": "neutral"},
    ]
    answers = {"q_01": "1", "q_02": "0"}
    base = 1.0
    expected = round(base * (0.6 + 0.4 * 0.0), 6)
    assert judge_yes_rate(answers, questions) == expected


def test_decompose_matches_judge_yes_rate():
    questions = [
        {"id": "q_01", "category": "progress", "requires": "action"},
        {"id": "q_02", "category": "size", "requires": "neutral"},
    ]
    answers = {"q_01": "1", "q_02": "0"}
    dec = decompose_judge_yes_rate(answers, questions, group_by="requires")
    assert dec["final_rate"] == judge_yes_rate(answers, questions)
    contrib_sum = sum(part["contribution"] for part in dec["buckets"].values())
    assert dec["final_rate"] == pytest.approx(contrib_sum, abs=1e-6)


def test_aggregate_scores_from_records_matches_dashboard_pattern():
    records = [
        {
            "sample_id": "s1",
            "scored": True,
            "challenger_score": 0.36,
            "king_score": 0.30,
            "questions": [],
            "judge_results": [],
        },
        {
            "sample_id": "s2",
            "scored": True,
            "challenger_score": 0.36,
            "king_score": 0.30,
            "questions": [],
            "judge_results": [],
        },
    ]
    summary = aggregate_scores_from_records(records)
    assert summary["score_challenger"] == 0.36
    assert summary["score_king"] == 0.30
    assert summary["win_margin"] == 0.06
    assert summary["valid_samples"] == 2


def test_sample_side_scores_recomputes_from_yes_rate():
    row = {
        "scored": True,
        "questions": [{"id": "q_01", "category": "progress", "requires": "action"}],
        "judge_results": [
            {
                "side": "challenger",
                "judge_model": "j1",
                "parse_ok": True,
                "yes_rate": 0.8,
                "answers": {"q_01": "1"},
            },
            {
                "side": "previous_king",
                "judge_model": "j1",
                "parse_ok": True,
                "yes_rate": 0.4,
                "answers": {"q_01": "0"},
            },
        ],
    }
    ch, k = sample_side_scores(row)
    assert ch == 0.8
    assert k == 0.4


def test_response_score_averages_judges():
    questions = [{"id": "q_01", "category": "progress", "requires": "read"}]
    per_judge = {
        "j1": {"q_01": "1"},
        "j2": {"q_01": "0"},
    }
    assert response_score(per_judge, questions) == 0.5
