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
    JudgeMarginShare,
    JudgePairAgreement,
    JudgeSampleGapSummary,
    SampleGapBucket,
    ScoreCaseCategory,
    ScoreCaseRow,
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
    lower_pct: float
    higher_pct: float
    gap_pct: float
    bucket: SampleGapBucket
    pick_challenger: bool


@dataclass(frozen=True)
class _CaseDef:
    case_id: str
    label: str
    category: ScoreCaseCategory


def _obs_matches_case(obs: _Observation, case_id: str) -> bool:
    lo, hi, gap = obs.lower_pct, obs.higher_pct, obs.gap_pct
    if case_id == "gap_le_10":
        return gap <= 10
    if case_id == "gap_10_20":
        return 10 < gap <= 20
    if case_id == "gap_20_50":
        return 20 < gap <= 50
    if case_id == "gap_50_80":
        return 50 < gap <= 80
    if case_id == "gap_gt_80":
        return gap > 80
    if case_id == "loser_lt_10":
        return lo < 10
    if case_id == "loser_10_30":
        return 10 <= lo < 30
    if case_id == "loser_30_70":
        return 30 <= lo < 70
    if case_id == "loser_ge_70":
        return lo >= 70
    if case_id == "crushed_loser":
        return lo < 10 and gap > 20
    if case_id == "crushed_loser_wide":
        return lo < 10 and gap > 50
    if case_id == "decisive_high":
        return gap > 50 and hi > 90
    if case_id == "close_call":
        return gap <= 20
    if case_id == "both_strong_close":
        return lo >= 70 and gap <= 20
    if case_id == "both_weak":
        return hi < 30
    if case_id == "weak_loser_big_gap":
        return lo < 30 and gap > 20
    if case_id == "winner_under_50_big_gap":
        return hi < 50 and gap > 30
    if case_id == "challenger_blowout":
        return obs.pick_challenger and gap > 50
    if case_id == "king_blowout":
        return not obs.pick_challenger and gap > 50
    if case_id == "loser_lt_10_gap_20_50":
        return lo < 10 and 20 < gap <= 50
    if case_id == "mid_split":
        return 20 < gap <= 50 and lo >= 20
    if case_id == "leader_gt_90":
        return hi > 90
    if case_id == "loser_zero":
        return lo == 0
    if case_id == "perfect_winner":
        return hi == 100 and gap > 20
    return False


SCORE_CASE_DEFINITIONS: list[_CaseDef] = [
    _CaseDef("gap_le_10", "Gap ≤10 pt", "gap_band"),
    _CaseDef("gap_10_20", "Gap 10–20 pt", "gap_band"),
    _CaseDef("gap_20_50", "Gap 20–50 pt", "gap_band"),
    _CaseDef("gap_50_80", "Gap 50–80 pt", "gap_band"),
    _CaseDef("gap_gt_80", "Gap >80 pt", "gap_band"),
    _CaseDef("loser_lt_10", "Loser score <10%", "loser_band"),
    _CaseDef("loser_10_30", "Loser score 10–30%", "loser_band"),
    _CaseDef("loser_30_70", "Loser score 30–70%", "loser_band"),
    _CaseDef("loser_ge_70", "Loser score ≥70%", "loser_band"),
    _CaseDef("crushed_loser", "Loser <10% & gap >20", "edge"),
    _CaseDef("crushed_loser_wide", "Loser <10% & gap >50", "edge"),
    _CaseDef("loser_lt_10_gap_20_50", "Loser <10% & gap 20–50", "edge"),
    _CaseDef("decisive_high", "Gap >50 & leader >90%", "edge"),
    _CaseDef("close_call", "Gap ≤20 (close)", "edge"),
    _CaseDef("both_strong_close", "Both ≥70% & gap ≤20", "edge"),
    _CaseDef("both_weak", "Both scores <30%", "edge"),
    _CaseDef("weak_loser_big_gap", "Loser <30% & gap >20", "edge"),
    _CaseDef("winner_under_50_big_gap", "Winner <50% & gap >30", "edge"),
    _CaseDef("challenger_blowout", "Challenger wins sample & gap >50", "edge"),
    _CaseDef("king_blowout", "King wins sample & gap >50", "edge"),
    _CaseDef("mid_split", "Gap 20–50 & loser ≥20%", "edge"),
    _CaseDef("leader_gt_90", "Leader score >90%", "edge"),
    _CaseDef("loser_zero", "Loser score 0%", "edge"),
    _CaseDef("perfect_winner", "Perfect 100% & gap >20", "edge"),
]


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


def _total_gap_points(observations: list[_Observation]) -> float:
    return sum(o.gap_pct for o in observations)


def _build_case_rows(observations: list[_Observation]) -> list[ScoreCaseRow]:
    if not observations:
        return []
    total_obs = len(observations)
    total_gap = _total_gap_points(observations)
    rows: list[ScoreCaseRow] = []
    for case in SCORE_CASE_DEFINITIONS:
        matched = [o for o in observations if _obs_matches_case(o, case.case_id)]
        if not matched:
            rows.append(
                ScoreCaseRow(
                    case_id=case.case_id,
                    label=case.label,
                    category=case.category,
                )
            )
            continue
        gap_sum = sum(o.gap_pct for o in matched)
        rows.append(
            ScoreCaseRow(
                case_id=case.case_id,
                label=case.label,
                category=case.category,
                observations=len(matched),
                observations_pct=round(len(matched) / total_obs * 100, 1),
                total_gap_points=round(gap_sum, 2),
                gap_share_pct=round(gap_sum / total_gap * 100, 1) if total_gap else 0.0,
                avg_gap=round(mean(o.gap_pct for o in matched), 2),
                avg_lower_score=round(mean(o.lower_pct for o in matched), 2),
                avg_higher_score=round(mean(o.higher_pct for o in matched), 2),
            )
        )
    return rows


