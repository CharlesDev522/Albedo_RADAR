"""Analyze Albedo scoring-results.jsonl for GLM + Qwen dual-zero rubric questions."""

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
from app.services.albedo_analysis_service import parse_model_uri

logger = logging.getLogger(__name__)

GLM_JUDGE_HINT = "glm"
QWEN_JUDGE_HINT = "qwen"
CHALLENGER_SIDE = "challenger"
KING_SIDE_RAW = "previous_king"

SIDE_DESCRIPTIONS = {
    CHALLENGER_SIDE: "Rubric questions scored against the challenger's answer for each duel sample.",
    KING_SIDE_RAW: "Rubric questions scored against the king's answer for each duel sample.",
}


def normalize_side_param(side: str | None) -> tuple[str, str]:
    """Map API side (challenger|king) to JSONL judge_results.side value."""
    raw = (side or CHALLENGER_SIDE).strip().lower()
    if raw in {"king", "previous_king", "k"}:
        return "king", KING_SIDE_RAW
    return CHALLENGER_SIDE, CHALLENGER_SIDE


def side_label(api_side: str) -> str:
    if api_side == "king":
        return "King model output"
    return "Challenger model output"


def side_description(raw_side: str) -> str:
    return SIDE_DESCRIPTIONS.get(raw_side, SIDE_DESCRIPTIONS[CHALLENGER_SIDE])


def _is_glm_judge(model: str | None) -> bool:
    return GLM_JUDGE_HINT in (model or "").lower()


def _is_qwen_judge(model: str | None) -> bool:
    return QWEN_JUDGE_HINT in (model or "").lower()


def _sample_label(sample_id: str) -> str:
    if ":" in sample_id:
        tail = sample_id.rsplit(":", 2)
        if len(tail) >= 2:
            return ":".join(tail[-2:])
    if "/" in sample_id:
        return sample_id.rsplit("/", 1)[-1]
    return sample_id


