"""Per-question decomposition of challenger vs king rubric margin for one duel."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.albedo_scoring_results import fetch_scoring_results_jsonl
from app.schemas.albedo_scoring_analysis import (
    AlbedoDuelQuestionMarginAnalysis,
    AlbedoQuestionMarginBuckets,
    AlbedoQuestionMarginRow,
)
from app.services.albedo_scoring_analysis_service import (
    CHALLENGER_SIDE,
    KING_SIDE_RAW,
    _duel_export_labels,
    _scoring_results_url,
    duel_export_filename,
    rubric_score_pct,
)

_QID_RE = re.compile(r"^q_(\d+)$", re.IGNORECASE)
DEFAULT_QUESTION_MAX_INDEX = 20


def question_index_from_id(question_id: str) -> int | None:
    m = _QID_RE.match(question_id.strip())
    if not m:
        return None
    return int(m.group(1))


def is_default_question_index(index: int | None) -> bool:
    return index is not None and 1 <= index <= DEFAULT_QUESTION_MAX_INDEX


@dataclass
class _QuestionAccum:
    text: str = ""
    category: str | None = None
    observations: int = 0
    signed_sum: float = 0.0
    abs_sum: float = 0.0


@dataclass
class _MarginAccum:
    per_question: dict[str, _QuestionAccum] = field(default_factory=dict)
    total_abs: float = 0.0
    total_signed: float = 0.0
    observations: int = 0
    sample_count: int = 0
    questions_per_sample: int | None = None


def _answer_numeric(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return 1.0 if float(value) == 1.0 else 0.0
    return 1.0 if str(value).strip().lower() in {"1", "1.0", "true", "yes"} else 0.0


def analyze_question_margin_shares(rows: list[dict[str, Any]]) -> _MarginAccum:
    """Decompose sample×judge margins into per-question absolute contributions."""
    acc = _MarginAccum()

    for row in rows:
        questions = [q for q in (row.get("questions") or []) if isinstance(q, dict) and q.get("id")]
        if not questions:
            continue
        questions.sort(key=lambda q: str(q["id"]))
        qids = [str(q["id"]) for q in questions]
        n = len(qids)
        if n == 0:
            continue
        acc.sample_count += 1
        if acc.questions_per_sample is None:
            acc.questions_per_sample = n
        elif acc.questions_per_sample != n:
            acc.questions_per_sample = -1

        meta_by_id = {str(q["id"]): q for q in questions}

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
            margin = rubric_score_pct(ch_ans, qids) - rubric_score_pct(k_ans, qids)
            acc.total_signed += margin
            acc.observations += 1

            for qid in qids:
                contrib = (_answer_numeric(ch_ans.get(qid)) - _answer_numeric(k_ans.get(qid))) * (
                    100.0 / n
                )
                qmeta = meta_by_id.get(qid) or {}
                slot = acc.per_question.setdefault(qid, _QuestionAccum())
                if not slot.text:
                    slot.text = str(qmeta.get("text") or "")
                    cat = qmeta.get("category")
                    slot.category = str(cat) if cat is not None else None
                slot.observations += 1
                slot.signed_sum += contrib
                abs_c = abs(contrib)
                slot.abs_sum += abs_c
                acc.total_abs += abs_c

    return acc


def build_question_margin_analysis(
    eval_run_id: str,
    rows: list[dict[str, Any]],
    *,
    export_filename: str | None = None,
) -> AlbedoDuelQuestionMarginAnalysis:
    acc = analyze_question_margin_shares(rows)
    total_abs = acc.total_abs

    default_abs = 0.0
    other_abs = 0.0
    out_rows: list[AlbedoQuestionMarginRow] = []

    for qid in sorted(acc.per_question.keys(), key=lambda x: (question_index_from_id(x) or 9999, x)):
        slot = acc.per_question[qid]
        idx = question_index_from_id(qid)
        is_default = is_default_question_index(idx)
        share = (slot.abs_sum / total_abs * 100.0) if total_abs > 0 else 0.0
        if is_default:
            default_abs += slot.abs_sum
        else:
            other_abs += slot.abs_sum
        out_rows.append(
            AlbedoQuestionMarginRow(
                question_id=qid,
                question_index=idx,
                is_default_q1_20=is_default,
                text=slot.text,
                category=slot.category,
                observations=slot.observations,
                signed_margin_sum=round(slot.signed_sum, 4),
                abs_margin_sum=round(slot.abs_sum, 4),
                share_of_abs_margin_pct=round(share, 3),
            )
        )

    if total_abs > 0 and (default_abs + other_abs) < total_abs * 0.999:
        other_abs = max(0.0, total_abs - default_abs)

    buckets = AlbedoQuestionMarginBuckets(
        default_q1_20_abs_sum=round(default_abs, 4),
        other_abs_sum=round(other_abs, 4),
        default_q1_20_share_pct=round(default_abs / total_abs * 100.0, 2) if total_abs > 0 else 0.0,
        other_share_pct=round(other_abs / total_abs * 100.0, 2) if total_abs > 0 else 0.0,
    )

    avg_margin = (
        acc.total_signed / acc.observations if acc.observations > 0 else None
    )

    q_per = acc.questions_per_sample if acc.questions_per_sample and acc.questions_per_sample > 0 else None

    return AlbedoDuelQuestionMarginAnalysis(
        eval_run_id=eval_run_id,
        export_filename=export_filename,
        total_samples=acc.sample_count,
        total_observations=acc.observations,
        questions_per_sample=q_per,
        total_abs_margin=round(total_abs, 4),
        total_signed_margin=round(acc.total_signed, 4),
        avg_margin_pct_per_observation=round(avg_margin, 4) if avg_margin is not None else None,
        buckets=buckets,
        questions=out_rows,
    )


async def get_question_margin_for_eval(
    eval_run_id: str,
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
) -> AlbedoDuelQuestionMarginAnalysis:
    settings = settings or get_settings()
    if subnet != 97:
        raise ValueError("question margin analysis is SN97 only")

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

    king_uid, challenger_uid, winner = _duel_export_labels(eval_run)
    export_name = duel_export_filename(
        king_uid=king_uid,
        challenger_uid=challenger_uid,
        winner=winner,
        polarity="zero",
    )

    return build_question_margin_analysis(
        eval_run_id,
        rows,
        export_filename=export_name,
    )
