"""Category and requires breakdown for one duel's scoring-results.jsonl."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.schemas.albedo_scoring_analysis import (
    AlbedoScoringBucketRow,
    AlbedoScoringDuelAnalysis,
    AlbedoScoringFormula,
    AlbedoScoringOverallSummary,
)

CHALLENGER_SIDE = "challenger"
KING_SIDE_RAW = "previous_king"

REQUIRES_WEIGHTS: dict[str, float] = {
    "action": 1.5,
    "read": 1.0,
    "neutral": 0.5,
    "netural": 0.5,
}


def normalize_requires(value: Any) -> str:
    key = str(value or "unknown").strip().lower()
    if not key:
        return "unknown"
    return key


def requires_weight(value: Any) -> float:
    return REQUIRES_WEIGHTS.get(normalize_requires(value), 1.0)


def normalize_category(value: Any) -> str:
    key = str(value or "uncategorized").strip()
    return key or "uncategorized"


def _answer_is_one(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) == 1.0
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def _answer_value(value: Any) -> float:
    return 1.0 if _answer_is_one(value) else 0.0


def weighted_side_score(
    answers: dict[str, Any],
    questions: list[dict[str, Any]],
) -> float:
    """Weighted yes-rate for one side on one sample×judge observation (0..1)."""
    weight_sum = 0.0
    score_sum = 0.0
    for question in questions:
        qid = str(question.get("id") or "")
        if not qid:
            continue
        weight = requires_weight(question.get("requires"))
        weight_sum += weight
        score_sum += _answer_value(answers.get(qid)) * weight
    if weight_sum <= 0:
        return 0.0
    return score_sum / weight_sum


def weighted_observation_margin(
    challenger_answers: dict[str, Any],
    king_answers: dict[str, Any],
    questions: list[dict[str, Any]],
) -> tuple[float, float, float]:
    """Return challenger score, king score, and margin in 0..1 scale."""
    ch = weighted_side_score(challenger_answers, questions)
    k = weighted_side_score(king_answers, questions)
    return ch, k, ch - k


@dataclass
class _BucketAccum:
    observations: int = 0
    challenger_yes: int = 0
    king_yes: int = 0
    weighted_ch_sum: float = 0.0
    weighted_k_sum: float = 0.0
    weight_sum: float = 0.0
    abs_margin_weighted_sum: float = 0.0


@dataclass
class _AnalysisAccum:
    categories: dict[str, _BucketAccum] = field(default_factory=lambda: defaultdict(_BucketAccum))
    requires: dict[str, _BucketAccum] = field(default_factory=lambda: defaultdict(_BucketAccum))
    total_samples: int = 0
    judge_observations: int = 0
    question_slots: int = 0
    total_abs_margin_weighted: float = 0.0
    observation_ch_scores: list[float] = field(default_factory=list)
    observation_k_scores: list[float] = field(default_factory=list)
    observation_margins: list[float] = field(default_factory=list)


def _accumulate_slot(
    acc: _BucketAccum,
    *,
    challenger_yes: bool,
    king_yes: bool,
    weight: float,
) -> float:
    ch = 1.0 if challenger_yes else 0.0
    k = 1.0 if king_yes else 0.0
    acc.observations += 1
    if challenger_yes:
        acc.challenger_yes += 1
    if king_yes:
        acc.king_yes += 1
    acc.weighted_ch_sum += ch * weight
    acc.weighted_k_sum += k * weight
    acc.weight_sum += weight
    abs_margin = abs(ch - k) * weight
    acc.abs_margin_weighted_sum += abs_margin
    return abs_margin


def _bucket_row(
    key: str,
    acc: _BucketAccum,
    *,
    total_abs_margin: float,
    show_requires_weight: bool = False,
) -> AlbedoScoringBucketRow:
    obs = acc.observations
    weight_sum = acc.weight_sum or 1.0
    share = (
        acc.abs_margin_weighted_sum / total_abs_margin * 100.0
        if total_abs_margin > 0
        else 0.0
    )
    multiplier = requires_weight(key) if show_requires_weight else None
    return AlbedoScoringBucketRow(
        key=key,
        weight_multiplier=multiplier,
        question_slots=obs,
        challenger_yes_rate=(acc.challenger_yes / obs * 100.0) if obs else 0.0,
        king_yes_rate=(acc.king_yes / obs * 100.0) if obs else 0.0,
        weighted_challenger_score=acc.weighted_ch_sum / weight_sum * 100.0,
        weighted_king_score=acc.weighted_k_sum / weight_sum * 100.0,
        weighted_margin=(acc.weighted_ch_sum - acc.weighted_k_sum) / weight_sum * 100.0,
        share_of_abs_weighted_margin_pct=share,
    )


def _overall_summary(
    acc: _AnalysisAccum,
    *,
    dashboard_run: dict[str, Any] | None = None,
) -> AlbedoScoringOverallSummary:
    obs = len(acc.observation_margins)
    if obs == 0:
        return AlbedoScoringOverallSummary()

    ch_avg = sum(acc.observation_ch_scores) / obs * 100.0
    k_avg = sum(acc.observation_k_scores) / obs * 100.0
    margin_avg = sum(acc.observation_margins) / obs * 100.0

    dashboard_ch = None
    dashboard_k = None
    dashboard_margin = None
    if dashboard_run:
        raw_ch = dashboard_run.get("score_challenger")
        raw_k = dashboard_run.get("score_king")
        raw_margin = dashboard_run.get("win_margin")
        if raw_ch is not None:
            dashboard_ch = float(raw_ch)
        if raw_k is not None:
            dashboard_k = float(raw_k)
        if raw_margin is not None:
            dashboard_margin = float(raw_margin)

    return AlbedoScoringOverallSummary(
        observation_count=obs,
        weighted_challenger_score_pct=round(ch_avg, 4),
        weighted_king_score_pct=round(k_avg, 4),
        weighted_margin_pct=round(margin_avg, 4),
        dashboard_score_challenger=dashboard_ch,
        dashboard_score_king=dashboard_k,
        dashboard_win_margin=dashboard_margin,
    )


def analyze_scoring_results_category_requires(
    rows: list[dict[str, Any]],
    *,
    eval_run_id: str = "",
    finished_at: str | None = None,
    challenger_label: str = "",
    king_label: str | None = None,
    challenger_won: bool = False,
    coronated: bool = False,
    dashboard_run: dict[str, Any] | None = None,
) -> AlbedoScoringDuelAnalysis:
    """Aggregate question answers by category and requires for one duel JSONL."""
    acc = _AnalysisAccum()

    for row in rows:
        questions = [q for q in (row.get("questions") or []) if isinstance(q, dict) and q.get("id")]
        if not questions:
            continue
        acc.total_samples += 1
        meta_by_id = {str(q["id"]): q for q in questions}
        question_list = list(meta_by_id.values())

        by_judge: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for entry in row.get("judge_results") or []:
            if not isinstance(entry, dict):
                continue
            side = entry.get("side")
            judge = str(entry.get("judge_model") or "")
            if side in (CHALLENGER_SIDE, KING_SIDE_RAW) and judge:
                by_judge[judge][str(side)] = entry

        for sides in by_judge.values():
            ch = sides.get(CHALLENGER_SIDE)
            k = sides.get(KING_SIDE_RAW)
            if not ch or not k:
                continue
            ch_ans = ch.get("answers") or {}
            k_ans = k.get("answers") or {}
            acc.judge_observations += 1

            ch_score, k_score, margin = weighted_observation_margin(ch_ans, k_ans, question_list)
            acc.observation_ch_scores.append(ch_score)
            acc.observation_k_scores.append(k_score)
            acc.observation_margins.append(margin)

            for qid, question in meta_by_id.items():
                category = normalize_category(question.get("category"))
                requires = normalize_requires(question.get("requires"))
                weight = requires_weight(requires)
                ch_yes = _answer_is_one(ch_ans.get(qid))
                k_yes = _answer_is_one(k_ans.get(qid))
                acc.question_slots += 1

                abs_margin = _accumulate_slot(
                    acc.categories[category],
                    challenger_yes=ch_yes,
                    king_yes=k_yes,
                    weight=weight,
                )
                _accumulate_slot(
                    acc.requires[requires],
                    challenger_yes=ch_yes,
                    king_yes=k_yes,
                    weight=weight,
                )
                acc.total_abs_margin_weighted += abs_margin

    total_abs = acc.total_abs_margin_weighted
    categories = [
        _bucket_row(key, bucket, total_abs_margin=total_abs)
        for key, bucket in sorted(
            acc.categories.items(),
            key=lambda item: item[1].abs_margin_weighted_sum,
            reverse=True,
        )
    ]
    requires_order = {"action": 0, "read": 1, "neutral": 2, "netural": 2, "unknown": 3}
    requires = [
        _bucket_row(key, bucket, total_abs_margin=total_abs, show_requires_weight=True)
        for key, bucket in sorted(
            acc.requires.items(),
            key=lambda item: (
                requires_order.get(item[0], 99),
                -item[1].abs_margin_weighted_sum,
            ),
        )
    ]

    return AlbedoScoringDuelAnalysis(
        eval_run_id=eval_run_id,
        finished_at=finished_at,
        challenger_label=challenger_label,
        king_label=king_label,
        challenger_won=challenger_won,
        coronated=coronated,
        total_samples=acc.total_samples,
        judge_observations=acc.judge_observations,
        question_slots=acc.question_slots,
        formula=AlbedoScoringFormula(requires_weights=dict(REQUIRES_WEIGHTS)),
        overall=_overall_summary(acc, dashboard_run=dashboard_run),
        categories=categories,
        requires=requires,
    )
