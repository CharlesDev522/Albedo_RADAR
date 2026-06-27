"""Compute cross-dimensional duel analytics from Albedo dashboard JSON."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.schemas.albedo_analysis import (
    AlbedoAnalysisOverview,
    AlbedoCurrentEval,
    AlbedoDuelSummary,
    AlbedoJudgeAggregate,
    AlbedoKingCoronation,
    AlbedoMarginBucket,
    AlbedoMetricAggregate,
    AlbedoPipelineStage,
    AlbedoReignMember,
    AlbedoTimelinePoint,
    AlbedoWinRateRow,
)

MARGIN_BUCKETS: list[tuple[str, float, float]] = [
    ("≤ -20%", -1.0, -0.20),
    ("-20% to -10%", -0.20, -0.10),
    ("-10% to -5%", -0.10, -0.05),
    ("-5% to 0%", -0.05, 0.0),
    ("0% to +5%", 0.0, 0.05),
    ("+5% to +10%", 0.05, 0.10),
    ("+10% to +20%", 0.10, 0.20),
    ("> +20%", 0.20, 1.0),
]


def parse_model_uri(model_uri: str | None) -> tuple[str, str, str]:
    """Return (namespace, model_name, full_uri) from an Albedo model URI."""
    if not model_uri:
        return "", "", ""
    base = model_uri.split("@", 1)[0]
    if "/" in base:
        namespace, model_name = base.split("/", 1)
        return namespace, model_name, model_uri
    return "", base, model_uri


def _parse_iso_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _win_rate_row(
    key: str,
    label: str,
    *,
    duels: int,
    wins: int,
    coronations: int = 0,
    margins: list[float] | None = None,
) -> AlbedoWinRateRow:
    losses = duels - wins
    win_pct = (wins / duels * 100.0) if duels else 0.0
    avg_margin = mean(margins) if margins else None
    return AlbedoWinRateRow(
        key=key,
        label=label,
        duels=duels,
        wins=wins,
        losses=losses,
        win_pct=round(win_pct, 1),
        avg_margin=round(avg_margin, 4) if avg_margin is not None else None,
        coronations=coronations,
    )


def _duel_summary(run: dict[str, Any]) -> AlbedoDuelSummary:
    ns, name, uri = parse_model_uri(run.get("model_uri"))
    king = run.get("king") or {}
    k_ns, k_name, k_uri = parse_model_uri(king.get("model_uri"))
    return AlbedoDuelSummary(
        eval_run_id=run.get("eval_run_id", ""),
        finished_at=run.get("finished_at", ""),
        challenger_won=bool(run.get("challenger_won")),
        coronated=bool(run.get("coronated")),
        king_version=run.get("king_version"),
        score_challenger=float(run.get("score_challenger") or 0),
        score_king=float(run.get("score_king") or 0),
        win_margin=float(run.get("win_margin") or 0),
        model_uri=uri,
        model_name=name,
        namespace=ns,
        hotkey=run.get("hotkey", ""),
        uid=int(run.get("uid") or 0),
        king_model_uri=k_uri or None,
        king_model_name=k_name or None,
        king_namespace=k_ns or None,
        king_uid=int(king["uid"]) if king.get("uid") is not None else None,
        king_hotkey=king.get("hotkey"),
        king_version_defended=int(king["king_version"]) if king.get("king_version") is not None else None,
        valid_turns=run.get("valid_turns"),
        total_turns=run.get("total_turns"),
    )


def _reign_member(member: dict[str, Any]) -> AlbedoReignMember:
    ns, name, uri = parse_model_uri(member.get("model_uri"))
    return AlbedoReignMember(
        king_version=int(member.get("king_version") or 0),
        model_uri=uri,
        model_name=name,
        namespace=ns,
        hotkey=member.get("hotkey", ""),
        uid=int(member.get("uid") or 0),
        weight_bps=int(member.get("weight_bps") or 0),
        score_challenger=member.get("score_challenger"),
        score_king=member.get("score_king"),
        eval_run_id=member.get("eval_run_id"),
    )


def _current_eval(raw: dict[str, Any] | None) -> AlbedoCurrentEval | None:
    if not raw:
        return None
    ns, name, uri = parse_model_uri(raw.get("model_uri"))
    return AlbedoCurrentEval(
        eval_run_id=raw.get("eval_run_id", ""),
        state=raw.get("state", ""),
        model_uri=uri,
        model_name=name,
        namespace=ns,
        hotkey=raw.get("hotkey", ""),
        uid=int(raw.get("uid") or 0),
        sample_count=raw.get("sample_count"),
        generated_sample_count=raw.get("generated_sample_count"),
        started_at=raw.get("started_at"),
    )


def _margin_bucket(margin: float) -> str:
    for label, lo, hi in MARGIN_BUCKETS:
        if lo < margin <= hi or (label.startswith("≤") and margin <= hi) or (label.startswith(">") and margin > lo):
            return label
    return MARGIN_BUCKETS[-1][0]


def _build_pipeline(state: dict[str, Any] | None) -> list[AlbedoPipelineStage]:
    if not state:
        return []
    stages: list[AlbedoPipelineStage] = []
    for key, value in state.items():
        if not isinstance(value, dict):
            continue
        stages.append(
            AlbedoPipelineStage(
                stage=key,
                status=value.get("state") or value.get("status"),
                detail=value.get("detail") or value.get("message"),
            )
        )
    return stages


def build_analysis_overview(
    dashboard: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    subnet: int = 97,
    source_url: str,
) -> AlbedoAnalysisOverview:
    eval_runs: list[dict[str, Any]] = list(dashboard.get("eval_runs") or [])
    reign_members = [_reign_member(m) for m in (dashboard.get("reign") or {}).get("members") or []]
    judge_models = list((dashboard.get("chain") or {}).get("judge_models") or [])

    challenger_wins = sum(1 for r in eval_runs if r.get("challenger_won"))
    king_wins = len(eval_runs) - challenger_wins
    coronations = sum(1 for r in eval_runs if r.get("coronated"))
    total = len(eval_runs)

    margins = [float(r.get("win_margin") or 0) for r in eval_runs]
    ch_scores = [float(r.get("score_challenger") or 0) for r in eval_runs]
    k_scores = [float(r.get("score_king") or 0) for r in eval_runs]

    ns_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0})
    hk_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0, "uid": None})
    king_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": []})
    judge_scores: dict[str, list[float]] = defaultdict(list)
    metric_scores: dict[str, list[float]] = defaultdict(list)
    margin_counts: dict[str, int] = defaultdict(int)
    timeline_raw: dict[str, dict[str, int]] = defaultdict(lambda: {"duels": 0, "ch_wins": 0, "k_wins": 0, "coronations": 0})

    king_history: list[AlbedoKingCoronation] = []

    for run in eval_runs:
        summary = _duel_summary(run)
        ns = summary.namespace or "unknown"
        hk = summary.hotkey or "unknown"
        won = summary.challenger_won
        margin = summary.win_margin

        ns_stats[ns]["duels"] += 1
        hk_stats[hk]["duels"] += 1
        hk_stats[hk]["uid"] = summary.uid
        if won:
            ns_stats[ns]["wins"] += 1
            hk_stats[hk]["wins"] += 1
        ns_stats[ns]["margins"].append(margin)
        hk_stats[hk]["margins"].append(margin)

        king_key = summary.king_model_uri or summary.king_model_name or "unknown"
        king_stats[king_key]["duels"] += 1
        if not won:
            king_stats[king_key]["wins"] += 1
        king_stats[king_key]["margins"].append(-margin)

        breakdown = run.get("score_breakdown") or {}
        for judge, score in (breakdown.get("by_judge") or {}).items():
            judge_scores[str(judge)].append(float(score))
        for metric, score in (breakdown.get("by_metric") or {}).items():
            metric_scores[str(metric)].append(float(score))

        margin_counts[_margin_bucket(margin)] += 1

        day = _parse_iso_date(run.get("finished_at"))
        if day:
            timeline_raw[day]["duels"] += 1
            if won:
                timeline_raw[day]["ch_wins"] += 1
            else:
                timeline_raw[day]["k_wins"] += 1
            if run.get("coronated"):
                timeline_raw[day]["coronations"] += 1

        if run.get("coronated"):
            ns_stats[ns]["coronations"] += 1
            hk_stats[hk]["coronations"] += 1
            defeated = run.get("king") or {}
            d_ns, d_name, d_uri = parse_model_uri(defeated.get("model_uri"))
            king_history.append(
                AlbedoKingCoronation(
                    king_version=int(run.get("king_version") or 0),
                    model_uri=summary.model_uri,
                    model_name=summary.model_name,
                    namespace=summary.namespace,
                    hotkey=summary.hotkey,
                    uid=summary.uid,
                    finished_at=summary.finished_at,
                    eval_run_id=summary.eval_run_id,
                    score_challenger=summary.score_challenger,
                    score_king=summary.score_king,
                    win_margin=summary.win_margin,
                    defeated_king_version=defeated.get("king_version"),
                    defeated_model_uri=d_uri or None,
                    defeated_model_name=d_name or None,
                    defeated_namespace=d_ns or None,
                )
            )

    king_history.sort(key=lambda k: k.king_version, reverse=True)

    def _sorted_rows(
        stats: dict[str, dict[str, Any]],
        label_fn,
        *,
        min_duels: int = 1,
        include_coronations: bool = False,
    ) -> list[AlbedoWinRateRow]:
        rows: list[AlbedoWinRateRow] = []
        for key, s in stats.items():
            if s["duels"] < min_duels:
                continue
            rows.append(
                _win_rate_row(
                    key,
                    label_fn(key, s),
                    duels=s["duels"],
                    wins=s["wins"],
                    coronations=s.get("coronations", 0) if include_coronations else 0,
                    margins=s.get("margins"),
                )
            )
        rows.sort(key=lambda r: (-r.duels, -r.win_pct))
        return rows

    challenger_by_namespace = _sorted_rows(
        ns_stats,
        lambda k, _s: k,
        min_duels=2,
        include_coronations=True,
    )[:20]

    challenger_by_hotkey = _sorted_rows(
        hk_stats,
        lambda k, s: f"uid {s.get('uid')} · {k[:8]}…" if len(k) > 12 else f"uid {s.get('uid')} · {k}",
        min_duels=2,
        include_coronations=True,
    )[:20]

    king_defense_by_model = _sorted_rows(
        king_stats,
        lambda k, _s: parse_model_uri(k)[1] or k,
        min_duels=3,
    )[:15]

    judge_aggregates = [
        AlbedoJudgeAggregate(
            judge=judge,
            avg_challenger_score=round(mean(scores), 4),
            duels=len(scores),
        )
        for judge, scores in sorted(judge_scores.items(), key=lambda x: x[0])
    ]

    metric_aggregates = [
        AlbedoMetricAggregate(
            metric=metric,
            avg_challenger_score=round(mean(scores), 4),
            duels=len(scores),
        )
        for metric, scores in sorted(metric_scores.items(), key=lambda x: -mean(x[1]))
    ]

    margin_histogram = [
        AlbedoMarginBucket(label=label, count=margin_counts.get(label, 0))
        for label, _, _ in MARGIN_BUCKETS
    ]

    timeline = [
        AlbedoTimelinePoint(
            date=day,
            duels=v["duels"],
            challenger_wins=v["ch_wins"],
            king_wins=v["k_wins"],
            coronations=v["coronations"],
            challenger_win_pct=round(v["ch_wins"] / v["duels"] * 100, 1) if v["duels"] else 0.0,
        )
        for day, v in sorted(timeline_raw.items())
    ]

    recent_duels = [_duel_summary(r) for r in eval_runs[:40]]

    return AlbedoAnalysisOverview(
        subnet=subnet,
        source_url=source_url,
        updated_at=dashboard.get("updated_at"),
        judge_models=judge_models,
        total_duels=total,
        challenger_wins=challenger_wins,
        king_wins=king_wins,
        coronations=coronations,
        challenger_win_pct=round(challenger_wins / total * 100, 1) if total else 0.0,
        king_win_pct=round(king_wins / total * 100, 1) if total else 0.0,
        avg_win_margin=round(mean(margins), 4) if margins else None,
        avg_challenger_score=round(mean(ch_scores), 4) if ch_scores else None,
        avg_king_score=round(mean(k_scores), 4) if k_scores else None,
        reign=reign_members,
        current_king=reign_members[0] if reign_members else None,
        current_eval=_current_eval(dashboard.get("current_eval")),
        queue_length=len(dashboard.get("queue") or []),
        king_history=king_history,
        recent_duels=recent_duels,
        challenger_by_namespace=challenger_by_namespace,
        challenger_by_hotkey=challenger_by_hotkey,
        king_defense_by_model=king_defense_by_model,
        judge_aggregates=judge_aggregates,
        metric_aggregates=metric_aggregates,
        margin_histogram=margin_histogram,
        timeline=timeline,
        pipeline=_build_pipeline(state),
        note="Live duel data from Hippius Albedo dashboard JSON (eval_runs + reign chain).",
    )


async def get_albedo_analysis_overview(
    subnet: int = 97,
    *,
    settings: Settings | None = None,
) -> AlbedoAnalysisOverview:
    settings = settings or get_settings()
    source_url = f"{settings.albedo_dashboard_url.rstrip('/')}/data/dashboard.json"
    dashboard = await fetch_dashboard(settings=settings)
    state_payload: dict[str, Any] | None = None
    try:
        state_payload = await fetch_state(settings=settings)
    except Exception:
        state_payload = None
    return build_analysis_overview(
        dashboard,
        state=state_payload,
        subnet=subnet,
        source_url=source_url,
    )
