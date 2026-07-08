"""Analyze Albedo scoring-results.jsonl for GLM + Qwen dual-zero on both duel sides."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.albedo_scoring_results import fetch_scoring_results_jsonl
from app.schemas.albedo_scoring_analysis import (
    AlbedoDualZeroQuestion,
    AlbedoSampleDualZeros,
    AlbedoScoringAnalysis,
)

logger = logging.getLogger(__name__)

GLM_JUDGE_HINT = "glm"
QWEN_JUDGE_HINT = "qwen"
CHALLENGER_SIDE = "challenger"
KING_SIDE_RAW = "previous_king"


@dataclass(frozen=True)
class ExportPayload:
    content: bytes
    filename: str
    media_type: str


def duel_export_filename(
    *,
    king_uid: int | None,
    challenger_uid: int | None,
    winner: str,
) -> str:
    """Filename: king uid vs challenger uid + who won."""
    k = king_uid if king_uid is not None else "k"
    c = challenger_uid if challenger_uid is not None else "c"
    return f"{k} vs {c} {winner}.jsonl"


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
    return str(value).strip() in {"0", "0.0", "false", "no"}


def analyze_dual_zero_questions(rows: list[dict[str, Any]]) -> AlbedoScoringAnalysis:
    """Questions where GLM and Qwen both score 0 on challenger AND king sides."""
    samples_out: list[AlbedoSampleDualZeros] = []
    total_dual_zero = 0

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
                _answer_is_zero(ch_glm_ans.get(qid))
                and _answer_is_zero(ch_qwen_ans.get(qid))
                and _answer_is_zero(k_glm_ans.get(qid))
                and _answer_is_zero(k_qwen_ans.get(qid))
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
        total_dual_zero += len(dual_questions)
        samples_out.append(
            AlbedoSampleDualZeros(
                sample_id=sample_id,
                dual_zero_count=len(dual_questions),
                questions=dual_questions,
            )
        )

    samples_out.sort(key=lambda s: (-s.dual_zero_count, s.sample_id))
    return AlbedoScoringAnalysis(
        total_samples=len(rows),
        samples_with_dual_zeros=len(samples_out),
        total_dual_zero_questions=total_dual_zero,
        samples=samples_out,
    )


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

    analysis = analyze_dual_zero_questions(rows)
    king_uid, challenger_uid, winner = _duel_export_labels(eval_run)
    return analysis.model_copy(
        update={
            "export_filename": duel_export_filename(
                king_uid=king_uid,
                challenger_uid=challenger_uid,
                winner=winner,
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


def build_dual_zero_export_jsonl(analysis: AlbedoScoringAnalysis) -> str:
    """One JSON line per dual-zero sample in a single JSONL file."""
    lines = [
        json.dumps(build_sample_export_record(sample), ensure_ascii=False)
        for sample in analysis.samples
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def build_dual_zero_export(
    analysis: AlbedoScoringAnalysis,
    *,
    king_uid: int | None,
    challenger_uid: int | None,
    winner: str,
) -> ExportPayload:
    if not analysis.samples:
        raise LookupError("No dual-zero samples to export")

    filename = duel_export_filename(
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
    )
    return ExportPayload(
        content=build_dual_zero_export_jsonl(analysis).encode("utf-8"),
        filename=filename,
        media_type="application/x-ndjson",
    )


async def get_dual_zero_export(
    eval_run_id: str,
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
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

    analysis = analyze_dual_zero_questions(rows)
    king_uid, challenger_uid, winner = _duel_export_labels(eval_run)
    return build_dual_zero_export(
        analysis,
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
    )
