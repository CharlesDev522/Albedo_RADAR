"""Tests for Albedo scoring-results dual-zero analysis."""

import json

from app.integrations.albedo_scoring_results import parse_scoring_results_jsonl
from app.services.albedo_scoring_analysis_service import (
    analyze_dual_zero_questions,
    build_dual_zero_export,
    build_dual_zero_export_jsonl,
    build_sample_export_json,
    duel_export_filename,
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
    ]
    analysis = analyze_dual_zero_questions(rows)

    assert analysis.total_samples == 2
    assert analysis.samples_with_dual_zeros == 1
    assert analysis.samples[0].sample_id == "dataset/a:1:1"


def test_duel_export_filename():
    assert duel_export_filename(king_uid=50, challenger_uid=205, winner="king") == "50 vs 205 king.jsonl"
    assert (
        duel_export_filename(king_uid=50, challenger_uid=205, winner="challenger")
        == "50 vs 205 challenger.jsonl"
    )


def test_build_dual_zero_export_jsonl_is_multiline_jsonl():
    rows = [
        _sample_row(sample_id="dataset/a:1:1"),
        _sample_row(sample_id="dataset/e:5:5"),
    ]
    analysis = analyze_dual_zero_questions(rows)
    payload = build_dual_zero_export_jsonl(analysis)
    lines = [line for line in payload.splitlines() if line.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["sample_id"] == "dataset/a:1:1"


def test_build_dual_zero_export_single_jsonl_file():
    rows = [_sample_row(sample_id="dataset/a:1:1")]
    analysis = analyze_dual_zero_questions(rows)
    payload = build_dual_zero_export(
        analysis,
        king_uid=50,
        challenger_uid=205,
        winner="king",
    )

    assert payload.media_type == "application/x-ndjson"
    assert payload.filename == "50 vs 205 king.jsonl"
    lines = payload.content.decode().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record.keys()) == {"sample_id", "questions"}
    assert set(record["questions"][0].keys()) == {
        "question_id",
        "text",
        "challenger_glm",
        "challenger_qwen",
        "king_glm",
        "king_qwen",
    }
    assert record["questions"][0]["text"] == "Runs test suite?"


def test_build_sample_export_json_minimal_shape():
    rows = [_sample_row(sample_id="dataset/a:1:1")]
    analysis = analyze_dual_zero_questions(rows)
    record = json.loads(build_sample_export_json(analysis.samples[0]).strip())
    assert "eval_run_id" not in record
    assert record["sample_id"] == "dataset/a:1:1"
