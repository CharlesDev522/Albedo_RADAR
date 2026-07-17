"""Tests for per-question duel margin decomposition."""

from app.services.albedo_duel_question_margin_service import (
    analyze_question_margin_shares,
    build_question_margin_analysis,
    is_default_question_index,
    question_index_from_id,
)


def _sample_row(
    sample_id: str,
    *,
    ch_q1: str = "1",
    k_q1: str = "0",
    ch_q2: str = "0",
    k_q2: str = "1",
) -> dict:
    return {
        "sample_id": sample_id,
        "questions": [
            {"id": "q_01", "category": "default", "text": "Q1"},
            {"id": "q_02", "category": "pytest", "text": "Q2"},
        ],
        "judge_results": [
            {
                "judge_model": "glm",
                "side": "challenger",
                "answers": {"q_01": ch_q1, "q_02": ch_q2},
            },
            {
                "judge_model": "glm",
                "side": "previous_king",
                "answers": {"q_01": k_q1, "q_02": k_q2},
            },
        ],
    }


def test_question_index_parsing():
    assert question_index_from_id("q_01") == 1
    assert question_index_from_id("q_20") == 20
    assert question_index_from_id("q_21") == 21
    assert is_default_question_index(20) is True
    assert is_default_question_index(21) is False


def test_margin_decomposition_two_questions_equal_share():
    rows = [_sample_row("s1", ch_q1="1", k_q1="0", ch_q2="0", k_q2="1")]
    acc = analyze_question_margin_shares(rows)
    assert acc.observations == 1
    assert acc.sample_count == 1
    # margin 0 overall; each question contributes |50| abs
    assert abs(acc.total_abs - 100.0) < 0.01

    result = build_question_margin_analysis("eval-1", rows)
    assert result.total_observations == 1
    assert len(result.questions) == 2
    assert abs(result.questions[0].share_of_abs_margin_pct - 50.0) < 0.1
    assert abs(result.buckets.default_q1_20_share_pct - 100.0) < 0.1


def test_default_vs_other_bucket():
    questions = [{"id": f"q_{i:02d}", "text": f"Q{i}"} for i in range(1, 22)]
    answers_ch = {f"q_{i:02d}": "1" if i == 21 else "0" for i in range(1, 22)}
    answers_k = {f"q_{i:02d}": "0" for i in range(1, 22)}
    row = {
        "sample_id": "big",
        "questions": questions,
        "judge_results": [
            {"judge_model": "j", "side": "challenger", "answers": answers_ch},
            {"judge_model": "j", "side": "previous_king", "answers": answers_k},
        ],
    }
    result = build_question_margin_analysis("eval-2", [row])
    q21 = next(q for q in result.questions if q.question_id == "q_21")
    assert q21.is_default_q1_20 is False
    assert result.buckets.other_share_pct > 0
    assert result.buckets.default_q1_20_share_pct < 100
