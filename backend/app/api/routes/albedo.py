"""Albedo king status, duels, HF analytics, and metagraph incentives."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.models import Miner, MinerCommitment, MinerStatus
from app.db.session import get_db
from app.integrations.albedo_client import (
    fetch_albedo_dashboard,
    fetch_albedo_state,
    king_hotkey,
    king_uid,
)
from app.integrations.albedo_normalize import (
    build_hf_analytics,
    current_king,
    hf_account,
    king_title_name,
    model_repo,
    verdict_info,
)
from app.schemas.albedo import (
    AlbedoPipelineState,
    AlbedoStatusResponse,
    DuelRun,
    FailRun,
    HfAccountStats,
    HfAnalyticsResponse,
    HfAnalyticsSummary,
    IncentiveOverviewResponse,
    MinerIncentiveEntry,
    PipelineCounts,
    ReignMember,
)

router = APIRouter(prefix="/albedo", tags=["albedo"])
settings = get_settings()

_MODEL_VERSIONS = ("v5", "v6")


def _reign_member(raw: dict, coldkey: str | None = None) -> ReignMember:
    uri = raw.get("model_uri")
    bps = raw.get("weight_bps")
    return ReignMember(
        king_version=raw.get("king_version"),
        title=king_title_name(raw.get("king_version")),
        uid=raw.get("uid"),
        hotkey=raw.get("hotkey"),
        coldkey=coldkey or raw.get("coldkey"),
        model_uri=uri,
        model_repo=model_repo(uri) or None,
        hf_account=hf_account(uri),
        weight_bps=bps,
        weight_pct=round(bps / 100, 1) if bps is not None else None,
        score_challenger=raw.get("score_challenger"),
        score_king=raw.get("score_king"),
    )


def _duel_run(raw: dict) -> DuelRun:
    uri = raw.get("model_uri")
    v = verdict_info(raw)
    defeated = raw.get("king") or {}
    return DuelRun(
        eval_run_id=raw.get("eval_run_id"),
        uid=raw.get("uid"),
        hotkey=raw.get("hotkey"),
        model_uri=uri,
        model_repo=model_repo(uri) or None,
        hf_account=hf_account(uri),
        king_version=raw.get("king_version"),
        challenger_won=v["won"],
        coronated=v["coronated"],
        badge=v["badge"],
        score_challenger=raw.get("score_challenger"),
        score_king=raw.get("score_king"),
        win_margin=raw.get("win_margin"),
        finished_at=raw.get("finished_at"),
        defeated_king_hf=hf_account(defeated.get("model_uri")),
    )


def _fail_run(raw: dict) -> FailRun:
    uri = raw.get("model_uri")
    return FailRun(
        eval_run_id=raw.get("eval_run_id") or raw.get("eval_id"),
        uid=raw.get("uid"),
        hotkey=raw.get("hotkey"),
        model_uri=uri,
        hf_account=hf_account(uri),
        fault_code=raw.get("fault_code") or raw.get("code") or raw.get("error_code"),
        fault_class=raw.get("fault_class"),
        finished_at=raw.get("finished_at") or raw.get("completed_at"),
    )


def _pipeline_state(raw: dict | None) -> AlbedoPipelineState | None:
    if not raw:
        return None
    counts = raw.get("counts") or {}

    def stage(name: str) -> PipelineCounts:
        c = counts.get(name) or {}
        return PipelineCounts(running=int(c.get("running") or 0), queued=int(c.get("queued") or 0))

    validate = stage("hippius_validate")
    pre_eval = stage("pre_eval")
    eval_stage = stage("eval")
    total = sum(s.running + s.queued for s in (validate, pre_eval, eval_stage))
    return AlbedoPipelineState(
        updated_at=raw.get("updated_at"),
        validate=validate,
        pre_eval=pre_eval,
        eval=eval_stage,
        total_in_flight=total,
    )


async def _coldkeys_for_hotkeys(db: AsyncSession, subnet: int, hotkeys: set[str]) -> dict[str, str]:
    if not hotkeys:
        return {}
    result = await db.execute(
        select(Miner.hotkey, Miner.coldkey).where(
            Miner.subnet == subnet,
            Miner.hotkey.in_(tuple(hotkeys)),
        )
    )
    return {str(hk): str(ck) for hk, ck in result.all() if hk and ck}


@router.get("/status", response_model=AlbedoStatusResponse)
async def albedo_status(
    subnet: int = Query(default=97, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AlbedoStatusResponse:
    """Current king, reign chain, duels (not fails), pipeline — v2 Hippius API."""
    dashboard = await fetch_albedo_dashboard()
    state_raw = await fetch_albedo_state()
    if not dashboard:
        return AlbedoStatusResponse(
            subnet=subnet,
            source_url=settings.albedo_dashboard_url,
        )

    hotkeys = set()
    for m in dashboard.get("reign", {}).get("members") or []:
        if m.get("hotkey"):
            hotkeys.add(str(m["hotkey"]))
    for r in (dashboard.get("eval_runs") or [])[:40]:
        if r.get("hotkey"):
            hotkeys.add(str(r["hotkey"]))
    coldkeys = await _coldkeys_for_hotkeys(db, subnet, hotkeys)

    members = dashboard.get("reign", {}).get("members") or []
    reign_chain = [
        _reign_member(m, coldkeys.get(str(m.get("hotkey") or "")))
        for m in sorted(members, key=lambda x: int(x.get("king_version") or 0), reverse=True)
    ]
    king_raw = current_king(dashboard.get("reign") or {})
    current = _reign_member(king_raw, coldkeys.get(str(king_raw.get("hotkey") or ""))) if king_raw else None

    duels = [_duel_run(r) for r in dashboard.get("eval_runs") or []]
    duels.sort(key=lambda d: d.finished_at or "", reverse=True)
    crownings = [_duel_run(r) for r in dashboard.get("crownings") or []]
    crownings.sort(key=lambda d: int(d.king_version or 0), reverse=True)
    fails = [_fail_run(r) for r in (dashboard.get("fails") or [])[:20]]

    return AlbedoStatusResponse(
        subnet=subnet,
        updated_at=dashboard.get("updated_at"),
        schema_version=int(dashboard.get("schema_version") or 2),
        source_url="https://us-east-1.hippius.com/albedo/data/dashboard.json",
        current_king=current,
        reign_chain=reign_chain,
        crownings=crownings,
        recent_duels=duels[:25],
        recent_fails=fails,
        pipeline=_pipeline_state(state_raw),
        stats=dashboard.get("stats") or {},
        queue_len=len(dashboard.get("queue") or []),
        current_eval=dashboard.get("current_eval"),
    )


@router.get("/analytics", response_model=HfAnalyticsResponse)
async def hf_analytics(
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=40, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> HfAnalyticsResponse:
    """HF namespace leaderboard: crowns, dethrones, win/crown rates."""
    dashboard = await fetch_albedo_dashboard()
    if not dashboard:
        return HfAnalyticsResponse(
            subnet=subnet,
            summary=HfAnalyticsSummary(),
        )

    hotkeys: set[str] = set()
    for r in dashboard.get("eval_runs") or []:
        if r.get("hotkey"):
            hotkeys.add(str(r["hotkey"]))
    coldkeys = await _coldkeys_for_hotkeys(db, subnet, hotkeys)
    built = build_hf_analytics(dashboard, coldkey_by_hotkey=coldkeys)

    accounts = [HfAccountStats(**row) for row in built["accounts"][:limit]]
    summary = HfAnalyticsSummary(
        total_eval_runs=built["total_eval_runs"],
        total_crownings=built["total_crownings"],
        unique_hf_accounts=built["unique_hf_accounts"],
        top_crown_holder=built["top_crown_holder"],
        crown_share_top=built["crown_share_top"],
    )
    return HfAnalyticsResponse(
        subnet=subnet,
        updated_at=dashboard.get("updated_at"),
        summary=summary,
        accounts=accounts,
    )


@router.get("/incentives", response_model=IncentiveOverviewResponse)
async def incentive_overview(
    subnet: int = Query(default=97, ge=0),
    limit: int = Query(default=50, ge=1, le=256),
    min_incentive: float = Query(default=0.0, ge=0.0),
    live: bool = Query(default=False, description="Fetch metagraph from chain (slow)"),
    db: AsyncSession = Depends(get_db),
) -> IncentiveOverviewResponse:
    dashboard = await fetch_albedo_dashboard()
    king_raw = current_king((dashboard or {}).get("reign") or {}) if dashboard else None
    king = _reign_member(king_raw) if king_raw else None
    king_hk = king_hotkey(dashboard)
    king_id = king_uid(dashboard)

    metagraph_block: int | None = None
    neuron_rows: list[tuple[int, str, str | None, float, float, int | None, bool]] = []

    if live:
        client = SubtensorClient(settings)
        await client.connect()
        try:
            snapshot = await client.get_subnet_snapshot(subnet)
            metagraph_block = snapshot.block
            miners_only = [n for n in snapshot.neurons if not n.is_validator]
            ranked = sorted(miners_only, key=lambda n: n.incentive, reverse=True)
            rank_positions = {n.uid: pos + 1 for pos, n in enumerate(ranked)}
            for n in snapshot.neurons:
                if n.is_validator:
                    continue
                neuron_rows.append(
                    (
                        n.uid,
                        n.hotkey,
                        n.coldkey,
                        n.incentive,
                        n.emission,
                        rank_positions.get(n.uid),
                        n.is_validator,
                    )
                )
        finally:
            await client.disconnect()
    else:
        for m in await _load_miners(db, subnet):
            if m.is_validator:
                continue
            neuron_rows.append(
                (
                    m.uid,
                    m.hotkey,
                    m.coldkey,
                    float(m.current_incentive or 0.0),
                    float(m.current_emission or 0.0),
                    m.rank_position,
                    m.is_validator,
                )
            )

    commits_by_uid = await _load_commits(db, subnet)
    entries: list[MinerIncentiveEntry] = []
    for uid, hotkey, coldkey, incentive, emission, rank_pos, is_validator in neuron_rows:
        if incentive < min_incentive:
            continue
        commit = commits_by_uid.get(uid)
        is_king = (king_hk is not None and hotkey == king_hk) or (
            king_id is not None and uid == king_id
        )
        entries.append(
            MinerIncentiveEntry(
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                incentive=incentive,
                emission=emission,
                rank_position=rank_pos,
                is_validator=is_validator,
                receiving_incentive=incentive > 0,
                is_king=is_king,
                king_model_repo=king.model_repo if is_king and king else None,
                commit_repo=commit.repo if commit else None,
            )
        )

    entries.sort(key=lambda e: (-e.incentive, e.uid))
    entries = entries[:limit]
    top = entries[0].incentive if entries else 0.0
    return IncentiveOverviewResponse(
        subnet=subnet,
        metagraph_block=metagraph_block,
        king=king,
        incentivized_count=sum(1 for e in entries if e.receiving_incentive),
        top_incentive=top,
        miners=entries,
    )


async def _load_miners(db: AsyncSession, subnet: int) -> list[Miner]:
    result = await db.execute(
        select(Miner).where(
            Miner.subnet == subnet,
            Miner.status == MinerStatus.ACTIVE,
        ).order_by(Miner.current_incentive.desc(), Miner.uid.asc())
    )
    return list(result.scalars().all())


async def _load_commits(db: AsyncSession, subnet: int) -> dict[int, MinerCommitment]:
    result = await db.execute(
        select(MinerCommitment).where(
            MinerCommitment.subnet == subnet,
            MinerCommitment.version.in_(_MODEL_VERSIONS),
        )
    )
    rows = list(result.scalars().all())
    return {r.uid: r for r in rows if r.uid is not None}
