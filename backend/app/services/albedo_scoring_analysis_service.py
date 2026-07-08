"""Analyze Albedo scoring-results.jsonl for GLM + Qwen dual-zero on both duel sides."""

from __future__ import annotations

import json
import logging
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

    return analyze_dual_zero_questions(rows)


def dual_zero_export_filename(eval_run_id: str) -> str:
    short = eval_run_id.replace("-", "")[:8]
    return f"dual-zero-both-{short}.jsonl"


def build_dual_zero_export_jsonl(analysis: AlbedoScoringAnalysis) -> str:
    """Minimal JSONL: sample_id + question_id + four judge reasons per dual-zero question."""
    lines: list[str] = []
    for sample in analysis.samples:
        record = {
            "sample_id": sample.sample_id,
            "questions": [
                {
                    "question_id": q.question_id,
                    "challenger_glm": q.challenger_glm,
                    "challenger_qwen": q.challenger_qwen,
                    "king_glm": q.king_glm,
                    "king_qwen": q.king_qwen,
                }
                for q in sample.questions
            ],
        }
        lines.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


async def get_dual_zero_export_jsonl(
    eval_run_id: str,
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
) -> tuple[str, str]:
    analysis = await get_scoring_analysis_for_eval(
        eval_run_id,
        subnet=subnet,
        settings=settings,
        fresh=fresh,
    )
    return build_dual_zero_export_jsonl(analysis), dual_zero_export_filename(eval_run_id)
