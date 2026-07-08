"""Tests for Albedo scoring-results dual-zero analysis."""

import json

from app.integrations.albedo_scoring_results import parse_scoring_results_jsonl
from app.services.albedo_scoring_analysis_service import (
    analyze_dual_zero_questions,
    build_dual_zero_export_jsonl,
    dual_zero_export_filename,
)


def _sample_row(
    *,
    sample_id: str,
    glm_q1: str = "0",
    qwen_q1: str = "0",
    glm_q2: str = "1",
    qwen_q2: str = "0",
    king_glm_q1: str = "0",
    king_qwen_q1: str = "0",
) -> dict:
    return {
        "sample_id": sample_id,
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
                    "q_01": "ch GLM: no test suite.",
                    "q_02": "ch GLM: pytest -x present.",
                },
            },
            {
                "judge_model": "qwen/qwen3.5-397b-a17b",
                "side": "challenger",
                "answers": {"q_01": qwen_q1, "q_02": qwen_q2},
                "explanations": {
                    "q_01": "ch Qwen: only git diff.",
                    "q_02": "ch Qwen: no -x flag.",
                },
            },
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "previous_king",
                "answers": {"q_01": king_glm_q1, "q_02": "1"},
                "explanations": {
                    "q_01": "k GLM: no test suite.",
                    "q_02": "k GLM: ok",
                },
            },
            {
                "judge_model": "qwen/qwen3.5-397b-a17b",
                "side": "previous_king",
                "answers": {"q_01": king_qwen_q1, "q_02": "1"},
                "explanations": {
                    "q_01": "k Qwen: no test suite.",
                    "q_02": "k Qwen: ok",
                },
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


def test_analyze_dual_zero_requires_both_sides():
    rows = [
        _sample_row(sample_id="dataset/a:1:1"),
        _sample_row(sample_id="dataset/b:2:2", glm_q1="1", qwen_q1="0"),
        _sample_row(sample_id="dataset/c:3:3", king_glm_q1="1", king_qwen_q1="0"),
    ]
    analysis = analyze_dual_zero_questions(rows)

    assert analysis.total_samples == 3
    assert analysis.samples_with_dual_zeros == 1
    assert analysis.total_dual_zero_questions == 1

    sample = analysis.samples[0]
    assert sample.sample_id == "dataset/a:1:1"
    q = sample.questions[0]
    assert q.question_id == "q_01"
    assert q.challenger_glm.startswith("ch GLM")
    assert q.challenger_qwen.startswith("ch Qwen")
    assert q.king_glm.startswith("k GLM")
    assert q.king_qwen.startswith("k Qwen")


def test_analyze_dual_zero_skips_when_any_side_not_zero():
    rows = [_sample_row(sample_id="dataset/d:4:4", king_glm_q1="0", king_qwen_q1="1")]
    analysis = analyze_dual_zero_questions(rows)
    assert analysis.samples_with_dual_zeros == 0


def test_build_dual_zero_export_jsonl_minimal_shape():
    rows = [_sample_row(sample_id="dataset/a:1:1")]
    analysis = analyze_dual_zero_questions(rows)
    analysis.eval_run_id = "fabc90bf-3871-46ef-ac7b-51d2e3b7039b"

    payload = build_dual_zero_export_jsonl(analysis)
    record = json.loads(payload.strip())

    assert set(record.keys()) == {"sample_id", "questions"}
    assert record["sample_id"] == "dataset/a:1:1"
    assert set(record["questions"][0].keys()) == {
        "question_id",
        "text",
        "challenger_glm",
        "challenger_qwen",
        "king_glm",
        "king_qwen",
    }
    assert "eval_run_id" not in record
    assert dual_zero_export_filename(analysis.eval_run_id) == "dual-zero-both-fabc90bf.jsonl"
