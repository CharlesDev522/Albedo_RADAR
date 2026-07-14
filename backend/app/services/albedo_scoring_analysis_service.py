"""Analyze Albedo scoring-results.jsonl for GLM + Qwen dual-zero / dual-one on both sides."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.albedo_scoring_results import fetch_scoring_results_jsonl
from app.schemas.albedo_scoring_analysis import (
    AlbedoDatasetBuildSummary,
    AlbedoDualZeroQuestion,
    AlbedoSampleDualZeros,
    AlbedoScoringAnalysis,
    KingReignDatasetSlice,
    ScoringConsensusPolarity,
)

logger = logging.getLogger(__name__)

GLM_JUDGE_HINT = "glm"
QWEN_JUDGE_HINT = "qwen"
CHALLENGER_SIDE = "challenger"
KING_SIDE_RAW = "previous_king"

_DATASET_RECENT_DUELS_LIMIT = 20
_DATASET_MIN_QUESTIONS_PER_SAMPLE = 5
_DATASET_EXPORT_FILENAMES: dict[ScoringConsensusPolarity, str] = {
    "zero": "binary-dual-zero-dataset.jsonl",
    "one": "binary-dual-one-dataset.jsonl",
}
_DEDUP_SCRIPT_FILENAME = "dedup_dual_zero_jsonl.py"
_DEDUP_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / _DEDUP_SCRIPT_FILENAME

_DATASET_CACHE: dict[str, tuple[float, "DatasetBuildResult"]] = {}
_DATASET_CACHE_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class ExportPayload:
    content: bytes
    filename: str
    media_type: str


@dataclass(frozen=True)
class DatasetBuildResult:
    summary: AlbedoDatasetBuildSummary
    records: list[dict[str, Any]]


def duel_export_filename(
    *,
    king_uid: int | None,
    challenger_uid: int | None,
    winner: str,
    polarity: ScoringConsensusPolarity = "zero",
) -> str:
    """Filename: king uid vs challenger uid + who won + polarity suffix."""
    k = king_uid if king_uid is not None else "k"
    c = challenger_uid if challenger_uid is not None else "c"
    suffix = "dual-zero" if polarity == "zero" else "dual-one"
    return f"{k} vs {c} {winner} {suffix}.jsonl"


def _is_glm_judge(model: str | None) -> bool:
    return GLM_JUDGE_HINT in (model or "").lower()


def _is_qwen_judge(model: str | None) -> bool:
    return QWEN_JUDGE_HINT in (model or "").lower()


def _judge_entry(
    sample: dict[str, Any],
    *,
    predicate,
    side: str,
) -> dict[str, Any] | None:
    for entry in sample.get("judge_results") or []:
        if entry.get("side") != side:
            continue
        if predicate(entry.get("judge_model")):
            return entry
    return None


def _answer_is_zero(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return float(value) == 0.0
    return str(value).strip().lower() in {"0", "0.0", "false", "no"}


def _answer_is_one(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) == 1.0
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def _answer_matches_polarity(value: Any, polarity: ScoringConsensusPolarity) -> bool:
    if polarity == "zero":
        return _answer_is_zero(value)
    return _answer_is_one(value)


def rubric_score_pct(answers: dict[str, Any], question_ids: list[str]) -> float:
    if not question_ids:
        return 0.0
    hits = sum(1 for qid in question_ids if _answer_is_one(answers.get(qid)))
    return hits / len(question_ids) * 100.0


def analyze_dual_consensus_questions(
    rows: list[dict[str, Any]],
    *,
    polarity: ScoringConsensusPolarity = "zero",
) -> AlbedoScoringAnalysis:
    """Questions where GLM and Qwen both score 0 or 1 on challenger AND king sides."""
    samples_out: list[AlbedoSampleDualZeros] = []
    total_matches = 0
    matches = _answer_matches_polarity

    for row in rows:
        ch_glm = _judge_entry(row, predicate=_is_glm_judge, side=CHALLENGER_SIDE)
        ch_qwen = _judge_entry(row, predicate=_is_qwen_judge, side=CHALLENGER_SIDE)
        k_glm = _judge_entry(row, predicate=_is_glm_judge, side=KING_SIDE_RAW)
        k_qwen = _judge_entry(row, predicate=_is_qwen_judge, side=KING_SIDE_RAW)
        if not (ch_glm and ch_qwen and k_glm and k_qwen):
            continue

        ch_glm_ans: dict[str, Any] = ch_glm.get("answers") or {}
        ch_qwen_ans: dict[str, Any] = ch_qwen.get("answers") or {}
        k_glm_ans: dict[str, Any] = k_glm.get("answers") or {}
        k_qwen_ans: dict[str, Any] = k_qwen.get("answers") or {}
        ch_glm_expl: dict[str, str] = ch_glm.get("explanations") or {}
        ch_qwen_expl: dict[str, str] = ch_qwen.get("explanations") or {}
        k_glm_expl: dict[str, str] = k_glm.get("explanations") or {}
        k_qwen_expl: dict[str, str] = k_qwen.get("explanations") or {}
        question_map = {q.get("id"): q for q in (row.get("questions") or []) if q.get("id")}

        dual_questions: list[AlbedoDualZeroQuestion] = []
        for qid, question in sorted(question_map.items()):
            if not (
                matches(ch_glm_ans.get(qid), polarity)
                and matches(ch_qwen_ans.get(qid), polarity)
                and matches(k_glm_ans.get(qid), polarity)
                and matches(k_qwen_ans.get(qid), polarity)
            ):
                continue
            dual_questions.append(
                AlbedoDualZeroQuestion(
                    question_id=str(qid),
                    text=str(question.get("text") or ""),
                    example_bad=question.get("example_bad"),
                    challenger_glm=ch_glm_expl.get(qid),
                    challenger_qwen=ch_qwen_expl.get(qid),
                    king_glm=k_glm_expl.get(qid),
                    king_qwen=k_qwen_expl.get(qid),
                )
            )

        if not dual_questions:
            continue

        sample_id = str(row.get("sample_id") or "")
        total_matches += len(dual_questions)
        samples_out.append(
            AlbedoSampleDualZeros(
                sample_id=sample_id,
                dual_zero_count=len(dual_questions),
                questions=dual_questions,
            )
        )

    samples_out.sort(key=lambda s: (-s.dual_zero_count, s.sample_id))
    return AlbedoScoringAnalysis(
        polarity=polarity,
        total_samples=len(rows),
        samples_with_dual_zeros=len(samples_out),
        total_dual_zero_questions=total_matches,
        samples=samples_out,
    )


def analyze_dual_zero_questions(rows: list[dict[str, Any]]) -> AlbedoScoringAnalysis:
    return analyze_dual_consensus_questions(rows, polarity="zero")


def analyze_dual_one_questions(rows: list[dict[str, Any]]) -> AlbedoScoringAnalysis:
    return analyze_dual_consensus_questions(rows, polarity="one")


def _scoring_results_url(eval_run: dict[str, Any]) -> str | None:
    artifacts = eval_run.get("artifacts") or {}
    url = artifacts.get("SCORING_RESULTS") or artifacts.get("scoring_results")
    return str(url) if url else None


def _duel_export_labels(eval_run: dict[str, Any]) -> tuple[int | None, int | None, str]:
    king = eval_run.get("king") or {}
    king_uid_raw = king.get("uid")
    challenger_uid_raw = eval_run.get("uid")
    king_uid = int(king_uid_raw) if king_uid_raw is not None else None
    challenger_uid = int(challenger_uid_raw) if challenger_uid_raw is not None else None
    winner = "challenger" if eval_run.get("challenger_won") else "king"
    return king_uid, challenger_uid, winner


async def get_scoring_analysis_for_eval(
    eval_run_id: str,
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> AlbedoScoringAnalysis:
    settings = settings or get_settings()
    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_run = next(
        (r for r in dashboard.get("eval_runs") or [] if r.get("eval_run_id") == eval_run_id),
        None,
    )
    if eval_run is None:
        raise LookupError(f"eval_run_id not found: {eval_run_id}")

    url = _scoring_results_url(eval_run)
    if not url:
        raise LookupError(f"No SCORING_RESULTS artifact for eval_run_id {eval_run_id}")

    async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
        rows = await fetch_scoring_results_jsonl(url, settings=settings, client=client, fresh=fresh)

    analysis = analyze_dual_consensus_questions(rows, polarity=polarity)
    king_uid, challenger_uid, winner = _duel_export_labels(eval_run)
    return analysis.model_copy(
        update={
            "export_filename": duel_export_filename(
                king_uid=king_uid,
                challenger_uid=challenger_uid,
                winner=winner,
                polarity=polarity,
            )
        }
    )


def build_sample_export_record(sample: AlbedoSampleDualZeros) -> dict[str, Any]:
    return {
        "sample_id": sample.sample_id,
        "questions": [
            {
                "question_id": q.question_id,
                "text": q.text,
                "example_bad": q.example_bad,
                "challenger_glm": q.challenger_glm,
                "challenger_qwen": q.challenger_qwen,
                "king_glm": q.king_glm,
                "king_qwen": q.king_qwen,
            }
            for q in sample.questions
        ],
    }


def sample_meets_export_question_minimum(sample: AlbedoSampleDualZeros) -> bool:
    """Exported JSONL rows require more than five consensus question_ids per sample."""
    return len(sample.questions) > _DATASET_MIN_QUESTIONS_PER_SAMPLE


def export_records_from_analysis(
    analysis: AlbedoScoringAnalysis,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    skipped = 0
    for sample in analysis.samples:
        if sample_meets_export_question_minimum(sample):
            records.append(build_sample_export_record(sample))
        else:
            skipped += 1
    return records, skipped


def build_sample_export_json(sample: AlbedoSampleDualZeros) -> str:
    return json.dumps(build_sample_export_record(sample), ensure_ascii=False) + "\n"


def build_consensus_export_jsonl(analysis: AlbedoScoringAnalysis) -> str:
    """One JSON line per matching sample in a single JSONL file."""
    records, _ = export_records_from_analysis(analysis)
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    return "\n".join(lines) + ("\n" if lines else "")


def build_dual_zero_export_jsonl(analysis: AlbedoScoringAnalysis) -> str:
    return build_consensus_export_jsonl(analysis)


def dedupe_records_by_sample_id(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Keep the first JSONL record per sample_id; drop later duplicates."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    removed = 0
    for record in records:
        sample_id = str(record.get("sample_id") or "")
        if not sample_id:
            unique.append(record)
            continue
        if sample_id in seen:
            removed += 1
            continue
        seen.add(sample_id)
        unique.append(record)
    return unique, removed


def build_dataset_export_jsonl(records: list[dict[str, Any]]) -> str:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    return "\n".join(lines) + ("\n" if lines else "")


def _binary_eval_runs(eval_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        run
        for run in eval_runs
        if run.get("scoring_mode") == "binary" and _scoring_results_url(run)
    ]


def _recent_binary_eval_runs(
    eval_runs: list[dict[str, Any]],
    *,
    limit: int = _DATASET_RECENT_DUELS_LIMIT,
) -> list[dict[str, Any]]:
    """Latest finished binary duels with scoring artifacts (newest first)."""
    binary_runs = _binary_eval_runs(eval_runs)
    binary_runs.sort(key=lambda r: str(r.get("finished_at") or ""), reverse=True)
    return binary_runs[:limit]


def _coronations_from_eval_runs(eval_runs: list[dict[str, Any]]) -> list[Any]:
    from app.services.albedo_king_history import coronation_from_eval_run

    coronations = []
    for run in eval_runs:
        cor = coronation_from_eval_run(run, None)
        if cor:
            coronations.append(cor)
    return sorted(coronations, key=lambda c: c.king_version)


def _king_reign_windows(
    coronations: list[Any],
) -> dict[int, tuple[str, str | None]]:
    """Map king_version -> (coronation_at, active_until). active_until is next coronation."""
    sorted_asc = sorted(coronations, key=lambda c: c.king_version)
    windows: dict[int, tuple[str, str | None]] = {}
    for idx, cor in enumerate(sorted_asc):
        active_until = sorted_asc[idx + 1].finished_at if idx + 1 < len(sorted_asc) else None
        windows[cor.king_version] = (cor.finished_at, active_until)
    return windows


def _binary_eval_runs_for_king_reign(
    eval_runs: list[dict[str, Any]],
    *,
    king_version: int,
    coronation_at: str,
    active_until: str | None,
) -> list[dict[str, Any]]:
    """Binary rubric duels defended by this king during their reign window."""
    runs: list[dict[str, Any]] = []
    for run in _binary_eval_runs(eval_runs):
        king = run.get("king") or {}
        if king.get("king_version") != king_version:
            continue
        finished = str(run.get("finished_at") or "")
        if finished < coronation_at:
            continue
        if active_until and finished > active_until:
            continue
        runs.append(run)
    runs.sort(key=lambda r: str(r.get("finished_at") or ""), reverse=True)
    return runs


def _kings_dataset_export_filename(
    polarity: ScoringConsensusPolarity,
    king_versions: list[int],
) -> str:
    suffix = "dual-zero" if polarity == "zero" else "dual-one"
    ordered = sorted(king_versions)
    if len(ordered) == 1:
        return f"binary-{suffix}-king-v{ordered[0]}-dataset.jsonl"
    version_tag = "-".join(str(v) for v in ordered)
    return f"binary-{suffix}-kings-v{version_tag}-dataset.jsonl"


def _king_reign_dataset_cache_key(
    polarity: ScoringConsensusPolarity,
    king_versions: list[int],
) -> str:
    versions = ",".join(str(v) for v in sorted(king_versions))
    return f"binary_dual_{polarity}_kings_{versions}"


async def _collect_consensus_records(
    binary_runs: list[dict[str, Any]],
    *,
    settings: Settings,
    fresh: bool,
    polarity: ScoringConsensusPolarity,
    client: httpx.AsyncClient,
) -> tuple[list[dict[str, Any]], int, int]:
    all_records: list[dict[str, Any]] = []
    duels_with_matches = 0
    skipped_samples = 0
    for run in binary_runs:
        url = _scoring_results_url(run)
        if not url:
            continue
        try:
            rows = await fetch_scoring_results_jsonl(
                url,
                settings=settings,
                client=client,
                fresh=fresh,
            )
            analysis = analyze_dual_consensus_questions(rows, polarity=polarity)
        except Exception:
            logger.warning(
                "Skipping binary duel dataset row eval_run_id=%s polarity=%s",
                run.get("eval_run_id"),
                polarity,
                exc_info=True,
            )
            continue
        run_records, run_skipped = export_records_from_analysis(analysis)
        skipped_samples += run_skipped
        if not run_records:
            continue
        duels_with_matches += 1
        all_records.extend(run_records)
    return all_records, duels_with_matches, skipped_samples


def _dataset_cache_key(polarity: ScoringConsensusPolarity) -> str:
    return f"binary_dual_{polarity}"


def _dataset_cache_get(polarity: ScoringConsensusPolarity) -> DatasetBuildResult | None:
    now = time.monotonic()
    cached = _DATASET_CACHE.get(_dataset_cache_key(polarity))
    if cached and cached[0] > now:
        return cached[1]
    return None


def _dataset_cache_set(polarity: ScoringConsensusPolarity, result: DatasetBuildResult) -> None:
    _DATASET_CACHE[_dataset_cache_key(polarity)] = (
        time.monotonic() + _DATASET_CACHE_TTL_SECONDS,
        result,
    )


def _polarity_label(polarity: ScoringConsensusPolarity) -> str:
    return "dual-zero" if polarity == "zero" else "dual-one"


async def build_binary_consensus_dataset(
    *,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> DatasetBuildResult:
    settings = settings or get_settings()
    if not fresh:
        cached = _dataset_cache_get(polarity)
        if cached is not None:
            return cached

    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_runs: list[dict[str, Any]] = list(dashboard.get("eval_runs") or [])
    binary_total = sum(1 for run in eval_runs if run.get("scoring_mode") == "binary")
    binary_runs_all = _binary_eval_runs(eval_runs)
    binary_runs = _recent_binary_eval_runs(eval_runs)

    async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
        all_records, duels_with_matches, skipped_samples = await _collect_consensus_records(
            binary_runs,
            settings=settings,
            fresh=fresh,
            polarity=polarity,
            client=client,
        )

    unique_records, duplicates_removed = dedupe_records_by_sample_id(all_records)
    total_questions = sum(len(record.get("questions") or []) for record in unique_records)
    summary = AlbedoDatasetBuildSummary(
        polarity=polarity,
        export_filename=_DATASET_EXPORT_FILENAMES[polarity],
        dedup_script_filename=_DEDUP_SCRIPT_FILENAME,
        build_mode="recent",
        min_questions_per_sample=_DATASET_MIN_QUESTIONS_PER_SAMPLE + 1,
        recent_duels_limit=_DATASET_RECENT_DUELS_LIMIT,
        binary_duels_total=binary_total,
        binary_duels_with_scoring=len(binary_runs_all),
        binary_duels_scanned=len(binary_runs),
        binary_duels_with_dual_zero=duels_with_matches,
        samples_before_dedup=len(all_records),
        unique_samples=len(unique_records),
        duplicates_removed=duplicates_removed,
        samples_skipped_min_questions=skipped_samples,
        total_dual_zero_questions=total_questions,
    )
    result = DatasetBuildResult(summary=summary, records=unique_records)
    if not fresh:
        _dataset_cache_set(polarity, result)
    return result


async def build_binary_consensus_dataset_for_kings(
    king_versions: list[int],
    *,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> DatasetBuildResult:
    settings = settings or get_settings()
    ordered_versions = sorted({int(v) for v in king_versions if int(v) > 0})
    if not ordered_versions:
        raise ValueError("At least one king_version is required")

    cache_key = _king_reign_dataset_cache_key(polarity, ordered_versions)
    if not fresh:
        cached = _DATASET_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_runs: list[dict[str, Any]] = list(dashboard.get("eval_runs") or [])
    binary_total = sum(1 for run in eval_runs if run.get("scoring_mode") == "binary")
    binary_runs_all = _binary_eval_runs(eval_runs)

    coronations = _coronations_from_eval_runs(eval_runs)
    windows = _king_reign_windows(coronations)
    missing = [v for v in ordered_versions if v not in windows]
    if missing:
        raise LookupError(f"No coronation data for king version(s): {', '.join(map(str, missing))}")

    seen_run_ids: set[str] = set()
    binary_runs: list[dict[str, Any]] = []
    breakdown: list[KingReignDatasetSlice] = []
    run_king: dict[str, int] = {}

    for king_version in ordered_versions:
        coronation_at, active_until = windows[king_version]
        king_runs = _binary_eval_runs_for_king_reign(
            eval_runs,
            king_version=king_version,
            coronation_at=coronation_at,
            active_until=active_until,
        )
        breakdown.append(
            KingReignDatasetSlice(
                king_version=king_version,
                coronation_at=coronation_at,
                active_until=active_until,
                binary_duels_scanned=len(king_runs),
            )
        )
        for run in king_runs:
            eval_run_id = str(run.get("eval_run_id") or "")
            if not eval_run_id or eval_run_id in seen_run_ids:
                continue
            seen_run_ids.add(eval_run_id)
            run_king[eval_run_id] = king_version
            binary_runs.append(run)

    async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
        all_records: list[dict[str, Any]] = []
        duels_with_matches = 0
        skipped_samples = 0
        matches_by_king: dict[int, int] = {v: 0 for v in ordered_versions}
        for run in binary_runs:
            url = _scoring_results_url(run)
            if not url:
                continue
            try:
                rows = await fetch_scoring_results_jsonl(
                    url,
                    settings=settings,
                    client=client,
                    fresh=fresh,
                )
                analysis = analyze_dual_consensus_questions(rows, polarity=polarity)
            except Exception:
                logger.warning(
                    "Skipping king reign dataset eval_run_id=%s polarity=%s",
                    run.get("eval_run_id"),
                    polarity,
                    exc_info=True,
                )
                continue
            run_records, run_skipped = export_records_from_analysis(analysis)
            skipped_samples += run_skipped
            if not run_records:
                continue
            duels_with_matches += 1
            king_version = run_king.get(str(run.get("eval_run_id") or ""))
            if king_version is not None:
                matches_by_king[king_version] = matches_by_king.get(king_version, 0) + 1
            all_records.extend(run_records)

    for slice_row in breakdown:
        slice_row.binary_duels_with_dual_zero = matches_by_king.get(slice_row.king_version, 0)

    unique_records, duplicates_removed = dedupe_records_by_sample_id(all_records)
    total_questions = sum(len(record.get("questions") or []) for record in unique_records)
    summary = AlbedoDatasetBuildSummary(
        polarity=polarity,
        export_filename=_kings_dataset_export_filename(polarity, ordered_versions),
        dedup_script_filename=_DEDUP_SCRIPT_FILENAME,
        build_mode="king_reign",
        king_versions=ordered_versions,
        king_reign_breakdown=breakdown,
        min_questions_per_sample=_DATASET_MIN_QUESTIONS_PER_SAMPLE + 1,
        recent_duels_limit=_DATASET_RECENT_DUELS_LIMIT,
        binary_duels_total=binary_total,
        binary_duels_with_scoring=len(binary_runs_all),
        binary_duels_scanned=len(binary_runs),
        binary_duels_with_dual_zero=duels_with_matches,
        samples_before_dedup=len(all_records),
        unique_samples=len(unique_records),
        duplicates_removed=duplicates_removed,
        samples_skipped_min_questions=skipped_samples,
        total_dual_zero_questions=total_questions,
    )
    result = DatasetBuildResult(summary=summary, records=unique_records)
    if not fresh:
        _DATASET_CACHE[cache_key] = (time.monotonic() + _DATASET_CACHE_TTL_SECONDS, result)
    return result


async def build_binary_dual_zero_dataset(
    *,
    settings: Settings | None = None,
    fresh: bool = False,
) -> DatasetBuildResult:
    return await build_binary_consensus_dataset(settings=settings, fresh=fresh, polarity="zero")


async def build_binary_dual_one_dataset(
    *,
    settings: Settings | None = None,
    fresh: bool = False,
) -> DatasetBuildResult:
    return await build_binary_consensus_dataset(settings=settings, fresh=fresh, polarity="one")


async def get_binary_dataset_summary(
    *,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> AlbedoDatasetBuildSummary:
    return (await build_binary_consensus_dataset(settings=settings, fresh=fresh, polarity=polarity)).summary


async def get_king_reign_dataset_summary(
    king_versions: list[int],
    *,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> AlbedoDatasetBuildSummary:
    return (
        await build_binary_consensus_dataset_for_kings(
            king_versions,
            settings=settings,
            fresh=fresh,
            polarity=polarity,
        )
    ).summary


async def get_binary_dataset_export(
    *,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> ExportPayload:
    result = await build_binary_consensus_dataset(settings=settings, fresh=fresh, polarity=polarity)
    if not result.records:
        raise LookupError(
            f"No {_polarity_label(polarity)} samples found across binary rubric duels"
        )

    return ExportPayload(
        content=build_dataset_export_jsonl(result.records).encode("utf-8"),
        filename=result.summary.export_filename,
        media_type="application/x-ndjson",
    )


async def get_king_reign_dataset_export(
    king_versions: list[int],
    *,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> ExportPayload:
    result = await build_binary_consensus_dataset_for_kings(
        king_versions,
        settings=settings,
        fresh=fresh,
        polarity=polarity,
    )
    if not result.records:
        raise LookupError(
            f"No {_polarity_label(polarity)} samples found for king reign dataset "
            f"(versions {sorted(set(king_versions))})"
        )

    return ExportPayload(
        content=build_dataset_export_jsonl(result.records).encode("utf-8"),
        filename=result.summary.export_filename,
        media_type="application/x-ndjson",
    )


def get_dedup_script_export() -> ExportPayload:
    if not _DEDUP_SCRIPT_PATH.is_file():
        raise LookupError(f"Dedup script not found: {_DEDUP_SCRIPT_PATH.name}")
    return ExportPayload(
        content=_DEDUP_SCRIPT_PATH.read_bytes(),
        filename=_DEDUP_SCRIPT_FILENAME,
        media_type="text/x-python",
    )


def build_consensus_export(
    analysis: AlbedoScoringAnalysis,
    *,
    king_uid: int | None,
    challenger_uid: int | None,
    winner: str,
) -> ExportPayload:
    polarity = analysis.polarity
    exportable = [s for s in analysis.samples if sample_meets_export_question_minimum(s)]
    if not exportable:
        raise LookupError(
            f"No {_polarity_label(polarity)} samples with more than "
            f"{_DATASET_MIN_QUESTIONS_PER_SAMPLE} questions to export"
        )

    filename = duel_export_filename(
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
        polarity=polarity,
    )
    filtered = analysis.model_copy(update={"samples": exportable})
    return ExportPayload(
        content=build_consensus_export_jsonl(filtered).encode("utf-8"),
        filename=filename,
        media_type="application/x-ndjson",
    )


def build_dual_zero_export(
    analysis: AlbedoScoringAnalysis,
    *,
    king_uid: int | None,
    challenger_uid: int | None,
    winner: str,
) -> ExportPayload:
    return build_consensus_export(
        analysis,
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
    )


async def get_consensus_export(
    eval_run_id: str,
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
    polarity: ScoringConsensusPolarity = "zero",
) -> ExportPayload:
    settings = settings or get_settings()
    dashboard = await fetch_dashboard(settings=settings, fresh=fresh)
    eval_run = next(
        (r for r in dashboard.get("eval_runs") or [] if r.get("eval_run_id") == eval_run_id),
        None,
    )
    if eval_run is None:
        raise LookupError(f"eval_run_id not found: {eval_run_id}")

    url = _scoring_results_url(eval_run)
    if not url:
        raise LookupError(f"No SCORING_RESULTS artifact for eval_run_id {eval_run_id}")

    async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
        rows = await fetch_scoring_results_jsonl(url, settings=settings, client=client, fresh=fresh)

    analysis = analyze_dual_consensus_questions(rows, polarity=polarity)
    king_uid, challenger_uid, winner = _duel_export_labels(eval_run)
    return build_consensus_export(
        analysis,
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
    )


async def get_dual_zero_export(
    eval_run_id: str,
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
) -> ExportPayload:
    return await get_consensus_export(
        eval_run_id,
        subnet=subnet,
        settings=settings,
        fresh=fresh,
        polarity="zero",
    )