def _judge_entry(
    sample: dict[str, Any],
    *,
    predicate,
    side: str = CHALLENGER_SIDE,
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


def analyze_dual_zero_questions(
    rows: list[dict[str, Any]],
    *,
    glm_judge: str | None = None,
    qwen_judge: str | None = None,
    side: str = CHALLENGER_SIDE,
    api_side: str | None = None,
) -> AlbedoScoringAnalysis:
    """Find rubric questions where GLM and Qwen both scored 0 for one duel side."""
    resolved_api_side = api_side or ("king" if side == KING_SIDE_RAW else CHALLENGER_SIDE)
    resolved_glm = glm_judge
    resolved_qwen = qwen_judge
    samples_out: list[AlbedoSampleDualZeros] = []
    total_dual_zero = 0

    for row in rows:
        glm_entry = _judge_entry(row, predicate=_is_glm_judge, side=side)
        qwen_entry = _judge_entry(row, predicate=_is_qwen_judge, side=side)
        if glm_entry is None or qwen_entry is None:
            continue
        resolved_glm = resolved_glm or glm_entry.get("judge_model")
        resolved_qwen = resolved_qwen or qwen_entry.get("judge_model")

        glm_answers: dict[str, Any] = glm_entry.get("answers") or {}
        qwen_answers: dict[str, Any] = qwen_entry.get("answers") or {}
        glm_expl: dict[str, str] = glm_entry.get("explanations") or {}
        qwen_expl: dict[str, str] = qwen_entry.get("explanations") or {}
        question_map = {q.get("id"): q for q in (row.get("questions") or []) if q.get("id")}

        dual_questions: list[AlbedoDualZeroQuestion] = []
        for qid, question in sorted(question_map.items()):
            if not (_answer_is_zero(glm_answers.get(qid)) and _answer_is_zero(qwen_answers.get(qid))):
                continue
            dual_questions.append(
                AlbedoDualZeroQuestion(
                    question_id=str(qid),
                    category=question.get("category"),
                    text=str(question.get("text") or ""),
                    side=resolved_api_side,
                    glm_explanation=glm_expl.get(qid),
                    qwen_explanation=qwen_expl.get(qid),
                )
            )

        if not dual_questions:
            continue

        sample_id = str(row.get("sample_id") or "")
        total_dual_zero += len(dual_questions)
        samples_out.append(
            AlbedoSampleDualZeros(
                sample_id=sample_id,
                sample_label=_sample_label(sample_id),
                side=resolved_api_side,
                challenger_score=_optional_float(row.get("challenger_score")),
                king_score=_optional_float(row.get("king_score")),
                dual_zero_count=len(dual_questions),
                questions=dual_questions,
            )
        )

    samples_out.sort(key=lambda s: (-s.dual_zero_count, s.sample_id))
    return AlbedoScoringAnalysis(
        eval_run_id="",
        glm_judge=resolved_glm,
        qwen_judge=resolved_qwen,
        side=resolved_api_side,
        side_raw=side,
        side_label=side_label(resolved_api_side),
        side_description=side_description(side),
        total_samples=len(rows),
        samples_with_dual_zeros=len(samples_out),
        total_dual_zero_questions=total_dual_zero,
        samples=samples_out,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    side: str | None = None,
) -> AlbedoScoringAnalysis:
    settings = settings or get_settings()
    api_side, raw_side = normalize_side_param(side)
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

    _, challenger_name, _ = parse_model_uri(eval_run.get("model_uri"))
    king = eval_run.get("king") or {}
    _, king_name, _ = parse_model_uri(king.get("model_uri"))

    analysis = analyze_dual_zero_questions(rows, side=raw_side, api_side=api_side)
    analysis.eval_run_id = eval_run_id
    analysis.scoring_results_url = url
    analysis.challenger_repo = challenger_name or None
    analysis.king_model_name = king_name or None
    analysis.finished_at = eval_run.get("finished_at")
    return analysis


def dual_zero_export_filename(eval_run_id: str, side: str = CHALLENGER_SIDE) -> str:
    short = eval_run_id.replace("-", "")[:8]
    api_side, _ = normalize_side_param(side)
    return f"dual-zero-{api_side}-{short}.jsonl"


def build_dual_zero_export_jsonl(analysis: AlbedoScoringAnalysis) -> str:
    """Serialize dual-zero samples as JSONL — one JSON object per sample_id."""
    lines: list[str] = []
    for sample in analysis.samples:
        record = {
            "eval_run_id": analysis.eval_run_id,
            "finished_at": analysis.finished_at,
            "challenger_repo": analysis.challenger_repo,
            "king_model_name": analysis.king_model_name,
            "glm_judge": analysis.glm_judge,
            "qwen_judge": analysis.qwen_judge,
            "side": analysis.side,
            "side_raw": analysis.side_raw,
            "side_label": analysis.side_label,
            "side_description": analysis.side_description,
            "scoring_results_url": analysis.scoring_results_url,
            "sample_id": sample.sample_id,
            "sample_label": sample.sample_label,
            "challenger_score": sample.challenger_score,
            "king_score": sample.king_score,
            "dual_zero_count": sample.dual_zero_count,
            "questions": [
                {
                    "question_id": q.question_id,
                    "category": q.category,
                    "text": q.text,
                    "side": q.side,
                    "glm_score": 0,
                    "qwen_score": 0,
                    "glm_explanation": q.glm_explanation,
                    "qwen_explanation": q.qwen_explanation,
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
    side: str | None = None,
) -> tuple[str, str]:
    analysis = await get_scoring_analysis_for_eval(
        eval_run_id,
        subnet=subnet,
        settings=settings,
        fresh=fresh,
        side=side,
    )
    return build_dual_zero_export_jsonl(analysis), dual_zero_export_filename(eval_run_id, side or CHALLENGER_SIDE)
