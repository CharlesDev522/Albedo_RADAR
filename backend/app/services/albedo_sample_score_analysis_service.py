"""Per-sample challenger vs king rubric score gap analysis for binary duels."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.albedo_scoring_results import fetch_scoring_results_jsonl
from app.schemas.albedo_sample_score_analysis import (
    AlbedoSampleScoreAnalysis,
    DuelSampleGapSummary,
    GapBucketCounts,
    GapBucketDistribution,
    JudgePairAgreement,
    JudgeSampleGapSummary,
    SampleGapBucket,
)
from app.services.albedo_analysis_service import judge_short_name
from app.services.albedo_scoring_analysis_service import (
    CHALLENGER_SIDE,
    KING_SIDE_RAW,
    _binary_eval_runs,
    _scoring_results_url,
)

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, AlbedoSampleScoreAnalysis]] = {}
_CACHE_TTL_SECONDS = 300.0

_GAP_LABELS: dict[SampleGapBucket, str] = {
    "close": "≤20 pt gap",
    "moderate": "20–50 pt gap (or wide low-confidence)",
    "decisive": ">50 pt gap & leader >90%",
}


@dataclass
class _Observation:
    eval_run_id: str
    finished_at: str
    challenger_label: str
    king_label: str
    winner: str
    judge_model: str
    sample_id: str
    challenger_pct: float
    king_pct: float
    gap_pct: float
    bucket: SampleGapBucket
    pick_challenger: bool


@dataclass
class _MutableCounts:
    close: int = 0
    moderate: int = 0
    decisive: int = 0

    def add(self, bucket: SampleGapBucket) -> None:
        if bucket == "close":
            self.close += 1
        elif bucket == "moderate":
            self.moderate += 1
        else:
            self.decisive += 1

    def to_counts(self) -> GapBucketCounts:
        total = self.close + self.moderate + self.decisive
        return GapBucketCounts(
            close=self.close,
            moderate=self.moderate,
            decisive=self.decisive,
            total=total,
        )


@dataclass
class _JudgeAccumulator:
    ch_scores: list[float] = field(default_factory=list)
    k_scores: list[float] = field(default_factory=list)
    gaps: list[float] = field(default_factory=list)
    pick_ch: int = 0
    counts: _MutableCounts = field(default_factory=_MutableCounts)


def gap_bucket_label(bucket: SampleGapBucket) -> str:
    return _GAP_LABELS[bucket]


def _answer_is_one(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) == 1.0
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def rubric_score_pct(answers: dict[str, Any], question_ids: list[str]) -> float:
    if not question_ids:
        return 0.0
    hits = sum(1 for qid in question_ids if _answer_is_one(answers.get(qid)))
    return hits / len(question_ids) * 100.0


def classify_sample_gap(challenger_pct: float, king_pct: float) -> SampleGapBucket:
    """Partition sample-judge observations into close / moderate / decisive buckets."""
    gap = abs(challenger_pct - king_pct)
    leader = max(challenger_pct, king_pct)
    if gap > 50 and leader > 90:
        return "decisive"
    if gap <= 20:
        return "close"
    return "moderate"


def _distribution(counts: _MutableCounts) -> GapBucketDistribution:
    total = counts.close + counts.moderate + counts.decisive
    if total == 0:
        return GapBucketDistribution(counts=counts.to_counts())
    return GapBucketDistribution(
        counts=counts.to_counts(),
        close_pct=round(counts.close / total * 100, 1),
        moderate_pct=round(counts.moderate / total * 100, 1),
        decisive_pct=round(counts.decisive / total * 100, 1),
    )


def _judge_pairs(judges: list[str]) -> list[tuple[str, str]]:
    ordered = sorted(judges)
    pairs: list[tuple[str, str]] = []
    for i, ja in enumerate(ordered):
        for jb in ordered[i + 1 :]:
            pairs.append((ja, jb))
    return pairs


def analyze_sample_rows(
    rows: list[dict[str, Any]],
    *,
    eval_run_id: str,
    finished_at: str = "",
    challenger_label: str = "",
    king_label: str = "",
    winner: str = "",
) -> list[_Observation]:
    observations: list[_Observation] = []
    for row in rows:
        sample_id = str(row.get("sample_id") or "")
        question_ids = [str(q.get("id")) for q in (row.get("questions") or []) if q.get("id")]
        if not question_ids:
            continue

        by_judge: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for entry in row.get("judge_results") or []:
            judge_model = str(entry.get("judge_model") or "")
            side = entry.get("side")
            if not judge_model or side not in (CHALLENGER_SIDE, KING_SIDE_RAW):
                continue
            by_judge[judge_model][str(side)] = entry

        for judge_model, sides in by_judge.items():
            ch_entry = sides.get(CHALLENGER_SIDE)
            k_entry = sides.get(KING_SIDE_RAW)
            if not ch_entry or not k_entry:
                continue
            ch_pct = rubric_score_pct(ch_entry.get("answers") or {}, question_ids)
            k_pct = rubric_score_pct(k_entry.get("answers") or {}, question_ids)
            gap = abs(ch_pct - k_pct)
            bucket = classify_sample_gap(ch_pct, k_pct)
            observations.append(
                _Observation(
                    eval_run_id=eval_run_id,
                    finished_at=finished_at,
                    challenger_label=challenger_label,
                    king_label=king_label,
                    winner=winner,
                    judge_model=judge_model,
                    sample_id=sample_id,
                    challenger_pct=round(ch_pct, 2),
                    king_pct=round(k_pct, 2),
                    gap_pct=round(gap, 2),
                    bucket=bucket,
                    pick_challenger=ch_pct > k_pct,
                )
            )
    return observations


def _duel_labels(run: dict[str, Any]) -> tuple[str, str, str]:
    king = run.get("king") or {}
    ch_uid = run.get("uid")
    k_uid = king.get("uid")
    challenger_label = f"uid {ch_uid}" if ch_uid is not None else "challenger"
    king_label = f"uid {k_uid}" if k_uid is not None else "king"
    winner = "challenger" if run.get("challenger_won") else "king"
    return challenger_label, king_label, winner


def _finalize_judge_summary(judge_model: str, acc: _JudgeAccumulator) -> JudgeSampleGapSummary:
    n = len(acc.ch_scores)
    return JudgeSampleGapSummary(
        judge_model=judge_model,
        short_name=judge_short_name(judge_model),
        observations=n,
        distribution=_distribution(acc.counts),
        avg_challenger_pct=round(mean(acc.ch_scores), 2) if n else 0.0,
        avg_king_pct=round(mean(acc.k_scores), 2) if n else 0.0,
        avg_gap_pct=round(mean(acc.gaps), 2) if n else 0.0,
        pick_challenger_pct=round(acc.pick_ch / n * 100, 1) if n else 0.0,
    )


def build_sample_score_analysis(observations: list[_Observation]) -> AlbedoSampleScoreAnalysis:
    if not observations:
        return AlbedoSampleScoreAnalysis()

    overall_counts = _MutableCounts()
    judge_acc: dict[str, _JudgeAccumulator] = defaultdict(_JudgeAccumulator)
    duel_meta: dict[str, dict[str, Any]] = {}
    duel_counts: dict[str, _MutableCounts] = defaultdict(_MutableCounts)
    duel_judge_acc: dict[str, dict[str, _JudgeAccumulator]] = defaultdict(lambda: defaultdict(_JudgeAccumulator))
    duel_samples: dict[str, set[str]] = defaultdict(set)
    pair_stats: dict[tuple[str, str], dict[str, int | list[float]]] = defaultdict(
        lambda: {"same_bucket": 0, "same_pick": 0, "deltas": [], "total": 0}
    )

    by_sample_judge: dict[tuple[str, str, str], _Observation] = {}
    for obs in observations:
        by_sample_judge[(obs.eval_run_id, obs.sample_id, obs.judge_model)] = obs

    for obs in observations:
        overall_counts.add(obs.bucket)
        jacc = judge_acc[obs.judge_model]
        jacc.counts.add(obs.bucket)
        jacc.ch_scores.append(obs.challenger_pct)
        jacc.k_scores.append(obs.king_pct)
        jacc.gaps.append(obs.gap_pct)
        if obs.pick_challenger:
            jacc.pick_ch += 1

        duel_meta[obs.eval_run_id] = {
            "finished_at": obs.finished_at,
            "challenger_label": obs.challenger_label,
            "king_label": obs.king_label,
            "winner": obs.winner,
        }
        duel_counts[obs.eval_run_id].add(obs.bucket)
        duel_samples[obs.eval_run_id].add(obs.sample_id)
        dj = duel_judge_acc[obs.eval_run_id][obs.judge_model]
        dj.counts.add(obs.bucket)
        dj.ch_scores.append(obs.challenger_pct)
        dj.k_scores.append(obs.king_pct)
        dj.gaps.append(obs.gap_pct)
        if obs.pick_challenger:
            dj.pick_ch += 1

    judge_models = sorted(judge_acc.keys())
    for eval_run_id, sample_ids in duel_samples.items():
        judges_in_duel = sorted(duel_judge_acc[eval_run_id].keys())
        for ja, jb in _judge_pairs(judges_in_duel):
            key = (ja, jb) if ja < jb else (jb, ja)
            for sample_id in sample_ids:
                a = by_sample_judge.get((eval_run_id, sample_id, ja))
                b = by_sample_judge.get((eval_run_id, sample_id, jb))
                if not a or not b:
                    continue
                stats = pair_stats[key]
                stats["total"] = int(stats["total"]) + 1
                if a.bucket == b.bucket:
                    stats["same_bucket"] = int(stats["same_bucket"]) + 1
                if a.pick_challenger == b.pick_challenger:
                    stats["same_pick"] = int(stats["same_pick"]) + 1
                cast_deltas = stats["deltas"]
                assert isinstance(cast_deltas, list)
                cast_deltas.append(abs(a.challenger_pct - b.challenger_pct))

    judge_pairs: list[JudgePairAgreement] = []
    for (ja, jb), stats in sorted(pair_stats.items(), key=lambda item: item[0]):
        total = int(stats["total"])
        if total == 0:
            continue
        deltas = stats["deltas"]
        assert isinstance(deltas, list)
        judge_pairs.append(
            JudgePairAgreement(
                judge_a=ja,
                judge_b=jb,
                short_name_a=judge_short_name(ja),
                short_name_b=judge_short_name(jb),
                observations=total,
                same_bucket_pct=round(int(stats["same_bucket"]) / total * 100, 1),
                same_pick_pct=round(int(stats["same_pick"]) / total * 100, 1),
                avg_score_delta_pct=round(mean(deltas), 2) if deltas else 0.0,
            )
        )

    duels: list[DuelSampleGapSummary] = []
    for eval_run_id in sorted(
        duel_meta.keys(),
        key=lambda eid: str(duel_meta[eid].get("finished_at") or ""),
        reverse=True,
    ):
        meta = duel_meta[eval_run_id]
        judges = [
            _finalize_judge_summary(judge_model, acc)
            for judge_model, acc in sorted(duel_judge_acc[eval_run_id].items())
        ]
        sample_count = len(duel_samples[eval_run_id])
        obs_count = sum(j.observations for j in judges)
        duels.append(
            DuelSampleGapSummary(
                eval_run_id=eval_run_id,
                finished_at=str(meta.get("finished_at") or ""),
                challenger_label=str(meta.get("challenger_label") or ""),
                king_label=str(meta.get("king_label") or ""),
                winner=str(meta.get("winner") or ""),
                sample_count=sample_count,
                judge_count=len(judges),
                observations=obs_count,
                distribution=_distribution(duel_counts[eval_run_id]),
                judges=judges,
            )
        )

    return AlbedoSampleScoreAnalysis(
        binary_duels_scanned=len(duel_meta),
        binary_duels_with_samples=len(duel_meta),
        total_samples=sum(len(s) for s in duel_samples.values()),
        total_observations=len(observations),
        judge_models=judge_models,
        overall=_distribution(overall_counts),
        by_judge=[
            _finalize_judge_summary(judge_model, acc)
            for judge_model, acc in sorted(judge_acc.items())
        ],
        judge_pairs=judge_pairs,
        duels=duels,
    )


async def get_sample_score_analysis(
    *,
    settings: Settings | None = None,
    fresh: bool = False,
) -> AlbedoSampleScoreAnalysis:
    settings = settings or get_settings()
    cache_key = "sample_score_analysis"
    if not fresh:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_runs: list[dict[str, Any]] = list(dashboard.get("eval_runs") or [])
    binary_total = sum(1 for run in eval_runs if run.get("scoring_mode") == "binary")
    binary_runs = sorted(
        _binary_eval_runs(eval_runs),
        key=lambda r: str(r.get("finished_at") or ""),
        reverse=True,
    )

    all_observations: list[_Observation] = []
    async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
        for run in binary_runs:
            url = _scoring_results_url(run)
            if not url:
                continue
            eval_run_id = str(run.get("eval_run_id") or "")
            try:
                rows = await fetch_scoring_results_jsonl(
                    url,
                    settings=settings,
                    client=client,
                    fresh=fresh,
                )
            except Exception:
                logger.warning(
                    "Skipping sample score analysis eval_run_id=%s",
                    eval_run_id,
                    exc_info=True,
                )
                continue
            ch_label, k_label, winner = _duel_labels(run)
            all_observations.extend(
                analyze_sample_rows(
                    rows,
                    eval_run_id=eval_run_id,
                    finished_at=str(run.get("finished_at") or ""),
                    challenger_label=ch_label,
                    king_label=k_label,
                    winner=winner,
                )
            )

    result = build_sample_score_analysis(all_observations)
    result = result.model_copy(
        update={
            "binary_duels_total": binary_total,
            "binary_duels_scanned": len(binary_runs),
            "updated_at": dashboard.get("updated_at"),
        }
    )
    if not fresh:
        _CACHE[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, result)
    return result
