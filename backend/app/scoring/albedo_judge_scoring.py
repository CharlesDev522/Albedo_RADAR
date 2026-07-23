"""Albedo binary rubric scoring (ported from albedo_eval_service.judge_core).

Source: https://github.com/tony-dendrite/albedo/tree/dev
"""

from __future__ import annotations

from statistics import mean
from typing import Any

# Defaults match albedo judge_core.py (overridable via env on the validator).
REQUIRES_WEIGHTS: dict[str, float] = {
    "action": 2.0,
    "read": 0.75,
    "neutral": 0.25,
}
SIZE_FACTOR_FLOOR = 0.6
CHALLENGER_WIN_MARGIN = 0.03

_ANSWER_TO_BIT: dict[str, float] = {"1": 1.0, "0": 0.0}


def _answer_bit(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return 1.0 if float(value) == 1.0 else 0.0
    key = str(value).strip().lower()
    if key in {"1", "1.0", "true", "yes"}:
        return 1.0
    if key in {"0", "0.0", "false", "no"}:
        return 0.0
    return None


def requires_weight(value: Any) -> float:
    key = str(value or "neutral").strip().lower() or "neutral"
    return REQUIRES_WEIGHTS.get(key, 1.0)


def judge_yes_rate(
    answers: dict[str, Any],
    questions: list[dict[str, Any]] | None = None,
) -> float | None:
    """Weighted mean of 1/0 answers; size-category questions apply a multiplier."""
    if questions:
        size_ids = {q.get("id") for q in questions if q.get("category") == "size"}
        weight_by_id = {
            q.get("id"): requires_weight(q.get("requires"))
            for q in questions
            if q.get("id")
        }
        num = den = 0.0
        size_num = size_den = 0.0
        for qid, value in answers.items():
            bit = _answer_bit(value)
            if bit is None:
                continue
            if qid in size_ids:
                size_num += bit
                size_den += 1.0
                continue
            weight = weight_by_id.get(qid, 1.0)
            num += weight * bit
            den += weight
        if den <= 0:
            return None
        rate = num / den
        if size_den > 0:
            rate *= SIZE_FACTOR_FLOOR + (1.0 - SIZE_FACTOR_FLOOR) * (size_num / size_den)
        return round(rate, 6)

    bits = [_answer_bit(v) for v in answers.values()]
    bits = [b for b in bits if b is not None]
    return round(mean(bits), 6) if bits else None


def response_score(
    per_judge_answers: dict[str, dict[str, Any]],
    questions: list[dict[str, Any]] | None = None,
) -> float | None:
    rates = [
        rate
        for rate in (judge_yes_rate(answers, questions) for answers in per_judge_answers.values())
        if rate is not None
    ]
    return round(mean(rates), 6) if rates else None


def side_mean_yes_rate(
    row: dict[str, Any],
    side: str,
    questions: list[dict[str, Any]],
) -> float | None:
    """Mean per-judge yes_rate for one side on one sample (matches artifact fields)."""
    rates: list[float] = []
    for result in row.get("judge_results") or []:
        if not isinstance(result, dict):
            continue
        if result.get("side") != side or not result.get("parse_ok"):
            continue
        stored = result.get("yes_rate")
        if stored is not None:
            rates.append(float(stored))
            continue
        answers = result.get("answers") or {}
        computed = judge_yes_rate(answers, questions)
        if computed is not None:
            rates.append(computed)
    return round(mean(rates), 6) if rates else None


def sample_side_scores(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return challenger and king scores for one scoring-results row."""
    if row.get("scored") is False:
        return None, None

    questions = [q for q in (row.get("questions") or []) if isinstance(q, dict)]
    ch = row.get("challenger_score")
    k = row.get("king_score")
    if ch is not None and k is not None:
        return float(ch), float(k)

    if questions:
        ch = side_mean_yes_rate(row, "challenger", questions)
        k = side_mean_yes_rate(row, "previous_king", questions)
        if ch is not None and k is not None:
            return ch, k

        per_judge_ch: dict[str, dict[str, Any]] = {}
        per_judge_k: dict[str, dict[str, Any]] = {}
        for result in row.get("judge_results") or []:
            if not isinstance(result, dict) or not result.get("parse_ok"):
                continue
            model = str(result.get("judge_model") or "")
            if not model:
                continue
            answers = result.get("answers") or {}
            if result.get("side") == "challenger":
                per_judge_ch[model] = answers
            elif result.get("side") == "previous_king":
                per_judge_k[model] = answers
        return response_score(per_judge_ch, questions), response_score(per_judge_k, questions)

    return None, None


def aggregate_scores_from_records(records: list[dict[str, Any]]) -> dict[str, float | None]:
    """Replicate dashboard duel means from scoring-results rows."""
    valid: list[tuple[float, float]] = []
    for row in records:
        ch, k = sample_side_scores(row)
        if ch is None or k is None:
            continue
        valid.append((ch, k))

    if not valid:
        return {
            "score_challenger": None,
            "score_king": None,
            "win_margin": None,
            "valid_samples": 0,
        }

    ch_mean = round(mean(ch for ch, _ in valid), 6)
    k_mean = round(mean(k for _, k in valid), 6)
    return {
        "score_challenger": ch_mean,
        "score_king": k_mean,
        "win_margin": round(ch_mean - k_mean, 6),
        "valid_samples": len(valid),
    }