def _split_case_rows(rows: list[ScoreCaseRow]) -> tuple[list[ScoreCaseRow], list[ScoreCaseRow], list[ScoreCaseRow]]:
    gap_bands = [r for r in rows if r.category == "gap_band"]
    loser_bands = [r for r in rows if r.category == "loser_band"]
    edge_cases = [r for r in rows if r.category == "edge"]
    return gap_bands, loser_bands, edge_cases


def _build_judge_margin_shares(observations: list[_Observation]) -> list[JudgeMarginShare]:
    if not observations:
        return []
    total_gap = _total_gap_points(observations)
    by_judge: dict[str, list[_Observation]] = defaultdict(list)
    for obs in observations:
        by_judge[obs.judge_model].append(obs)
    shares: list[JudgeMarginShare] = []
    for judge_model, obs_list in sorted(by_judge.items()):
        gap_sum = sum(o.gap_pct for o in obs_list)
        pick_ch = sum(1 for o in obs_list if o.pick_challenger)
        n = len(obs_list)
        shares.append(
            JudgeMarginShare(
                judge_model=judge_model,
                short_name=judge_short_name(judge_model),
                observations=n,
                total_gap_points=round(gap_sum, 2),
                gap_share_pct=round(gap_sum / total_gap * 100, 1) if total_gap else 0.0,
                avg_gap=round(gap_sum / n, 2) if n else 0.0,
                pick_challenger_pct=round(pick_ch / n * 100, 1) if n else 0.0,
            )
        )
    shares.sort(key=lambda s: (-s.gap_share_pct, s.judge_model))
    return shares


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
            lower = min(ch_pct, k_pct)
            higher = max(ch_pct, k_pct)
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
                    lower_pct=round(lower, 2),
                    higher_pct=round(higher, 2),
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


def _finalize_judge_summary(
    judge_model: str,
    acc: _JudgeAccumulator,
    *,
    total_gap: float,
) -> JudgeSampleGapSummary:
    n = len(acc.ch_scores)
    gap_sum = sum(acc.gaps)
    return JudgeSampleGapSummary(
        judge_model=judge_model,
        short_name=judge_short_name(judge_model),
        observations=n,
        distribution=_distribution(acc.counts),
        avg_challenger_pct=round(mean(acc.ch_scores), 2) if n else 0.0,
        avg_king_pct=round(mean(acc.k_scores), 2) if n else 0.0,
        avg_gap_pct=round(mean(acc.gaps), 2) if n else 0.0,
        pick_challenger_pct=round(acc.pick_ch / n * 100, 1) if n else 0.0,
        total_gap_points=round(gap_sum, 2),
        gap_share_pct=round(gap_sum / total_gap * 100, 1) if total_gap else 0.0,
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
    duel_observations: dict[str, list[_Observation]] = defaultdict(list)
    for obs in observations:
        duel_observations[obs.eval_run_id].append(obs)

    total_gap = _total_gap_points(observations)
    all_case_rows = _build_case_rows(observations)
    gap_bands, loser_bands, edge_cases = _split_case_rows(all_case_rows)

    for eval_run_id in sorted(
        duel_meta.keys(),
        key=lambda eid: str(duel_meta[eid].get("finished_at") or ""),
        reverse=True,
    ):
        meta = duel_meta[eval_run_id]
        duel_obs = duel_observations[eval_run_id]
        duel_gap = _total_gap_points(duel_obs)
        duel_cases = _build_case_rows(duel_obs)
        d_gap_bands, _, d_edge = _split_case_rows(duel_cases)
        judges = [
            _finalize_judge_summary(judge_model, acc, total_gap=duel_gap)
            for judge_model, acc in sorted(duel_judge_acc[eval_run_id].items())
        ]
        sample_count = len(duel_samples[eval_run_id])
        obs_count = len(duel_obs)
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
                total_gap_points=round(duel_gap, 2),
                distribution=_distribution(duel_counts[eval_run_id]),
                gap_bands=d_gap_bands,
                edge_cases=[c for c in d_edge if c.observations > 0],
                judge_margin_shares=_build_judge_margin_shares(duel_obs),
                judges=judges,
            )
        )

    return AlbedoSampleScoreAnalysis(
        binary_duels_scanned=len(duel_meta),
        binary_duels_with_samples=len(duel_meta),
        total_samples=sum(len(s) for s in duel_samples.values()),
        total_observations=len(observations),
        total_gap_points=round(total_gap, 2),
        judge_models=judge_models,
        overall=_distribution(overall_counts),
        gap_bands=gap_bands,
        loser_bands=loser_bands,
        edge_cases=[c for c in edge_cases if c.observations > 0],
        judge_margin_shares=_build_judge_margin_shares(observations),
        by_judge=[
            _finalize_judge_summary(judge_model, acc, total_gap=total_gap)
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
