"""Compute cross-dimensional duel analytics from Albedo dashboard JSON."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.schemas.albedo_analysis import (
    AlbedoAnalysisOverview,
    AlbedoCurrentEval,
    AlbedoDuelJudgeVote,
    AlbedoDuelSummary,
    AlbedoKingCoronation,
    AlbedoKingTenure,
    AlbedoMarginBucket,
    AlbedoPipelineStage,
    AlbedoReignMember,
    AlbedoReignSlotHolder,
    AlbedoScoreTimelinePoint,
    AlbedoTimelinePoint,
    AlbedoWinRateRow,
)
from app.services.albedo_miner_lookup import (
    MinerLookup,
    resolve_committed,
)

logger = logging.getLogger(__name__)

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
    if not model_uri:
        return "", "", ""
    base = model_uri.split("@", 1)[0]
    if "/" in base:
        namespace, model_name = base.split("/", 1)
        return namespace, model_name, model_uri
    return "", base, model_uri


def judge_short_name(judge: str) -> str:
    name = judge.rsplit("/", 1)[-1] if "/" in judge else judge
    if name.lower().startswith("glm"):
        return "glm"
    return name


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


def _compute_slot_tenure(
    *,
    coronation_at: str | None,
    king_version: int,
    reign_versions: set[int],
    slot_exit_at: dict[int, str],
    now: str,
    voided_window: tuple[str, str] | None,
) -> tuple[str | None, float | None, float | None]:
    """
    Slot reward tenure for a king version.

    Kings in the live Hippius reign chain keep earning through now, even if the
    5-slot rollover would have ended them earlier, and including the voided-king
    window when illegitimate coronations temporarily displaced them.
    """
    if not coronation_at:
        return None, None, None

    rollover_exit = slot_exit_at.get(king_version)
    if king_version in reign_versions:
        slot_until = None
        slot_hours = _hours_between(coronation_at, now)
        bridge_hours: float | None = None
        if rollover_exit:
            rollover_hours = _hours_between(coronation_at, rollover_exit) or 0.0
            if slot_hours is not None and slot_hours > rollover_hours:
                bridge_hours = round(slot_hours - rollover_hours, 1)
        if voided_window and bridge_hours is not None:
            window_hours = _hours_between(voided_window[0], voided_window[1]) or 0.0
            bridge_hours = round(min(bridge_hours, window_hours), 1)
            if bridge_hours <= 0:
                bridge_hours = None
        return slot_until, slot_hours, bridge_hours

    slot_until = rollover_exit
    slot_end = rollover_exit or now
    return slot_until, _hours_between(coronation_at, slot_end), None


def _short_model_label(namespace: str, model_name: str, *, max_len: int = 22) -> str:
    label = f"{namespace}/{model_name}" if namespace else model_name
    if len(label) <= max_len:
        return label
    return label[: max_len - 1] + "…"


def _build_score_timeline(
    eval_runs: list[dict[str, Any]],
    *,
    miner_lookup: MinerLookup | None,
) -> list[AlbedoScoreTimelinePoint]:
    """All finished duels from dashboard eval_runs, oldest-first for charting."""
    points: list[AlbedoScoreTimelinePoint] = []
    for run in eval_runs:
        if not run.get("finished_at"):
            continue

        summary = _duel_summary(run, miner_lookup)
        points.append(
            AlbedoScoreTimelinePoint(
                eval_run_id=summary.eval_run_id,
                finished_at=summary.finished_at,
                score_challenger=summary.score_challenger,
                score_king=summary.score_king,
                win_margin=summary.win_margin,
                challenger_won=summary.challenger_won,
                coronated=summary.coronated,
                challenger_uid=summary.uid,
                king_uid=summary.king_uid,
                challenger_label=_short_model_label(summary.namespace, summary.model_name),
                king_label=_short_model_label(
                    summary.king_namespace or "",
                    summary.king_model_name or "king",
                ),
            )
        )

    points.sort(key=lambda p: p.finished_at)
    return points


def _resolve_repo(
    lookup: MinerLookup | None,
    *,
    hotkey: str,
    uid: int | None,
    namespace: str,
    model_name: str,
    model_uri: str | None = None,
) -> tuple[str | None, str | None]:
    ident = (
        lookup.resolve(
            hotkey=hotkey or None,
            uid=uid,
            model_uri=model_uri,
            namespace=namespace,
            model_name=model_name,
        )
        if lookup
        else None
    )
    repo = ident.repo if ident and ident.repo else (f"{namespace}/{model_name}" if namespace else None)
    coldkey = ident.coldkey if ident else None
    return repo, coldkey


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


def _judge_score_pairs(run: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Per-judge challenger and king rubric win-rates from dashboard breakdown."""
    breakdown = run.get("score_breakdown") or {}
    by_ch = breakdown.get("by_judge") or {}
    by_k = breakdown.get("by_judge_king") or {}
    pairs: dict[str, tuple[float, float]] = {}
    for judge, ch_raw in by_ch.items():
        ch = float(ch_raw)
        if judge in by_k:
            k = float(by_k[judge])
        else:
            k = 1.0 - ch
        pairs[str(judge)] = (ch, k)
    return pairs


