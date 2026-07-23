"""Category and requires breakdown for one duel's scoring-results.jsonl."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.scoring.albedo_judge_scoring import (
    CHALLENGER_WIN_MARGIN,
    REQUIRES_WEIGHTS,
    SIZE_FACTOR_FLOOR,
    aggregate_scores_from_records,
    judge_yes_rate,
    requires_weight,
    sample_side_scores,
)
from app.schemas.albedo_scoring_analysis import (
    AlbedoScoringBucketRow,
    AlbedoScoringDuelAnalysis,
    AlbedoScoringFormula,
    AlbedoScoringOverallSummary,
)

CHALLENGER_SIDE = "challenger"
KING_SIDE_RAW = "previous_king"


def normalize_requires(value: Any) -> str:
    key = str(value or "neutral").strip().lower()
    return key or "neutral"


def normalize_category(value: Any) -> str:
    key = str(value or "uncategorized").strip()
    return key or "uncategorized"


def _is_size_question(question: dict[str, Any]) -> bool:
    return str(question.get("category") or "").strip().lower() == "size"


def _non_size_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [q for q in questions if isinstance(q, dict) and q.get("id") and not _is_size_question(q)]


def _subset_rate(answers: dict[str, Any], questions: list[dict[str, Any]]) -> float | None:
    if not questions:
        return None
    ids = {str(q["id"]) for q in questions if q.get("id")}
    filtered = {qid: answers[qid] for qid in ids if qid in answers}
    return judge_yes_rate(filtered, questions)


@dataclass
class _BucketAccum:
    observations: int = 0
    ch_rate_sum: float = 0.0
    k_rate_sum: float = 0.0
    abs_margin_sum: float = 0.0


@dataclass
class _SlotPoolAccum:
    weighted_ch_sum: float = 0.0
    weighted_k_sum: float = 0.0
    weight_sum: float = 0.0
    abs_margin_weighted_sum: float = 0.0


@dataclass
class _AnalysisAccum:
    categories: dict[str, _BucketAccum] = field(default_factory=lambda: defaultdict(_BucketAccum))
    requires: dict[str, _BucketAccum] = field(default_factory=lambda: defaultdict(_BucketAccum))
    slot_pool: _SlotPoolAccum = field(default_factory=_SlotPoolAccum)
    size_slots: int = 0
    total_samples: int = 0
    judge_observations: int = 0
    question_slots: int = 0


def _add_observation(acc: _BucketAccum, *, ch_rate: float, k_rate: float) -> float:
    acc.observations += 1
    acc.ch_rate_sum += ch_rate
    acc.k_rate_sum += k_rate
    abs_margin = abs(ch_rate - k_rate)
    acc.abs_margin_sum += abs_margin
    return abs_margin


def _accumulate_slot_pool(
    acc: _SlotPoolAccum,
    *,
    challenger_yes: bool,
    king_yes: bool,
    weight: float,
) -> float:
    ch = 1.0 if challenger_yes else 0.0
    k = 1.0 if king_yes else 0.0
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
    if obs <= 0:
        return AlbedoScoringBucketRow(key=key, weight_multiplier=requires_weight(key) if show_requires_weight else None)

    ch_mean = acc.ch_rate_sum / obs
    k_mean = acc.k_rate_sum / obs
    share = acc.abs_margin_sum / total_abs_margin * 100.0 if total_abs_margin > 0 else 0.0
    return AlbedoScoringBucketRow(
        key=key,
        weight_multiplier=requires_weight(key) if show_requires_weight else None,
        question_slots=obs,
        challenger_yes_rate=ch_mean * 100.0,
        king_yes_rate=k_mean * 100.0,
        weighted_challenger_score=ch_mean * 100.0,
        weighted_king_score=k_mean * 100.0,
        weighted_margin=(ch_mean - k_mean) * 100.0,
        share_of_abs_weighted_margin_pct=share,
    )


def _slot_pool_summary(acc: _SlotPoolAccum) -> tuple[float | None, float | None, float | None]:
    weight_sum = acc.weight_sum
    if weight_sum <= 0:
        return None, None, None
    ch = acc.weighted_ch_sum / weight_sum
    k = acc.weighted_k_sum / weight_sum
    return ch, k, ch - k


def _overall_summary(
    acc: _AnalysisAccum,
    *,
    replicated: dict[str, float | None],
    dashboard_run: dict[str, Any] | None = None,
) -> AlbedoScoringOverallSummary:
    ch = replicated.get("score_challenger")
    k = replicated.get("score_king")
    margin = replicated.get("win_margin")

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

    slot_ch, slot_k, slot_margin = _slot_pool_summary(acc.slot_pool)

    return AlbedoScoringOverallSummary(
        observation_count=acc.total_samples,
        weighted_challenger_score_pct=round(float(ch) * 100.0, 4) if ch is not None else 0.0,
        weighted_king_score_pct=round(float(k) * 100.0, 4) if k is not None else 0.0,
        weighted_margin_pct=round(float(margin) * 100.0, 4) if margin is not None else 0.0,
        dashboard_score_challenger=dashboard_ch,
        dashboard_score_king=dashboard_k,
        dashboard_win_margin=dashboard_margin,
        replicated_valid_samples=int(replicated.get("valid_samples") or 0),
        slot_pooled_challenger_score_pct=round(slot_ch * 100.0, 4) if slot_ch is not None else None,
        slot_pooled_king_score_pct=round(slot_k * 100.0, 4) if slot_k is not None else None,
        slot_pooled_margin_pct=round(slot_margin * 100.0, 4) if slot_margin is not None else None,
        challenger_win_margin=CHALLENGER_WIN_MARGIN,
        jsonl_matches_dashboard=(
            ch is not None
            and dashboard_ch is not None
            and abs(ch - dashboard_ch) < 1e-4
            and k is not None
            and dashboard_k is not None
            and abs(k - dashboard_k) < 1e-4
        ),
        bucket_margin_matches_duel=(
            ch is not None
            and k is not None
            and margin is not None
            and slot_margin is not None
            and abs(slot_margin - margin) < 0.02
        ),
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
    """Aggregate per-sample judge observations by category and requires."""
    acc = _AnalysisAccum()
    replicated = aggregate_scores_from_records(rows)

    for row in rows:
        questions = [q for q in (row.get("questions") or []) if isinstance(q, dict) and q.get("id")]
        if not questions:
            continue

        ch_score, k_score = sample_side_scores(row)
        if ch_score is not None and k_score is not None:
            acc.total_samples += 1

        meta_by_id = {str(q["id"]): q for q in questions}
        question_list = list(meta_by_id.values())
        non_size = _non_size_questions(question_list)

        by_judge: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for entry in row.get("judge_results") or []:
            if not isinstance(entry, dict):
                continue
            side = entry.get("side")
            judge = str(entry.get("judge_model") or "")
            if side in (CHALLENGER_SIDE, KING_SIDE_RAW) and judge and entry.get("parse_ok"):
                by_judge[judge][str(side)] = entry

        categories_seen = {normalize_category(q.get("category")) for q in non_size}
        requires_seen = {normalize_requires(q.get("requires")) for q in non_size}

        for sides in by_judge.values():
            ch = sides.get(CHALLENGER_SIDE)
            k = sides.get(KING_SIDE_RAW)
            if not ch or not k:
                continue
            ch_ans = ch.get("answers") or {}
            k_ans = k.get("answers") or {}
            acc.judge_observations += 1

            for category in categories_seen:
                subset = [
                    q
                    for q in non_size
                    if normalize_category(q.get("category")) == category
                ]
                ch_rate = _subset_rate(ch_ans, subset)
                k_rate = _subset_rate(k_ans, subset)
                if ch_rate is None or k_rate is None:
                    continue
                _add_observation(acc.categories[category], ch_rate=ch_rate, k_rate=k_rate)

            for requires in requires_seen:
                subset = [
                    q
                    for q in non_size
                    if normalize_requires(q.get("requires")) == requires
                ]
                ch_rate = _subset_rate(ch_ans, subset)
                k_rate = _subset_rate(k_ans, subset)
                if ch_rate is None or k_rate is None:
                    continue
                _add_observation(acc.requires[requires], ch_rate=ch_rate, k_rate=k_rate)

            for qid, question in meta_by_id.items():
                if _is_size_question(question):
                    acc.size_slots += 1
                    continue

                category = normalize_category(question.get("category"))
                requires = normalize_requires(question.get("requires"))
                weight = requires_weight(requires)
                ch_bit = _subset_rate({qid: ch_ans.get(qid)}, [question])
                k_bit = _subset_rate({qid: k_ans.get(qid)}, [question])
                ch_yes = ch_bit == 1.0 if ch_bit is not None else False
                k_yes = k_bit == 1.0 if k_bit is not None else False
                acc.question_slots += 1
                _accumulate_slot_pool(
                    acc.slot_pool,
                    challenger_yes=ch_yes,
                    king_yes=k_yes,
                    weight=weight,
                )

    category_abs = sum(b.abs_margin_sum for b in acc.categories.values())
    requires_abs = sum(b.abs_margin_sum for b in acc.requires.values())

    categories = [
        _bucket_row(key, bucket, total_abs_margin=category_abs)
        for key, bucket in sorted(
            acc.categories.items(),
            key=lambda item: item[1].abs_margin_sum,
            reverse=True,
        )
    ]
    requires_order = {"action": 0, "read": 1, "neutral": 2, "unknown": 99}
    requires = [
        _bucket_row(key, bucket, total_abs_margin=requires_abs, show_requires_weight=True)
        for key, bucket in sorted(
            acc.requires.items(),
            key=lambda item: (
                requires_order.get(item[0], 99),
                -item[1].abs_margin_sum,
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
        size_question_slots=acc.size_slots,
        formula=AlbedoScoringFormula(
            requires_weights=dict(REQUIRES_WEIGHTS),
            size_factor_floor=SIZE_FACTOR_FLOOR,
            challenger_win_margin=CHALLENGER_WIN_MARGIN,
        ),
        overall=_overall_summary(acc, replicated=replicated, dashboard_run=dashboard_run),
        categories=categories,
        requires=requires,
    )
