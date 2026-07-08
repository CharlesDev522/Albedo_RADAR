"""Tests for Albedo scoring-results dual-zero analysis."""

import json

from app.integrations.albedo_scoring_results import parse_scoring_results_jsonl
from app.services.albedo_scoring_analysis_service import analyze_dual_zero_questions


def _sample_row(
    *,
    sample_id: str,
    glm_q1: str = "0",
    qwen_q1: str = "0",
    glm_q2: str = "1",
    qwen_q2: str = "0",
) -> dict:
    return {
        "sample_id": sample_id,
        "challenger_score": 0.4,
        "king_score": 0.6,
        "questions": [
            {"id": "q_01", "category": "overall", "text": "Runs test suite?"},
            {"id": "q_02", "category": "pytest", "text": "Uses pytest -x?"},
        ],
        "judge_results": [
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "challenger",
                "answers": {"q_01": glm_q1, "q_02": glm_q2},
                "explanations": {
                    "q_01": "GLM: no test suite command found.",
                    "q_02": "GLM: pytest -x present.",
                },
            },
            {
                "judge_model": "qwen/qwen3.5-397b-a17b",
                "side": "challenger",
                "answers": {"q_01": qwen_q1, "q_02": qwen_q2},
                "explanations": {
                    "q_01": "Qwen: only git diff was run.",
                    "q_02": "Qwen: no -x flag.",
                },
            },
            {
                "judge_model": "deepseek/deepseek-v3.2",
                "side": "challenger",
                "answers": {"q_01": "0", "q_02": "1"},
                "explanations": {"q_01": "DS reason", "q_02": "DS ok"},
            },
        ],
    }


def test_parse_scoring_results_jsonl():
    payload = "\n".join(
        [
            json.dumps({"sample_id": "a", "questions": [], "judge_results": []}),
            "",
            json.dumps({"sample_id": "b", "questions": [], "judge_results": []}),
        ]
    )
    rows = parse_scoring_results_jsonl(payload)
    assert len(rows) == 2
    assert rows[0]["sample_id"] == "a"


def test_analyze_dual_zero_questions_groups_by_sample():
    rows = [
        _sample_row(sample_id="dataset/a:1:1"),
        _sample_row(sample_id="dataset/b:2:2", glm_q1="1", qwen_q1="0"),
    ]
    analysis = analyze_dual_zero_questions(rows)

    assert analysis.total_samples == 2
    assert analysis.samples_with_dual_zeros == 1
    assert analysis.total_dual_zero_questions == 1
    assert analysis.glm_judge == "z-ai/glm-5.1"
    assert analysis.qwen_judge == "qwen/qwen3.5-397b-a17b"

    sample = analysis.samples[0]
    assert sample.sample_id == "dataset/a:1:1"
    assert sample.sample_label == "1:1"
    assert sample.dual_zero_count == 1
    assert sample.questions[0].question_id == "q_01"
    assert "test suite" in sample.questions[0].text
    assert sample.questions[0].glm_explanation.startswith("GLM:")
    assert sample.questions[0].qwen_explanation.startswith("Qwen:")


def test_analyze_dual_zero_skips_when_only_one_judge_is_zero():
    rows = [_sample_row(sample_id="dataset/c:3:3", glm_q1="1", qwen_q1="0")]
    analysis = analyze_dual_zero_questions(rows)
    assert analysis.samples_with_dual_zeros == 0
    assert analysis.total_dual_zero_questions == 0
