"""Category and requires breakdown for one duel's scoring-results.jsonl."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Literal

from app.scoring.albedo_judge_scoring import (
    CHALLENGER_WIN_MARGIN,
    REQUIRES_WEIGHTS,
    SIZE_FACTOR_FLOOR,
    aggregate_decomposed_metric,
    aggregate_scores_from_records,
    decompose_judge_yes_rate,
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


@dataclass
class _CurrentSampleBuckets:
    ch_contrib: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    k_contrib: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    ch_partial: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    k_partial: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    weight_share: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    judge_observations: int = 0


@dataclass
class _BucketSeries:
    ch_contrib_samples: list[float] = field(default_factory=list)
    k_contrib_samples: list[float] = field(default_factory=list)
    ch_partial_samples: list[float] = field(default_factory=list)
    k_partial_samples: list[float] = field(default_factory=list)
    weight_share_samples: list[float] = field(default_factory=list)
    judge_observations: int = 0


@dataclass
class _TotalsAccum:
    base_ch: list[list[float]] = field(default_factory=list)
    base_k: list[list[float]] = field(default_factory=list)
    size_mult_ch: list[list[float]] = field(default_factory=list)
    size_mult_k: list[list[float]] = field(default_factory=list)
    size_yes_ch: list[list[float]] = field(default_factory=list)
    size_yes_k: list[list[float]] = field(default_factory=list)


@dataclass
class _AnalysisAccum:
    buckets: dict[str, dict[str, _BucketSeries]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(_BucketSeries))
    )
    current: dict[str, _CurrentSampleBuckets] = field(
        default_factory=lambda: defaultdict(_CurrentSampleBuckets)
    )
    totals: _TotalsAccum = field(default_factory=_TotalsAccum)
    size_slots: int = 0
    total_samples: int = 0
    judge_observations: int = 0
    current_sample_ch_base: list[float] = field(default_factory=list)
    current_sample_k_base: list[float] = field(default_factory=list)
    current_sample_ch_mult: list[float] = field(default_factory=list)
    current_sample_k_mult: list[float] = field(default_factory=list)
    current_sample_ch_size_yes: list[float] = field(default_factory=list)
    current_sample_k_size_yes: list[float] = field(default_factory=list)


def _mean_or_zero(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _flush_sample(acc: _AnalysisAccum) -> None:
    for group_by, sample_buckets in acc.current.items():
        if sample_buckets.judge_observations <= 0:
            continue

        for key, ch_values in sample_buckets.ch_contrib.items():
            series = acc.buckets[group_by][key]
            series.ch_contrib_samples.append(_mean_or_zero(ch_values))
            series.k_contrib_samples.append(_mean_or_zero(sample_buckets.k_contrib.get(key, [])))
            series.ch_partial_samples.append(_mean_or_zero(sample_buckets.ch_partial.get(key, [])))
            series.k_partial_samples.append(_mean_or_zero(sample_buckets.k_partial.get(key, [])))
            series.weight_share_samples.append(_mean_or_zero(sample_buckets.weight_share.get(key, [])))
            series.judge_observations += sample_buckets.judge_observations

        sample_buckets.ch_contrib.clear()
        sample_buckets.k_contrib.clear()
        sample_buckets.ch_partial.clear()
        sample_buckets.k_partial.clear()
        sample_buckets.weight_share.clear()
        sample_buckets.judge_observations = 0

    if acc.current_sample_ch_base:
        acc.totals.base_ch.append(list(acc.current_sample_ch_base))
        acc.totals.base_k.append(list(acc.current_sample_k_base))
        acc.totals.size_mult_ch.append(list(acc.current_sample_ch_mult))
        acc.totals.size_mult_k.append(list(acc.current_sample_k_mult))
        if acc.current_sample_ch_size_yes:
            acc.totals.size_yes_ch.append(list(acc.current_sample_ch_size_yes))
            acc.totals.size_yes_k.append(list(acc.current_sample_k_size_yes))

    acc.current_sample_ch_base.clear()
    acc.current_sample_k_base.clear()
    acc.current_sample_ch_mult.clear()
    acc.current_sample_k_mult.clear()
    acc.current_sample_ch_size_yes.clear()
    acc.current_sample_k_size_yes.clear()


def _scale_bucket_contributions(
    decomposition: dict[str, Any],
    *,
    target_rate: float | None,
) -> dict[str, Any]:
    """Scale bucket contributions so they sum to target_rate (stored yes_rate)."""
    if target_rate is None:
        return decomposition

    target = float(target_rate)
    final_rate = decomposition.get("final_rate")
    buckets: dict[str, dict[str, float]] = decomposition.get("buckets") or {}

    if final_rate is not None and final_rate > 0:
        scale = target / float(final_rate)
        if abs(scale - 1.0) < 1e-9:
            return decomposition
        scaled = dict(decomposition)
        scaled_buckets: dict[str, dict[str, float]] = {}
        for key, part in buckets.items():
            scaled_part = dict(part)
            scaled_part["contribution"] = part.get("contribution", 0.0) * scale
            scaled_part["base_contribution"] = part.get("base_contribution", 0.0) * scale
            scaled_buckets[key] = scaled_part
        scaled["buckets"] = scaled_buckets
        scaled["final_rate"] = round(target, 6)
        if decomposition.get("base_rate") is not None:
            scaled["base_rate"] = round(float(decomposition["base_rate"]) * scale, 6)
        return scaled

    if target <= 0:
        return decomposition

    # Stored yes_rate is positive but answer-derived score is zero (e.g. all misses).
    total_share = sum(part.get("weight_share", 0.0) for part in buckets.values())
    scaled = dict(decomposition)
    scaled_buckets = {}
    for key, part in buckets.items():
        share = part.get("weight_share", 0.0)
        if total_share > 0:
            fraction = share / total_share
        else:
            fraction = 1.0 / len(buckets) if buckets else 0.0
        scaled_part = dict(part)
        scaled_part["contribution"] = target * fraction
        scaled_part["base_contribution"] = target * fraction
        scaled_buckets[key] = scaled_part
    scaled["buckets"] = scaled_buckets
    scaled["final_rate"] = round(target, 6)
    scaled["base_rate"] = round(target, 6)
    return scaled


def _accumulate_decomposition(
    acc: _AnalysisAccum,
    *,
    group_by: Literal["requires", "category"],
    ch_answers: dict[str, Any],
    k_answers: dict[str, Any],
    questions: list[dict[str, Any]],
    ch_yes_rate: float | None = None,
    k_yes_rate: float | None = None,
) -> None:
    ch_dec = _scale_bucket_contributions(
        decompose_judge_yes_rate(ch_answers, questions, group_by=group_by),
        target_rate=ch_yes_rate,
    )
    k_dec = _scale_bucket_contributions(
        decompose_judge_yes_rate(k_answers, questions, group_by=group_by),
        target_rate=k_yes_rate,
    )

    if group_by == "requires":
        if ch_dec["base_rate"] is not None:
            acc.current_sample_ch_base.append(ch_dec["base_rate"])
        if k_dec["base_rate"] is not None:
            acc.current_sample_k_base.append(k_dec["base_rate"])
        acc.current_sample_ch_mult.append(ch_dec["size_multiplier"])
        acc.current_sample_k_mult.append(k_dec["size_multiplier"])
        if ch_dec["size_yes_rate"] is not None:
            acc.current_sample_ch_size_yes.append(ch_dec["size_yes_rate"])
        if k_dec["size_yes_rate"] is not None:
            acc.current_sample_k_size_yes.append(k_dec["size_yes_rate"])

    sample_buckets = acc.current[group_by]
    sample_buckets.judge_observations += 1

    all_keys = set(ch_dec["buckets"]) | set(k_dec["buckets"])
    for key in all_keys:
        ch_part = ch_dec["buckets"].get(key, {})
        k_part = k_dec["buckets"].get(key, {})
        sample_buckets.ch_contrib[key].append(ch_part.get("contribution", 0.0))
        sample_buckets.k_contrib[key].append(k_part.get("contribution", 0.0))
        sample_buckets.ch_partial[key].append(ch_part.get("partial_rate", 0.0))
        sample_buckets.k_partial[key].append(k_part.get("partial_rate", 0.0))
        sample_buckets.weight_share[key].append(
            ch_part.get("weight_share", k_part.get("weight_share", 0.0))
        )


def _mean_across_samples(values: list[float]) -> float:
    return round(mean(values), 6) if values else 0.0


def _bucket_row(
    key: str,
    series: _BucketSeries,
    *,
    show_requires_weight: bool = False,
) -> AlbedoScoringBucketRow:
    if not series.ch_contrib_samples:
        return AlbedoScoringBucketRow(
            key=key,
            weight_multiplier=requires_weight(key) if show_requires_weight else None,
        )

    ch_contrib = _mean_across_samples(series.ch_contrib_samples)
    k_contrib = _mean_across_samples(series.k_contrib_samples)
    ch_partial = _mean_across_samples(series.ch_partial_samples)
    k_partial = _mean_across_samples(series.k_partial_samples)
    weight_share = _mean_across_samples(series.weight_share_samples)

    return AlbedoScoringBucketRow(
        key=key,
        weight_multiplier=requires_weight(key) if show_requires_weight else None,
        question_slots=series.judge_observations,
        weight_share_pct=weight_share * 100.0,
        challenger_yes_rate=ch_partial * 100.0,
        king_yes_rate=k_partial * 100.0,
        weighted_challenger_score=ch_contrib * 100.0,
        weighted_king_score=k_contrib * 100.0,
        weighted_margin=(ch_contrib - k_contrib) * 100.0,
        share_of_abs_weighted_margin_pct=0.0,
    )


def _finalize_bucket_shares(rows: list[AlbedoScoringBucketRow]) -> list[AlbedoScoringBucketRow]:
    total_abs = sum(abs(row.weighted_margin) for row in rows)
    if total_abs <= 0:
        return rows
    return [
        row.model_copy(
            update={
                "share_of_abs_weighted_margin_pct": abs(row.weighted_margin) / total_abs * 100.0,
            }
        )
        for row in rows
    ]


def _size_bucket_row(acc: _AnalysisAccum) -> AlbedoScoringBucketRow | None:
    ch_mult = aggregate_decomposed_metric(acc.totals.size_mult_ch)
    k_mult = aggregate_decomposed_metric(acc.totals.size_mult_k)
    ch_yes = aggregate_decomposed_metric(acc.totals.size_yes_ch)
    k_yes = aggregate_decomposed_metric(acc.totals.size_yes_k)
    if ch_mult is None and k_mult is None:
        return None
    return AlbedoScoringBucketRow(
        key="size",
        question_slots=acc.size_slots,
        weight_share_pct=0.0,
        challenger_yes_rate=(ch_yes or 0.0) * 100.0,
        king_yes_rate=(k_yes or 0.0) * 100.0,
        weighted_challenger_score=(ch_mult or 1.0) * 100.0,
        weighted_king_score=(k_mult or 1.0) * 100.0,
        weighted_margin=((ch_mult or 1.0) - (k_mult or 1.0)) * 100.0,
        share_of_abs_weighted_margin_pct=0.0,
        note="Size multiplier (informational; already embedded in requires contributions)",
    )


def _total_row(
    key: str,
    *,
    ch_score: float | None,
    k_score: float | None,
    note: str | None = None,
) -> AlbedoScoringBucketRow | None:
    if ch_score is None or k_score is None:
        return None
    return AlbedoScoringBucketRow(
        key=key,
        question_slots=0,
        weight_share_pct=100.0,
        challenger_yes_rate=ch_score * 100.0,
        king_yes_rate=k_score * 100.0,
        weighted_challenger_score=ch_score * 100.0,
        weighted_king_score=k_score * 100.0,
        weighted_margin=(ch_score - k_score) * 100.0,
        share_of_abs_weighted_margin_pct=0.0,
        note=note,
    )


def _overall_summary(
    acc: _AnalysisAccum,
    *,
    replicated: dict[str, float | None],
    dashboard_run: dict[str, Any] | None = None,
    requires_rows: list[AlbedoScoringBucketRow],
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

    base_ch = aggregate_decomposed_metric(acc.totals.base_ch)
    base_k = aggregate_decomposed_metric(acc.totals.base_k)
    contrib_ch = sum(
        row.weighted_challenger_score
        for row in requires_rows
        if row.key not in {"size", "_total"}
    )
    contrib_k = sum(
        row.weighted_king_score
        for row in requires_rows
        if row.key not in {"size", "_total"}
    )

    duel_ch_pct = round(float(ch) * 100.0, 4) if ch is not None else None
    duel_k_pct = round(float(k) * 100.0, 4) if k is not None else None

    return AlbedoScoringOverallSummary(
        observation_count=acc.total_samples,
        weighted_challenger_score_pct=round(float(ch) * 100.0, 4) if ch is not None else 0.0,
        weighted_king_score_pct=round(float(k) * 100.0, 4) if k is not None else 0.0,
        weighted_margin_pct=round(float(margin) * 100.0, 4) if margin is not None else 0.0,
        dashboard_score_challenger=dashboard_ch,
        dashboard_score_king=dashboard_k,
        dashboard_win_margin=dashboard_margin,
        replicated_valid_samples=int(replicated.get("valid_samples") or 0),
        base_challenger_score_pct=round(base_ch * 100.0, 4) if base_ch is not None else None,
        base_king_score_pct=round(base_k * 100.0, 4) if base_k is not None else None,
        requires_contrib_challenger_pct=round(contrib_ch, 4) if requires_rows else None,
        requires_contrib_king_pct=round(contrib_k, 4) if requires_rows else None,
        challenger_win_margin=CHALLENGER_WIN_MARGIN,
        jsonl_matches_dashboard=(
            ch is not None
            and dashboard_ch is not None
            and abs(ch - dashboard_ch) < 1e-4
            and k is not None
            and dashboard_k is not None
            and abs(k - dashboard_k) < 1e-4
        ),
        requires_contrib_matches_duel=(
            duel_ch_pct is not None
            and duel_k_pct is not None
            and abs(contrib_ch - duel_ch_pct) < 0.2
            and abs(contrib_k - duel_k_pct) < 0.2
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
    """Decompose duel scores by category/requires using the official rubric."""
    acc = _AnalysisAccum()
    replicated = aggregate_scores_from_records(rows)

    for row in rows:
        questions = [q for q in (row.get("questions") or []) if isinstance(q, dict) and q.get("id")]
        if not questions:
            continue

        ch_score, k_score = sample_side_scores(row)
        if ch_score is not None and k_score is not None:
            acc.total_samples += 1

        by_judge: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for entry in row.get("judge_results") or []:
            if not isinstance(entry, dict):
                continue
            side = entry.get("side")
            judge = str(entry.get("judge_model") or "")
            if side in (CHALLENGER_SIDE, KING_SIDE_RAW) and judge and entry.get("parse_ok"):
                by_judge[judge][str(side)] = entry

        acc.size_slots += sum(
            1 for q in questions if str(q.get("category") or "").strip().lower() == "size"
        )

        for sides in by_judge.values():
            ch = sides.get(CHALLENGER_SIDE)
            k = sides.get(KING_SIDE_RAW)
            if not ch or not k:
                continue
            ch_ans = ch.get("answers") or {}
            k_ans = k.get("answers") or {}
            ch_yes_rate = ch.get("yes_rate")
            k_yes_rate = k.get("yes_rate")
            if ch_yes_rate is not None:
                ch_yes_rate = float(ch_yes_rate)
            if k_yes_rate is not None:
                k_yes_rate = float(k_yes_rate)
            acc.judge_observations += 1
            _accumulate_decomposition(
                acc,
                group_by="requires",
                ch_answers=ch_ans,
                k_answers=k_ans,
                questions=questions,
                ch_yes_rate=ch_yes_rate,
                k_yes_rate=k_yes_rate,
            )
            _accumulate_decomposition(
                acc,
                group_by="category",
                ch_answers=ch_ans,
                k_answers=k_ans,
                questions=questions,
                ch_yes_rate=ch_yes_rate,
                k_yes_rate=k_yes_rate,
            )

        _flush_sample(acc)

    requires_order = {"action": 0, "read": 1, "neutral": 2, "unknown": 99}
    requires_body = [
        _bucket_row(key, series, show_requires_weight=True)
        for key, series in sorted(
            acc.buckets["requires"].items(),
            key=lambda item: (requires_order.get(item[0], 99), -sum(item[1].ch_contrib_samples)),
        )
    ]
    requires_body = _finalize_bucket_shares(requires_body)

    final_ch = replicated.get("score_challenger")
    final_k = replicated.get("score_king")

    requires_rows = list(requires_body)
    size_row = _size_bucket_row(acc)
    if size_row:
        requires_rows.append(size_row)
    total_row = _total_row(
        "_total",
        ch_score=final_ch,
        k_score=final_k,
        note="Duel score (mean per-sample side scores; requires rows sum here)",
    )
    if total_row:
        requires_rows.append(total_row)

    categories_body = [
        _bucket_row(key, series)
        for key, series in sorted(
            acc.buckets["category"].items(),
            key=lambda item: -sum(item[1].ch_contrib_samples),
        )
    ]
    categories = _finalize_bucket_shares(categories_body)
    if size_row:
        categories.append(size_row.model_copy())
    if total_row:
        categories.append(total_row.model_copy())

    return AlbedoScoringDuelAnalysis(
        eval_run_id=eval_run_id,
        finished_at=finished_at,
        challenger_label=challenger_label,
        king_label=king_label,
        challenger_won=challenger_won,
        coronated=coronated,
        total_samples=acc.total_samples,
        judge_observations=acc.judge_observations,
        question_slots=acc.judge_observations,
        size_question_slots=acc.size_slots,
        formula=AlbedoScoringFormula(
            requires_weights=dict(REQUIRES_WEIGHTS),
            size_factor_floor=SIZE_FACTOR_FLOOR,
            challenger_win_margin=CHALLENGER_WIN_MARGIN,
        ),
        overall=_overall_summary(
            acc,
            replicated=replicated,
            dashboard_run=dashboard_run,
            requires_rows=requires_body,
        ),
        categories=categories,
        requires=requires_rows,
    )