def _pick_challenger(ch: float, k: float) -> bool:
    if ch != k:
        return ch > k
    return ch > 0.5


def _judge_votes(run: dict[str, Any]) -> dict[str, bool]:
    return {
        judge: _pick_challenger(ch, k)
        for judge, (ch, k) in _judge_score_pairs(run).items()
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


def _build_judge_vote_rows(run: dict[str, Any]) -> list[AlbedoDuelJudgeVote]:
    challenger_won = bool(run.get("challenger_won"))
    rows: list[AlbedoDuelJudgeVote] = []
    for judge, (ch, k) in _judge_score_pairs(run).items():
        pick_ch = _pick_challenger(ch, k)
        rows.append(
            AlbedoDuelJudgeVote(
                judge=judge,
                short_name=judge_short_name(judge),
                challenger_score=round(ch, 4),
                king_score=round(k, 4),
                pick_challenger=pick_ch,
                agrees_with_verdict=pick_ch == challenger_won,
                margin_from_neutral=round(ch - k, 4),
            )
        )
    return rows


def _duel_summary(
    run: dict[str, Any],
    lookup: MinerLookup | None = None,
) -> AlbedoDuelSummary:
    ns, name, uri = parse_model_uri(run.get("model_uri"))
    king = run.get("king") or {}
    k_ns, k_name, k_uri = parse_model_uri(king.get("model_uri"))
    uid = int(run.get("uid") or 0)
    king_uid = int(king["uid"]) if king.get("uid") is not None else None
    repo, coldkey = _resolve_repo(
        lookup,
        hotkey=run.get("hotkey", ""),
        uid=uid,
        namespace=ns,
        model_name=name,
        model_uri=run.get("model_uri"),
    )
    king_repo, king_coldkey = _resolve_repo(
        lookup,
        hotkey=king.get("hotkey", ""),
        uid=king_uid,
        namespace=k_ns,
        model_name=k_name,
        model_uri=king.get("model_uri"),
    )
    judge_votes = _build_judge_vote_rows(run)
    scores = [v.challenger_score for v in judge_votes]
    judge_spread = round(max(scores) - min(scores), 4) if len(scores) >= 2 else None
    votes = _judge_votes(run)
    pattern = _consensus_pattern(votes)
    breakdown = run.get("score_breakdown") or {}
    req_raw = run.get("required_win_margin")
    req_margin = float(req_raw) if req_raw is not None else None
    win_margin = float(run.get("win_margin") or 0)
    return AlbedoDuelSummary(
        eval_run_id=run.get("eval_run_id", ""),
        finished_at=run.get("finished_at", ""),
        challenger_won=bool(run.get("challenger_won")),
        coronated=bool(run.get("coronated")),
        king_version=run.get("king_version"),
        score_challenger=float(run.get("score_challenger") or 0),
        score_king=float(run.get("score_king") or 0),
        win_margin=win_margin,
        model_uri=uri,
        model_name=name,
        namespace=ns,
        repo=repo,
        coldkey=coldkey,
        hotkey=run.get("hotkey", ""),
        uid=uid,
        king_model_uri=k_uri or None,
        king_model_name=k_name or None,
        king_namespace=k_ns or None,
        king_repo=king_repo,
        king_coldkey=king_coldkey,
        king_uid=king_uid,
        king_hotkey=king.get("hotkey"),
        king_version_defended=int(king["king_version"]) if king.get("king_version") is not None else None,
        valid_turns=run.get("valid_turns"),
        total_turns=run.get("total_turns"),
        scoring_mode=run.get("scoring_mode"),
        required_win_margin=req_margin,
        margin_cleared=win_margin >= req_margin if req_margin is not None else None,
        scored_sample_count=run.get("scored_sample_count"),
        judge_errors=run.get("judge_errors"),
        metric_breakdown={
            str(metric): float(score) for metric, score in (breakdown.get("by_metric") or {}).items()
        },
        category_breakdown={
            str(cat): float(score) for cat, score in (breakdown.get("by_category") or {}).items()
        },
        artifacts={str(k): str(v) for k, v in (run.get("artifacts") or {}).items()},
        judge_scores={v.judge: v.challenger_score for v in judge_votes},
        judge_votes=judge_votes,
        judge_spread=judge_spread,
        panel_pattern=pattern,
        unanimous_panel=pattern in ("unanimous_challenger", "unanimous_king"),
    )


def _reign_member(member: dict[str, Any], lookup: MinerLookup | None) -> AlbedoReignMember:
    ns, name, uri = parse_model_uri(member.get("model_uri"))
    uid = int(member.get("uid") or 0)
    repo, coldkey = _resolve_repo(
        lookup,
        hotkey=member.get("hotkey", ""),
        uid=uid,
        namespace=ns,
        model_name=name,
        model_uri=member.get("model_uri"),
    )
    return AlbedoReignMember(
        king_version=int(member.get("king_version") or 0),
        model_uri=uri,
        model_name=name,
        namespace=ns,
        hotkey=member.get("hotkey", ""),
        uid=uid,
        weight_bps=int(member.get("weight_bps") or 0),
        repo=repo,
        coldkey=coldkey,
        score_challenger=member.get("score_challenger"),
        score_king=member.get("score_king"),
        eval_run_id=member.get("eval_run_id"),
    )


def _current_eval(raw: dict[str, Any] | None, lookup: MinerLookup | None) -> AlbedoCurrentEval | None:
    if not raw:
        return None
    ns, name, uri = parse_model_uri(raw.get("model_uri"))
    uid = int(raw.get("uid") or 0)
    repo, coldkey = _resolve_repo(
        lookup,
        hotkey=raw.get("hotkey", ""),
        uid=uid,
        namespace=ns,
        model_name=name,
        model_uri=raw.get("model_uri"),
    )
    return AlbedoCurrentEval(
        eval_run_id=raw.get("eval_run_id", ""),
        state=raw.get("state", ""),
        model_uri=uri,
        model_name=name,
        namespace=ns,
        hotkey=raw.get("hotkey", ""),
        uid=uid,
        repo=repo,
        coldkey=coldkey,
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
    stages = state.get("stages") or {}
    counts = state.get("counts") or {}
    result: list[AlbedoPipelineStage] = []
    for stage_name in ("hippius_validate", "pre_eval", "eval"):
        bucket = stages.get(stage_name) or {}
        count_row = counts.get(stage_name) or {}
        running = int(count_row.get("running") or len(bucket.get("running") or []))
        queued = int(count_row.get("queued") or len(bucket.get("queued") or []))
        label = stage_name.replace("_", " ").title()
        result.append(
            AlbedoPipelineStage(
                stage=stage_name,
                status=f"{running} running, {queued} queued",
                detail=label,
            )
        )
    return result


def _build_reign_slot_holders(
    reign_members: list[AlbedoReignMember],
    lookup: MinerLookup | None,
) -> list[AlbedoReignSlotHolder]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "slots": 0,
            "weight_bps": 0,
            "versions": [],
            "uid": 0,
            "hotkey": "",
            "label": "",
            "repo": None,
            "coldkey": None,
        }
    )
    for member in reign_members:
        key = member.hotkey or member.model_uri
        g = grouped[key]
        g["slots"] += 1
        g["weight_bps"] += member.weight_bps
        g["versions"].append(member.king_version)
        g["uid"] = member.uid
        g["hotkey"] = member.hotkey
        g["label"] = member.repo or f"{member.namespace}/{member.model_name}"
        g["repo"] = member.repo
        g["coldkey"] = member.coldkey
    rows = [
        AlbedoReignSlotHolder(
            key=key,
            label=data["label"],
            repo=data["repo"],
            coldkey=data["coldkey"],
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
    lookup: MinerLookup | None,
    *,
    voided: set[int] | None = None,
    voided_window: tuple[str, str] | None = None,
) -> list[AlbedoKingTenure]:
    from app.services.albedo_king_history import legitimate_dethroned_at, slot_exit_schedule

    voided = voided or set()
    coronations_by_version = {c.king_version: c for c in king_history}
    dethroned_at = legitimate_dethroned_at(
        king_history,
        eval_runs=eval_runs,
        voided=voided,
        reign_versions={m.king_version for m in reign_members},
        current_king_version=reign_members[0].king_version if reign_members else None,
    )
    slot_exit_at = slot_exit_schedule(king_history)

    reign_by_version = {m.king_version: m for m in reign_members}
    reign_versions = set(reign_by_version)
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
        repo, coldkey = _resolve_repo(
            lookup,
            hotkey=hotkey,
            uid=uid,
            namespace=namespace,
            model_name=model_name,
            model_uri=model_uri,
        )
        if coronation:
            repo = coronation.repo or repo
            coldkey = coronation.coldkey or coldkey

        coronation_at = coronation.finished_at if coronation else None
        active_until = dethroned_at.get(version)
        if version == current_king_version:
            active_until = None

        slot_until, slot_tenure_hours, voided_bridge_hours = _compute_slot_tenure(
            coronation_at=coronation_at,
            king_version=version,
            reign_versions=reign_versions,
            slot_exit_at=slot_exit_at,
            now=now,
            voided_window=voided_window,
        )
        active_end = active_until or (now if version == current_king_version else dethroned_at.get(version) or now)

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
                repo=repo,
                coldkey=coldkey,
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
                slot_tenure_hours=slot_tenure_hours,
                voided_bridge_hours=voided_bridge_hours,
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
    miner_lookup: MinerLookup | None = None,
    archived_king_history: list[AlbedoKingCoronation] | None = None,
) -> AlbedoAnalysisOverview:
    from app.services.albedo_king_history import (
        filter_voided_coronations,
        merge_king_histories,
        voided_king_versions,
        voided_reign_window,
    )

    voided = voided_king_versions(dashboard)
    voided_window = voided_reign_window(dashboard, voided)
    eval_runs: list[dict[str, Any]] = list(dashboard.get("eval_runs") or [])
    reign_members = [
        _reign_member(m, miner_lookup) for m in (dashboard.get("reign") or {}).get("members") or []
    ]
    judge_models = list((dashboard.get("chain") or {}).get("judge_models") or [])
    updated_at = dashboard.get("updated_at")

    challenger_wins = sum(1 for r in eval_runs if r.get("challenger_won"))
    king_wins = len(eval_runs) - challenger_wins
    coronations = sum(
        1
        for r in eval_runs
        if r.get("coronated") and int(r.get("king_version") or -1) not in voided
    )
    total = len(eval_runs)

    margins = [float(r.get("win_margin") or 0) for r in eval_runs]
    ch_scores = [float(r.get("score_challenger") or 0) for r in eval_runs]
    k_scores = [float(r.get("score_king") or 0) for r in eval_runs]
    binary_scoring_duels = sum(1 for r in eval_runs if r.get("scoring_mode") == "binary")
    required_win_margin = next(
        (float(r["required_win_margin"]) for r in eval_runs if r.get("required_win_margin") is not None),
        None,
    )

    ns_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0})
    repo_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0})
    hk_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0, "uid": None})
    king_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": []})
    margin_counts: dict[str, int] = defaultdict(int)
    timeline_raw: dict[str, dict[str, int]] = defaultdict(lambda: {"duels": 0, "ch_wins": 0, "k_wins": 0, "coronations": 0})

    king_history: list[AlbedoKingCoronation] = []

    for run in eval_runs:
        summary = _duel_summary(run, miner_lookup)
        ns = summary.namespace or "unknown"
        hk = summary.hotkey or "unknown"
        repo_key = summary.repo or f"{summary.namespace}/{summary.model_name}"
        won = summary.challenger_won
        margin = summary.win_margin

        for bucket, key in ((ns_stats, ns), (repo_stats, repo_key), (hk_stats, hk)):
            bucket[key]["duels"] += 1
            if won:
                bucket[key]["wins"] += 1
            bucket[key]["margins"].append(margin)
        hk_stats[hk]["uid"] = summary.uid

        king_key = summary.king_model_uri or summary.king_model_name or "unknown"
        king_stats[king_key]["duels"] += 1
        if not won:
            king_stats[king_key]["wins"] += 1
        king_stats[king_key]["margins"].append(-margin)

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
            for bucket, key in ((ns_stats, ns), (repo_stats, repo_key), (hk_stats, hk)):
                bucket[key]["coronations"] += 1
            from app.services.albedo_king_history import coronation_from_eval_run

            cor = coronation_from_eval_run(run, miner_lookup)
            if cor and cor.king_version not in voided:
                king_history.append(cor)

    live_crown_count = len(king_history)
    if archived_king_history:
        king_history = merge_king_histories(king_history, archived_king_history)
    king_history = filter_voided_coronations(king_history, voided)
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

    reign_slot_holders = _build_reign_slot_holders(reign_members, miner_lookup)
    king_tenures = _build_king_tenures(
        eval_runs,
        reign_members,
        king_history,
        updated_at,
        miner_lookup,
        voided=voided,
        voided_window=voided_window,
    )
    voided_king_versions_list = sorted(voided)
    crown_history_coverage_note = ""
    if voided:
        voided_label = ", ".join(f"v{v}" for v in sorted(voided))
        bridge_note = (
            f"Excluded {len(voided)} voided king(s) rolled back by Hippius ({voided_label}). "
            "Current reign kings keep slot credit through the voided window."
        )
        if voided_window:
            bridge_hours = _hours_between(voided_window[0], voided_window[1])
            if bridge_hours:
                bridge_note += f" Voided window ≈ {bridge_hours:.0f}h."
        crown_history_coverage_note = bridge_note

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

    recent_runs = sorted(
        eval_runs,
        key=lambda r: str(r.get("finished_at") or ""),
        reverse=True,
    )
    recent_duels = [_duel_summary(r, miner_lookup) for r in recent_runs[:60]]
    score_timeline = _build_score_timeline(eval_runs, miner_lookup=miner_lookup)

    lookup_note = ""
    if miner_lookup and miner_lookup.by_hotkey:
        lookup_note = (
            f" Repo/coldkey from {len(miner_lookup.by_hotkey)} hotkeys"
            f" ({len(miner_lookup.by_model_base)} model paths, historical + active commits)."
        )

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
        required_win_margin=required_win_margin,
        binary_scoring_duels=binary_scoring_duels,
        reign=reign_members,
        current_king=reign_members[0] if reign_members else None,
        current_eval=_current_eval(dashboard.get("current_eval"), miner_lookup),
        queue_length=len(dashboard.get("queue") or []),
        king_history=king_history,
        king_tenures=king_tenures,
        reign_slot_holders=reign_slot_holders,
        voided_king_versions=voided_king_versions_list,
        crown_history_coverage_note=crown_history_coverage_note,
        recent_duels=recent_duels,
        challenger_by_namespace=_sorted_rows(ns_stats, lambda k, _s: k, min_duels=2, include_coronations=True)[:20],
        challenger_by_repo=_sorted_rows(repo_stats, lambda k, _s: k, min_duels=2, include_coronations=True)[:20],
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
        margin_histogram=margin_histogram,
        timeline=timeline,
        score_timeline=score_timeline,
        pipeline=_build_pipeline(state),
        miner_lookup_coverage_pct=miner_lookup.coverage_pct if miner_lookup else None,
        note=(
            "Live duel data from Hippius Albedo dashboard JSON (eval_runs + reign chain)."
            + (
                f" Binary rubric scoring on {binary_scoring_duels}/{total} recent duels"
                f" (win bar ≥ {required_win_margin * 100:.0f}% when set)."
                if required_win_margin is not None
                else ""
            )
            + lookup_note
        ),
    )


