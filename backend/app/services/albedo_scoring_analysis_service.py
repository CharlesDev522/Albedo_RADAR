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
    ScoringConsensusPolarity,
)

logger = logging.getLogger(__name__)

GLM_JUDGE_HINT = "glm"
QWEN_JUDGE_HINT = "qwen"
CHALLENGER_SIDE = "challenger"
KING_SIDE_RAW = "previous_king"

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


def build_sample_export_json(sample: AlbedoSampleDualZeros) -> str:
    return json.dumps(build_sample_export_record(sample), ensure_ascii=False) + "\n"


def build_consensus_export_jsonl(analysis: AlbedoScoringAnalysis) -> str:
    """One JSON line per matching sample in a single JSONL file."""
    lines = [
        json.dumps(build_sample_export_record(sample), ensure_ascii=False)
        for sample in analysis.samples
    ]
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
    binary_runs = _binary_eval_runs(eval_runs)

    all_records: list[dict[str, Any]] = []
    duels_with_matches = 0

    async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
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
            if not analysis.samples:
                continue
            duels_with_matches += 1
            for sample in analysis.samples:
                all_records.append(build_sample_export_record(sample))

    unique_records, duplicates_removed = dedupe_records_by_sample_id(all_records)
    total_questions = sum(len(record.get("questions") or []) for record in unique_records)
    summary = AlbedoDatasetBuildSummary(
        polarity=polarity,
        export_filename=_DATASET_EXPORT_FILENAMES[polarity],
        dedup_script_filename=_DEDUP_SCRIPT_FILENAME,
        binary_duels_total=binary_total,
        binary_duels_with_scoring=len(binary_runs),
        binary_duels_with_dual_zero=duels_with_matches,
        samples_before_dedup=len(all_records),
        unique_samples=len(unique_records),
        duplicates_removed=duplicates_removed,
        total_dual_zero_questions=total_questions,
    )
    result = DatasetBuildResult(summary=summary, records=unique_records)
    if not fresh:
        _dataset_cache_set(polarity, result)
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
    if not analysis.samples:
        raise LookupError(f"No {_polarity_label(polarity)} samples to export")

    filename = duel_export_filename(
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
        polarity=polarity,
    )
    return ExportPayload(
        content=build_consensus_export_jsonl(analysis).encode("utf-8"),
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
