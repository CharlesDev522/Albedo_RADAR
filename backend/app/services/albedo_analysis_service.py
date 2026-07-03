"""Compute cross-dimensional duel analytics from Albedo dashboard JSON."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.rewards.crown_reward_math import (
    DEFAULT_KING_WEIGHT_BPS,
    estimate_crown_alpha,
    fetch_crown_reward_basis,
    ongoing_daily_alpha,
)
from app.schemas.albedo_analysis import (
    AlbedoAnalysisOverview,
    AlbedoCrownEvent,
    AlbedoCrownLeaderboardRow,
    AlbedoCurrentEval,
    AlbedoDuelJudgeVote,
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
    AlbedoRepoColdkeyLink,
    AlbedoRepoCrownAnalysis,
    AlbedoRewardBasis,
    AlbedoTimelinePoint,
    AlbedoWinRateRow,
)
from app.services.albedo_miner_lookup import MinerLookup

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


def _build_judge_vote_rows(run: dict[str, Any]) -> list[AlbedoDuelJudgeVote]:
    challenger_won = bool(run.get("challenger_won"))
    breakdown = run.get("score_breakdown") or {}
    rows: list[AlbedoDuelJudgeVote] = []
    for judge, score in (breakdown.get("by_judge") or {}).items():
        s = float(score)
        pick_ch = s > 0.5
        rows.append(
            AlbedoDuelJudgeVote(
                judge=str(judge),
                short_name=judge_short_name(str(judge)),
                challenger_score=round(s, 4),
                king_score=round(1.0 - s, 4),
                pick_challenger=pick_ch,
                agrees_with_verdict=pick_ch == challenger_won,
                margin_from_neutral=round(s - 0.5, 4),
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


def _solo_dissenter(votes: dict[str, bool]) -> str | None:
    if len(votes) != 3:
        return None
    ch_votes = [j for j, v in votes.items() if v]
    k_votes = [j for j, v in votes.items() if not v]
    if len(ch_votes) == 1:
        return ch_votes[0]
    if len(k_votes) == 1:
        return k_votes[0]
    return None


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
            "split_agree": 0,
            "split_total": 0,
            "solo_dissent": 0,
            "solo_dissent_wins": 0,
            "extreme": 0,
        }
    )
    consensus_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"duels": 0, "ch_wins": 0, "k_wins": 0})

    for run in eval_runs:
        votes = _judge_votes(run)
        pattern = _consensus_pattern(votes)
        consensus_counts[pattern]["duels"] += 1
        challenger_won = bool(run.get("challenger_won"))
        if challenger_won:
            consensus_counts[pattern]["ch_wins"] += 1
        else:
            consensus_counts[pattern]["k_wins"] += 1

        breakdown = run.get("score_breakdown") or {}
        by_judge = breakdown.get("by_judge") or {}
        is_split = pattern in ("split_2_1_challenger", "split_1_2_king")
        dissenter = _solo_dissenter(votes)

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
            if s >= 0.6 or s <= 0.4:
                per_judge[judge]["extreme"] += 1
            if challenger_won:
                per_judge[judge]["when_ch_wins"].append(s)
            else:
                per_judge[judge]["when_k_wins"].append(s)
            if is_split:
                per_judge[judge]["split_total"] += 1
                if picks_ch == challenger_won:
                    per_judge[judge]["split_agree"] += 1
            if dissenter == judge:
                per_judge[judge]["solo_dissent"] += 1
                dissenter_pick = votes[judge]
                if dissenter_pick == challenger_won:
                    per_judge[judge]["solo_dissent_wins"] += 1

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
                score_std=round(pstdev(stats["scores"]), 4) if len(stats["scores"]) > 1 else 0.0,
                pick_challenger_pct=round(stats["pick_challenger"] / duels * 100, 1),
                pick_king_pct=round((duels - stats["pick_challenger"]) / duels * 100, 1),
                agree_verdict_pct=round(stats["agree"] / duels * 100, 1),
                overturn_duels=stats["overturn"],
                split_majority_align_pct=round(stats["split_agree"] / stats["split_total"] * 100, 1)
                if stats["split_total"]
                else None,
                solo_dissent_win_pct=round(stats["solo_dissent_wins"] / stats["solo_dissent"] * 100, 1)
                if stats["solo_dissent"]
                else None,
                extreme_call_pct=round(stats["extreme"] / duels * 100, 1),
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
        for pattern, stats in sorted(consensus_counts.items(), key=lambda x: -x[1]["duels"])
        if stats["duels"] > 0 and pattern != "unknown"
    ]
    return aggregates, details, consensus


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
) -> list[AlbedoKingTenure]:
    coronations_by_version = {c.king_version: c for c in king_history}
    sorted_coronations = sorted(king_history, key=lambda c: c.king_version)
    version_to_coronation_time = {c.king_version: c.finished_at for c in sorted_coronations}

    dethroned_at: dict[int, str] = {}
    for cor in sorted_coronations:
        if cor.defeated_king_version is not None:
            dethroned_at[cor.defeated_king_version] = cor.finished_at

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


def _alpha_to_tao(alpha: float, alpha_price_tao: float | None) -> float | None:
    if alpha <= 0 or alpha_price_tao is None or alpha_price_tao <= 0:
        return None
    return alpha * alpha_price_tao


def _build_repo_crown_analysis(
    king_history: list[AlbedoKingCoronation],
    reign_members: list[AlbedoReignMember],
    updated_at: str | None,
    repo_duel_stats: dict[str, dict[str, Any]] | None = None,
    reward_basis: AlbedoRewardBasis | None = None,
) -> tuple[AlbedoRepoCrownAnalysis, list[AlbedoCrownLeaderboardRow]]:
    """Aggregate crown reward time by repo with repo↔coldkey relations."""
    sorted_coronations = sorted(king_history, key=lambda c: c.king_version)
    version_to_time = {c.king_version: c.finished_at for c in sorted_coronations}
    dethroned_at: dict[int, str] = {}
    for cor in sorted_coronations:
        if cor.defeated_king_version is not None:
            dethroned_at[cor.defeated_king_version] = cor.finished_at
    slot_exit_at: dict[int, str] = {}
    versions_sorted = [c.king_version for c in sorted_coronations]
    for idx, version in enumerate(versions_sorted):
        exit_idx = idx + REIGN_CHAIN_SLOTS
        if exit_idx < len(versions_sorted):
            slot_exit_at[version] = version_to_time[versions_sorted[exit_idx]]

    reign_versions = {m.king_version for m in reign_members}
    reign_weight = {m.king_version: m.weight_bps for m in reign_members}
    reign_by_repo = defaultdict(set)
    reign_by_link: set[tuple[str, str]] = set()
    for member in reign_members:
        if member.repo:
            reign_by_repo[member.repo].add(member.king_version)
        if member.repo and member.coldkey:
            reign_by_link.add((member.repo, member.coldkey))

    now = updated_at or datetime.now(timezone.utc).isoformat()
    current_king_version = reign_members[0].king_version if reign_members else None
    duel_stats = repo_duel_stats or {}
    basis = reward_basis or AlbedoRewardBasis()
    daily_subnet_alpha = basis.daily_subnet_alpha
    alpha_price = basis.alpha_price_tao
    default_weight = basis.default_weight_bps or DEFAULT_KING_WEIGHT_BPS

    events: list[AlbedoCrownEvent] = []
    for cor in sorted_coronations:
        active_until = dethroned_at.get(cor.king_version)
        if cor.king_version == current_king_version:
            active_until = None
        slot_until = slot_exit_at.get(cor.king_version)
        if cor.king_version in reign_versions and not slot_until:
            slot_until = None
        active_end = active_until or (now if cor.king_version == current_king_version else dethroned_at.get(cor.king_version) or now)
        slot_end = slot_until or (now if cor.king_version in reign_versions else slot_exit_at.get(cor.king_version) or now)
        slot_hours = _hours_between(
            cor.finished_at,
            slot_end if slot_until else now if cor.king_version in reign_versions else slot_end,
        )
        weight_bps = reign_weight.get(cor.king_version, default_weight)
        est_alpha = estimate_crown_alpha(
            slot_hours,
            weight_bps=weight_bps,
            daily_subnet_alpha=daily_subnet_alpha,
        )
        est_tao = _alpha_to_tao(est_alpha, alpha_price)
        events.append(
            AlbedoCrownEvent(
                king_version=cor.king_version,
                crowned_at=cor.finished_at,
                active_until=active_until,
                slot_until=slot_until,
                active_hours=_hours_between(cor.finished_at, active_end if active_until else now),
                slot_hours=slot_hours,
                weight_bps=weight_bps,
                estimated_alpha=round(est_alpha, 4) if est_alpha > 0 else None,
                estimated_tao=round(est_tao, 6) if est_tao is not None else None,
                repo=cor.repo,
                coldkey=cor.coldkey,
                hotkey=cor.hotkey,
                uid=cor.uid,
                model_name=cor.model_name,
                is_current_king=cor.king_version == current_king_version,
            )
        )

    def _accumulate(group_type: str, key_fn) -> list[AlbedoCrownLeaderboardRow]:
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "label": "",
                "coronations": 0,
                "active_hours": 0.0,
                "slot_hours": 0.0,
                "weight_pct": 0.0,
                "reign_slots": 0,
                "coldkeys": set(),
                "hotkeys": set(),
                "uids": set(),
                "repos": set(),
                "events": [],
                "estimated_alpha": 0.0,
            }
        )
        for event in events:
            key = key_fn(event)
            if not key:
                continue
            g = grouped[key]
            g["label"] = key
            g["coronations"] += 1
            g["active_hours"] += event.active_hours or 0.0
            g["slot_hours"] += event.slot_hours or 0.0
            g["estimated_alpha"] += event.estimated_alpha or 0.0
            if event.king_version in reign_weight:
                g["weight_pct"] = max(g["weight_pct"], reign_weight[event.king_version] / 100.0)
            if event.coldkey:
                g["coldkeys"].add(event.coldkey)
            g["hotkeys"].add(event.hotkey)
            g["uids"].add(event.uid)
            if event.repo:
                g["repos"].add(event.repo)
            g["events"].append(event)

        rows: list[AlbedoCrownLeaderboardRow] = []
        for key, data in grouped.items():
            duels = duel_stats.get(key, {"duels": 0, "wins": 0})
            duel_count = int(duels.get("duels") or 0)
            challenger_wins = int(duels.get("wins") or 0)
            coldkeys = sorted(data["coldkeys"])
            repos = sorted(data["repos"])
            if group_type == "repo":
                owner_count = len(coldkeys)
                reign_slots = len(reign_by_repo.get(key, set()))
            else:
                owner_count = len(repos)
                reign_slots = 0

            total_alpha = data["estimated_alpha"]
            total_tao = _alpha_to_tao(total_alpha, alpha_price)
            ongoing = None
            if group_type == "repo" and reign_slots > 0:
                slot_weight = reign_weight.get(
                    next((e.king_version for e in data["events"] if e.is_current_king), 0),
                    default_weight,
                )
                ongoing = ongoing_daily_alpha(weight_bps=slot_weight, daily_subnet_alpha=daily_subnet_alpha)
            elif group_type == "coldkey":
                reign_events = [e for e in data["events"] if e.king_version in reign_versions]
                if reign_events:
                    ongoing = sum(
                        ongoing_daily_alpha(
                            weight_bps=reign_weight.get(e.king_version, default_weight),
                            daily_subnet_alpha=daily_subnet_alpha,
                        )
                        for e in reign_events
                    )

            rows.append(
                AlbedoCrownLeaderboardRow(
                    key=key,
                    label=data["label"],
                    group_type=group_type,
                    coronations=data["coronations"],
                    total_active_hours=round(data["active_hours"], 1),
                    total_slot_hours=round(data["slot_hours"], 1),
                    current_weight_pct=round(data["weight_pct"], 1),
                    reign_slots=reign_slots,
                    owner_count=owner_count,
                    multi_owner=owner_count > 1 if group_type == "repo" else owner_count > 1,
                    coldkeys=coldkeys,
                    hotkeys=sorted(data["hotkeys"]),
                    uids=sorted(data["uids"]),
                    duel_count=duel_count if group_type == "repo" else 0,
                    challenger_wins=challenger_wins if group_type == "repo" else 0,
                    challenger_win_pct=(
                        round(challenger_wins / duel_count * 100, 1) if duel_count and group_type == "repo" else None
                    ),
                    total_estimated_alpha=round(total_alpha, 4) if total_alpha > 0 else None,
                    total_estimated_tao=round(total_tao, 6) if total_tao is not None else None,
                    ongoing_daily_alpha=round(ongoing, 4) if ongoing and ongoing > 0 else None,
                    crown_events=sorted(data["events"], key=lambda e: e.king_version, reverse=True),
                )
            )
        rows.sort(key=lambda r: (-r.coronations, -r.total_slot_hours, -r.total_active_hours))
        return rows

    crowns_by_repo = _accumulate("repo", lambda e: e.repo)
    crowns_by_coldkey = _accumulate("coldkey", lambda e: e.coldkey)

    link_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "coronations": 0,
            "active_hours": 0.0,
            "slot_hours": 0.0,
            "estimated_alpha": 0.0,
            "hotkeys": set(),
            "uids": set(),
            "last_crowned_at": None,
            "in_reign": False,
            "reign_weight_bps": 0,
        }
    )
    for event in events:
        if not event.repo or not event.coldkey:
            continue
        link = link_stats[(event.repo, event.coldkey)]
        link["coronations"] += 1
        link["active_hours"] += event.active_hours or 0.0
        link["slot_hours"] += event.slot_hours or 0.0
        link["estimated_alpha"] += event.estimated_alpha or 0.0
        link["hotkeys"].add(event.hotkey)
        link["uids"].add(event.uid)
        if event.king_version in reign_versions:
            link["in_reign"] = True
            link["reign_weight_bps"] = reign_weight.get(event.king_version, default_weight)
        prev = link["last_crowned_at"]
        if prev is None or event.crowned_at > prev:
            link["last_crowned_at"] = event.crowned_at

    repo_coldkey_links: list[AlbedoRepoColdkeyLink] = []
    for (repo, coldkey), stats in link_stats.items():
        hotkeys = sorted(stats["hotkeys"])
        uids = sorted(stats["uids"])
        total_alpha = stats["estimated_alpha"]
        total_tao = _alpha_to_tao(total_alpha, alpha_price)
        link_ongoing = None
        if stats["in_reign"]:
            link_ongoing = ongoing_daily_alpha(
                weight_bps=stats["reign_weight_bps"] or default_weight,
                daily_subnet_alpha=daily_subnet_alpha,
            )
        repo_coldkey_links.append(
            AlbedoRepoColdkeyLink(
                repo=repo,
                coldkey=coldkey,
                hotkey=hotkeys[-1] if hotkeys else None,
                uid=uids[-1] if uids else None,
                coronations=stats["coronations"],
                total_slot_hours=round(stats["slot_hours"], 1),
                total_active_hours=round(stats["active_hours"], 1),
                total_estimated_alpha=round(total_alpha, 4) if total_alpha > 0 else None,
                total_estimated_tao=round(total_tao, 6) if total_tao is not None else None,
                ongoing_daily_alpha=round(link_ongoing, 4) if link_ongoing and link_ongoing > 0 else None,
                in_reign=(repo, coldkey) in reign_by_link,
                last_crowned_at=stats["last_crowned_at"],
            )
        )
    repo_coldkey_links.sort(
        key=lambda row: (-row.coronations, -row.total_slot_hours, row.repo, row.coldkey)
    )

    multi_owner_repos = sorted(
        row.key for row in crowns_by_repo if row.multi_owner
    )
    unique_coldkeys = {link.coldkey for link in repo_coldkey_links}
    grand_alpha = sum(row.total_estimated_alpha or 0.0 for row in crowns_by_repo)
    grand_tao = _alpha_to_tao(grand_alpha, alpha_price)

    analysis = AlbedoRepoCrownAnalysis(
        reward_basis=basis,
        crowns_by_repo=crowns_by_repo,
        crowns_by_coldkey=crowns_by_coldkey,
        repo_coldkey_links=repo_coldkey_links,
        multi_owner_repos=multi_owner_repos,
        total_repos_crowned=len(crowns_by_repo),
        total_unique_coldkeys=len(unique_coldkeys),
        grand_total_estimated_alpha=round(grand_alpha, 4) if grand_alpha > 0 else None,
        grand_total_estimated_tao=round(grand_tao, 6) if grand_tao is not None else None,
    )
    return analysis, crowns_by_coldkey


def build_analysis_overview(
    dashboard: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    subnet: int = 97,
    source_url: str,
    miner_lookup: MinerLookup | None = None,
    reward_basis: AlbedoRewardBasis | None = None,
    archived_king_history: list[AlbedoKingCoronation] | None = None,
    archived_crown_count: int = 0,
) -> AlbedoAnalysisOverview:
    eval_runs: list[dict[str, Any]] = list(dashboard.get("eval_runs") or [])
    reign_members = [
        _reign_member(m, miner_lookup) for m in (dashboard.get("reign") or {}).get("members") or []
    ]
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
    repo_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0})
    hk_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": [], "coronations": 0, "uid": None})
    king_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"duels": 0, "wins": 0, "margins": []})
    metric_scores: dict[str, list[float]] = defaultdict(list)
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
            for bucket, key in ((ns_stats, ns), (repo_stats, repo_key), (hk_stats, hk)):
                bucket[key]["coronations"] += 1
            from app.services.albedo_king_history import coronation_from_eval_run

            cor = coronation_from_eval_run(run, miner_lookup)
            if cor:
                king_history.append(cor)

    live_crown_count = len(king_history)
    if archived_king_history:
        from app.services.albedo_king_history import merge_king_histories

        king_history = merge_king_histories(king_history, archived_king_history)
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
    reign_slot_holders = _build_reign_slot_holders(reign_members, miner_lookup)
    king_tenures = _build_king_tenures(eval_runs, reign_members, king_history, updated_at, miner_lookup)
    repo_crown_analysis, crowns_by_coldkey = _build_repo_crown_analysis(
        king_history, reign_members, updated_at, repo_duel_stats=repo_stats, reward_basis=reward_basis
    )
    versions = sorted(c.king_version for c in king_history) if king_history else []
    repo_crown_analysis.earliest_crown_version = versions[0] if versions else None
    repo_crown_analysis.latest_crown_version = versions[-1] if versions else None
    repo_crown_analysis.archived_crown_count = archived_crown_count
    crowns_by_repo = repo_crown_analysis.crowns_by_repo

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

    recent_duels = [_duel_summary(r, miner_lookup) for r in eval_runs[:60]]

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
        reign=reign_members,
        current_king=reign_members[0] if reign_members else None,
        current_eval=_current_eval(dashboard.get("current_eval"), miner_lookup),
        queue_length=len(dashboard.get("queue") or []),
        king_history=king_history,
        king_tenures=king_tenures,
        reign_slot_holders=reign_slot_holders,
        repo_crown_analysis=repo_crown_analysis,
        crowns_by_repo=crowns_by_repo,
        crowns_by_coldkey=crowns_by_coldkey,
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
        judge_aggregates=judge_aggregates,
        judge_details=judge_details,
        judge_consensus=judge_consensus,
        metric_aggregates=metric_aggregates,
        margin_histogram=margin_histogram,
        timeline=timeline,
        pipeline=_build_pipeline(state),
        miner_lookup_coverage_pct=miner_lookup.coverage_pct if miner_lookup else None,
        note=(
            "Live duel data from Hippius Albedo dashboard JSON (eval_runs + reign chain)."
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
    try:
        reward_basis = await fetch_crown_reward_basis(subnet, settings=settings)
    except Exception:
        reward_basis = AlbedoRewardBasis()

    archived_history: list[AlbedoKingCoronation] = []
    archived_count = 0
    if db is not None:
        try:
            from app.services.albedo_crown_archive_service import (
                backfill_crowns_from_alerts,
                import_crown_seed_if_configured,
                load_archived_king_history,
                sync_crowns_from_dashboard,
            )

            await sync_crowns_from_dashboard(db, subnet, dashboard, miner_lookup=miner_lookup)
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
        reward_basis=reward_basis,
        archived_king_history=archived_history,
        archived_crown_count=archived_count,
    )