async def get_albedo_analysis_overview(
    subnet: int = 97,
    *,
    settings: Settings | None = None,
    miner_lookup: MinerLookup | None = None,
    db: AsyncSession | None = None,
) -> AlbedoAnalysisOverview:
    settings = settings or get_settings()
    source_url = f"{settings.albedo_dashboard_url.rstrip('/')}/data/dashboard.json"
    dashboard = await fetch_dashboard(settings=settings)
    state_payload: dict[str, Any] | None = None
    try:
        state_payload = await fetch_state(settings=settings)
    except Exception:
        state_payload = None

    archived_history: list[AlbedoKingCoronation] = []
    archived_count = 0
    if db is not None:
        try:
            from app.services.albedo_king_history import voided_king_versions
            from app.services.albedo_crown_archive_service import (
                backfill_crowns_from_alerts,
                import_crown_seed_if_configured,
                load_archived_king_history,
                purge_voided_coronations,
                sync_crowns_from_dashboard,
            )

            voided = voided_king_versions(dashboard)
            await sync_crowns_from_dashboard(db, subnet, dashboard, miner_lookup=miner_lookup)
            await purge_voided_coronations(db, subnet, voided)
            await backfill_crowns_from_alerts(db, subnet, miner_lookup=miner_lookup)
            await import_crown_seed_if_configured(
                db, subnet, settings=settings, miner_lookup=miner_lookup
            )
            await db.commit()
            archived_history = await load_archived_king_history(db, subnet, miner_lookup=miner_lookup)
            archived_count = len(archived_history)
        except Exception:
            await db.rollback()
            logger.exception("crown archive sync failed for subnet %s", subnet)

    return build_analysis_overview(
        dashboard,
        state=state_payload,
        subnet=subnet,
        source_url=source_url,
        miner_lookup=miner_lookup,
        archived_king_history=archived_history,
    )
