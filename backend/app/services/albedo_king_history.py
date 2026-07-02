"""King coronation parsing and history merge (avoids circular imports)."""

from __future__ import annotations

from typing import Any

from app.schemas.albedo_analysis import AlbedoKingCoronation
from app.services.albedo_miner_lookup import MinerLookup


def coronation_from_eval_run(
    run: dict[str, Any],
    lookup: MinerLookup | None = None,
) -> AlbedoKingCoronation | None:
    from app.services.albedo_analysis_service import (
        _duel_summary,
        _resolve_repo,
        parse_model_uri,
    )

    if not run.get("coronated"):
        return None
    summary = _duel_summary(run, lookup)
    defeated = run.get("king") or {}
    d_ns, d_name, d_uri = parse_model_uri(defeated.get("model_uri"))
    d_uid = int(defeated["uid"]) if defeated.get("uid") is not None else None
    d_repo, d_coldkey = _resolve_repo(
        lookup,
        hotkey=defeated.get("hotkey", ""),
        uid=d_uid,
        namespace=d_ns,
        model_name=d_name,
        model_uri=defeated.get("model_uri"),
    )
    return AlbedoKingCoronation(
        king_version=int(run.get("king_version") or 0),
        model_uri=summary.model_uri,
        model_name=summary.model_name,
        namespace=summary.namespace,
        repo=summary.repo,
        coldkey=summary.coldkey,
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
        defeated_repo=d_repo,
        defeated_coldkey=d_coldkey,
    )


def _coronation_score(c: AlbedoKingCoronation) -> int:
    score = 0
    if c.repo:
        score += 2
    if c.coldkey:
        score += 3
    if c.eval_run_id:
        score += 1
    if c.defeated_king_version is not None:
        score += 1
    return score


def merge_king_histories(
    live: list[AlbedoKingCoronation],
    archived: list[AlbedoKingCoronation],
) -> list[AlbedoKingCoronation]:
    by_version: dict[int, AlbedoKingCoronation] = {}
    for row in archived:
        by_version[row.king_version] = row
    for row in live:
        prev = by_version.get(row.king_version)
        if prev is None or _coronation_score(row) >= _coronation_score(prev):
            by_version[row.king_version] = row
    return sorted(by_version.values(), key=lambda c: c.king_version, reverse=True)


def crown_history_coverage_note(
    *,
    merged: list[AlbedoKingCoronation],
    live_count: int,
    archived_count: int,
) -> str:
    if not merged:
        return "No crown history yet."
    versions = sorted(c.king_version for c in merged)
    earliest, latest = versions[0], versions[-1]
    parts = [
        f"Archived {archived_count} coronations (v{earliest}–v{latest}).",
        f"Hippius dashboard currently shows {live_count} live coronations.",
    ]
    if earliest > 1:
        parts.append(
            f"Kings before v{earliest} are not in Hippius eval_runs anymore — "
            "rewards for those versions require a manual seed import."
        )
    return " ".join(parts)
