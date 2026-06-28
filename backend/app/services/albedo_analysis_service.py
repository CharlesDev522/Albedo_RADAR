"""Compute cross-dimensional duel analytics from Albedo dashboard JSON."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.schemas.albedo_analysis import (
    AlbedoAnalysisOverview,
    AlbedoCurrentEval,
    AlbedoDuelSummary,
    AlbedoJudgeAggregate,
    AlbedoJudgeConsensus,
    AlbedoJudgeDetail,
    AlbedoKingCoronation,
    AlbedoKingTenure,
    AlbedoMarginBucket,
    AlbedoMetricAggregate,
    AlbedoPipelineStage,
    AlbedoReignMember,
    AlbedoReignSlotHolder,
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

REIGN_CHAIN_SLOTS = 5


def parse_model_uri(model_uri: str | None) -> tuple[str, str, str]:
    """Return (namespace, model_name, full_uri) from an Albedo model URI."""
    if not model_uri:
        return "", "", ""
    base = model_uri.split("@", 1)[0]
    if "/" in base:
        namespace, model_name = base.split("/", 1)
        return namespace, model_name, model_uri
    return "", base, model_uri


def judge_short_name(judge: str) -> str:
    if "/" in judge:
        return judge.rsplit("/", 1)[-1]
    return judge


def _parse_iso_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_iso_date(iso: str | None) -> str | None:
    dt = _parse_iso_dt(iso)
    return dt.date().isoformat() if dt else None


def _hours_between(start: str | None, end: str | None) -> float | None:
    a = _parse_iso_dt(start)
    b = _parse_iso_dt(end)
    if not a or not b:
        return None
    return round((b - a).total_seconds() / 3600.0, 1)


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
    breakdown = run.get("score_breakdown") or {}
    judge_scores = {str(k): float(v) for k, v in (breakdown.get("by_judge") or {}).items()}
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
        judge_scores=judge_scores,
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


def _judge_votes(run: dict[str, Any]) -> dict[str, bool]:
    breakdown = run.get("score_breakdown") or {}
    return {
        str(judge): float(score) > 0.5
        for judge, score in (breakdown.get("by_judge") or {}).items()
    }


def _consensus_pattern(votes: dict[str, bool]) -> str:
    if not votes:
        return "unknown"
    picks = list(votes.values())
    ch = sum(1 for v in picks if v)
    k = len(picks) - ch
    if ch == len(picks):
        return "unanimous_challenger"
    if k == len(picks):
        return "unanimous_king"
    if ch == 2 and k == 1:
        return "split_2_1_challenger"
    if ch == 1 and k == 2:
        return "split_1_2_king"
    return "other_split"


CONSENSUS_LABELS = {
    "unanimous_challenger": "3–0 challenger",
    "unanimous_king": "0–3 king",
    "split_2_1_challenger": "2–1 challenger",
    "split_1_2_king": "1–2 king",
    "other_split": "Other split",
    "unknown": "Unknown",
}


def _build_judge_details(
    eval_runs: list[dict[str, Any]],
    judge_models: list[str],
) -> tuple[list[AlbedoJudgeAggregate], list[AlbedoJudgeDetail], list[AlbedoJudgeConsensus]]:
    per_judge: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "scores": [],
            "pick_challenger": 0,
            "agree": 0,
            "overturn": 0,
            "when_ch_wins": [],
            "when_k_wins": [],
            "unanimous_challenger": 0,
            "unanimous_king": 0,
            "split": 0,
        }
    )
    consensus_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"duels": 0, "ch_wins": 0, "k_wins": 0})

    for run in eval_runs:
        votes = _judge_votes(run)
        pattern = _consensus_pattern(votes)
        consensus_counts[pattern]["duels"] += 1
        if run.get("challenger_won"):
            consensus_counts[pattern]["ch_wins"] += 1
        else:
            consensus_counts[pattern]["k_wins"] += 1

        challenger_won = bool(run.get("challenger_won"))
        breakdown = run.get("score_breakdown") or {}
        by_judge = breakdown.get("by_judge") or {}

        if len(votes) >= 2:
            all_ch = all(votes.values())
            all_k = not any(votes.values())
            for judge in votes:
                if all_ch:
                    per_judge[judge]["unanimous_challenger"] += 1
                elif all_k:
                    per_judge[judge]["unanimous_king"] += 1
                else:
                    per_judge[judge]["split"] += 1

        for judge, score in by_judge.items():
            judge = str(judge)
            s = float(score)
            picks_ch = s > 0.5
            per_judge[judge]["scores"].append(s)
            if picks_ch:
                per_judge[judge]["pick_challenger"] += 1
            if picks_ch == challenger_won:
                per_judge[judge]["agree"] += 1
            else:
                per_judge[judge]["overturn"] += 1
            if challenger_won:
                per_judge[judge]["when_ch_wins"].append(s)
            else:
                per_judge[judge]["when_k_wins"].append(s)

    ordered_judges = judge_models or sorted(per_judge.keys())
    aggregates: list[AlbedoJudgeAggregate] = []
    details: list[AlbedoJudgeDetail] = []

    for judge in ordered_judges:
        stats = per_judge.get(judge)
        if not stats or not stats["scores"]:
            continue
        duels = len(stats["scores"])
        avg = mean(stats["scores"])
        aggregates.append(
            AlbedoJudgeAggregate(
                judge=judge,
                short_name=judge_short_name(judge),
                avg_challenger_score=round(avg, 4),
                duels=duels,
            )
        )
        details.append(
            AlbedoJudgeDetail(
                judge=judge,
                short_name=judge_short_name(judge),
                duels=duels,
                avg_challenger_score=round(avg, 4),
                avg_king_score=round(1.0 - avg, 4),
                pick_challenger_pct=round(stats["pick_challenger"] / duels * 100, 1),
                pick_king_pct=round((duels - stats["pick_challenger"]) / duels * 100, 1),
                agree_verdict_pct=round(stats["agree"] / duels * 100, 1),
                overturn_duels=stats["overturn"],
                avg_score_when_challenger_wins=round(mean(stats["when_ch_wins"]), 4)
                if stats["when_ch_wins"]
                else None,
                avg_score_when_king_wins=round(mean(stats["when_k_wins"]), 4)
                if stats["when_k_wins"]
                else None,
                unanimous_challenger_duels=stats["unanimous_challenger"],
                unanimous_king_duels=stats["unanimous_king"],
                split_duels=stats["split"],
            )
        )

    total = len(eval_runs) or 1
    consensus = [
        AlbedoJudgeConsensus(
            pattern=pattern,
            label=CONSENSUS_LABELS.get(pattern, pattern),
            duels=stats["duels"],
            pct=round(stats["duels"] / total * 100, 1),
            challenger_wins=stats["ch_wins"],
            king_wins=stats["k_wins"],
        )
        for pattern, stats in sorted(
            consensus_counts.items(),
            key=lambda x: -x[1]["duels"],
        )
        if stats["duels"] > 0 and pattern != "unknown"
    ]
    return aggregates, details, consensus


def _build_reign_slot_holders(reign_members: list[AlbedoReignMember]) -> list[AlbedoReignSlotHolder]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"slots": 0, "weight_bps": 0, "versions": [], "uid": 0, "hotkey": "", "label": ""}
    )
    for member in reign_members:
        key = member.hotkey or member.model_uri
        g = grouped[key]
        g["slots"] += 1
        g["weight_bps"] += member.weight_bps
        g["versions"].append(member.king_version)
        g["uid"] = member.uid
        g["hotkey"] = member.hotkey
        g["label"] = f"{member.namespace}/{member.model_name}"
    rows = [
        AlbedoReignSlotHolder(
            key=key,
            label=data["label"],
            hotkey=data["hotkey"],
            uid=data["uid"],
            slots_held=data["slots"],
            weight_bps=data["weight_bps"],
            weight_pct=round(data["weight_bps"] / 100.0, 1),
            king_versions=sorted(data["versions"], reverse=True),
        )
        for key, data in grouped.items()
    ]
    rows.sort(key=lambda r: (-r.slots_held, -r.weight_bps))
    return rows


def _build_king_tenures(
    eval_runs: list[dict[str, Any]],
    reign_members: list[AlbedoReignMember],
    king_history: list[AlbedoKingCoronation],
    updated_at: str | None,
) -> list[AlbedoKingTenure]:
    coronations_by_version = {c.king_version: c for c in king_history}
    sorted_coronations = sorted(king_history, key=lambda c: c.king_version)
    version_to_coronation_time = {c.king_version: c.finished_at for c in sorted_coronations}

    # When version K is dethroned as active king: next coronation that defeated K.
    dethroned_at: dict[int, str] = {}
    for cor in sorted_coronations:
        if cor.defeated_king_version is not None:
            dethroned_at[cor.defeated_king_version] = cor.finished_at

    # Slot exit: 5 newer coronations push the oldest slot out.
    slot_exit_at: dict[int, str] = {}
    versions_sorted = [c.king_version for c in sorted_coronations]
    for idx, version in enumerate(versions_sorted):
        exit_idx = idx + REIGN_CHAIN_SLOTS
        if exit_idx < len(versions_sorted):
            exit_version = versions_sorted[exit_idx]
            slot_exit_at[version] = version_to_coronation_time[exit_version]

    reign_by_version = {m.king_version: m for m in reign_members}
    hotkey_slots_in_reign: dict[str, int] = defaultdict(int)
    for member in reign_members:
        hotkey_slots_in_reign[member.hotkey] += 1

    now = updated_at or datetime.now(timezone.utc).isoformat()
    current_king_version = reign_members[0].king_version if reign_members else None
    target_versions = [m.king_version for m in reign_members]

    tenures: list[AlbedoKingTenure] = []
    for rank, version in enumerate(target_versions, start=1):
        reign_member = reign_by_version.get(version)
        coronation = coronations_by_version.get(version)
        if not reign_member and not coronation:
            continue

        model_uri = reign_member.model_uri if reign_member else coronation.model_uri
        model_name = reign_member.model_name if reign_member else coronation.model_name
        namespace = reign_member.namespace if reign_member else coronation.namespace
        hotkey = reign_member.hotkey if reign_member else coronation.hotkey
        uid = reign_member.uid if reign_member else coronation.uid

        coronation_at = coronation.finished_at if coronation else None
        active_until = dethroned_at.get(version)
        if version == current_king_version:
            active_until = None
        slot_until = slot_exit_at.get(version)
        if version in reign_by_version and not slot_until:
            slot_until = None

        active_end = active_until or (now if version == current_king_version else dethroned_at.get(version) or now)
        slot_end = slot_until or (now if version in reign_by_version else slot_exit_at.get(version) or now)

        defenses = 0
        attacks = 0
        if coronation_at:
            for run in eval_runs:
                king = run.get("king") or {}
                if king.get("king_version") != version:
                    continue
                finished = run.get("finished_at") or ""
                if finished < coronation_at:
                    continue
                if active_until and finished > active_until:
                    continue
                attacks += 1
                if not run.get("challenger_won"):
                    defenses += 1

        tenures.append(
            AlbedoKingTenure(
                king_version=version,
                model_uri=model_uri,
                model_name=model_name,
                namespace=namespace,
                hotkey=hotkey,
                uid=uid,
                reign_rank=rank,
                weight_bps=reign_member.weight_bps if reign_member else 0,
                weight_pct=round((reign_member.weight_bps if reign_member else 0) / 100.0, 1),
                reign_slots=hotkey_slots_in_reign.get(hotkey, 1),
                is_current_king=version == current_king_version,
                in_reign_chain=version in reign_by_version,
                coronation_at=coronation_at,
                active_until=active_until,
                slot_until=slot_until,
                active_tenure_hours=_hours_between(coronation_at, active_end if active_until else now),
                slot_tenure_hours=_hours_between(
                    coronation_at,
                    slot_end if slot_until else now if version in reign_by_version else slot_end,
                ),
                defenses=defenses,
                attacks_faced=attacks,
                defense_pct=round(defenses / attacks * 100, 1) if attacks else None,
                coronation_margin=coronation.win_margin if coronation else None,
                defeated_king_version=coronation.defeated_king_version if coronation else None,
            )
        )

    return tenures


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
    updated_at = dashboard.get("updated_at")

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

    judge_aggregates, judge_details, judge_consensus = _build_judge_details(eval_runs, judge_models)
    reign_slot_holders = _build_reign_slot_holders(reign_members)
    king_tenures = _build_king_tenures(eval_runs, reign_members, king_history, updated_at)

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
        updated_at=updated_at,
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
        king_tenures=king_tenures,
        reign_slot_holders=reign_slot_holders,
        recent_duels=recent_duels,
        challenger_by_namespace=_sorted_rows(ns_stats, lambda k, _s: k, min_duels=2, include_coronations=True)[:20],
        challenger_by_hotkey=_sorted_rows(
            hk_stats,
            lambda k, s: f"uid {s.get('uid')} · {k[:8]}…" if len(k) > 12 else f"uid {s.get('uid')} · {k}",
            min_duels=2,
            include_coronations=True,
        )[:20],
        king_defense_by_model=_sorted_rows(
            king_stats,
            lambda k, _s: parse_model_uri(k)[1] or k,
            min_duels=3,
        )[:15],
        judge_aggregates=judge_aggregates,
        judge_details=judge_details,
        judge_consensus=judge_consensus,
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
