"""Persist and merge king coronation history beyond Hippius dashboard window."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertNotification, AlbedoKingCrownRecord
from app.schemas.albedo_analysis import AlbedoKingCoronation
from app.services.albedo_king_history import coronation_from_eval_run
from app.services.albedo_miner_lookup import MinerLookup

logger = logging.getLogger(__name__)


def _parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record_to_coronation(
    row: AlbedoKingCrownRecord,
    *,
    lookup: MinerLookup | None = None,
) -> AlbedoKingCoronation:
    coldkey = row.coldkey
    repo = row.repo
    if lookup and row.hotkey and (not coldkey or not repo):
        ident = lookup.resolve(hotkey=row.hotkey, uid=row.uid, model_uri=row.model_uri)
        if ident:
            coldkey = coldkey or ident.coldkey
            repo = repo or ident.repo
    ns = row.namespace or ""
    name = row.model_name or ""
    if not repo and ns:
        repo = f"{ns}/{name}" if name else ns
    return AlbedoKingCoronation(
        king_version=row.king_version,
        model_uri=row.model_uri,
        model_name=name,
        namespace=ns,
        repo=repo,
        coldkey=coldkey,
        hotkey=row.hotkey or "",
        uid=int(row.uid or 0),
        finished_at=row.finished_at.isoformat(),
        eval_run_id=row.eval_run_id or "",
        score_challenger=float(row.score_challenger or 0),
        score_king=float(row.score_king or 0),
        win_margin=float(row.win_margin or 0),
        defeated_king_version=row.defeated_king_version,
        defeated_model_uri=row.defeated_model_uri,
        defeated_model_name=row.defeated_model_name,
        defeated_namespace=row.defeated_namespace,
        defeated_repo=row.defeated_repo,
        defeated_coldkey=row.defeated_coldkey,
    )


def _coronation_to_record(
    subnet: int,
    cor: AlbedoKingCoronation,
    *,
    source: str,
) -> AlbedoKingCrownRecord:
    finished = _parse_dt(cor.finished_at) or datetime.now(timezone.utc)
    return AlbedoKingCrownRecord(
        subnet=subnet,
        king_version=cor.king_version,
        eval_run_id=cor.eval_run_id or None,
        finished_at=finished,
        model_uri=cor.model_uri,
        model_name=cor.model_name or None,
        namespace=cor.namespace or None,
        repo=cor.repo,
        coldkey=cor.coldkey,
        hotkey=cor.hotkey or None,
        uid=cor.uid,
        score_challenger=cor.score_challenger,
        score_king=cor.score_king,
        win_margin=cor.win_margin,
        defeated_king_version=cor.defeated_king_version,
        defeated_model_uri=cor.defeated_model_uri,
        defeated_model_name=cor.defeated_model_name,
        defeated_namespace=cor.defeated_namespace,
        defeated_repo=cor.defeated_repo,
        defeated_coldkey=cor.defeated_coldkey,
        source=source,
    )


def _apply_coronation_to_row(row: AlbedoKingCrownRecord, cor: AlbedoKingCoronation, *, source: str) -> None:
    finished = _parse_dt(cor.finished_at)
    if finished:
        row.finished_at = finished
    row.eval_run_id = cor.eval_run_id or row.eval_run_id
    row.model_uri = cor.model_uri or row.model_uri
    row.model_name = cor.model_name or row.model_name
    row.namespace = cor.namespace or row.namespace
    row.repo = cor.repo or row.repo
    row.coldkey = cor.coldkey or row.coldkey
    row.hotkey = cor.hotkey or row.hotkey
    row.uid = cor.uid if cor.uid else row.uid
    row.score_challenger = cor.score_challenger
    row.score_king = cor.score_king
    row.win_margin = cor.win_margin
    row.defeated_king_version = cor.defeated_king_version
    row.defeated_model_uri = cor.defeated_model_uri or row.defeated_model_uri
    row.defeated_model_name = cor.defeated_model_name or row.defeated_model_name
    row.defeated_namespace = cor.defeated_namespace or row.defeated_namespace
    row.defeated_repo = cor.defeated_repo or row.defeated_repo
    row.defeated_coldkey = cor.defeated_coldkey or row.defeated_coldkey
    row.source = source


async def upsert_coronations(
    session: AsyncSession,
    subnet: int,
    coronations: list[AlbedoKingCoronation],
    *,
    source: str = "dashboard",
) -> int:
    if not coronations:
        return 0
    versions = [c.king_version for c in coronations]
    existing = (
        await session.execute(
            select(AlbedoKingCrownRecord).where(
                AlbedoKingCrownRecord.subnet == subnet,
                AlbedoKingCrownRecord.king_version.in_(versions),
            )
        )
    ).scalars().all()
    by_version = {row.king_version: row for row in existing}
    upserted = 0
    for cor in coronations:
        row = by_version.get(cor.king_version)
        if row is None:
            session.add(_coronation_to_record(subnet, cor, source=source))
            upserted += 1
        else:
            _apply_coronation_to_row(row, cor, source=source)
            upserted += 1
    return upserted


async def sync_crowns_from_dashboard(
    session: AsyncSession,
    subnet: int,
    dashboard: dict[str, Any],
    *,
    miner_lookup: MinerLookup | None = None,
) -> int:
    coronations: list[AlbedoKingCoronation] = []
    for run in dashboard.get("eval_runs") or []:
        if not isinstance(run, dict) or not run.get("coronated"):
            continue
        cor = coronation_from_eval_run(run, miner_lookup)
        if cor:
            coronations.append(cor)
    return await upsert_coronations(session, subnet, coronations, source="dashboard")


def _coronation_from_alert_detail(detail: dict[str, Any], *, king_version: int | None) -> AlbedoKingCoronation | None:
    from app.services.albedo_analysis_service import parse_model_uri

    if king_version is None:
        king_version = detail.get("king_version")
    if king_version is None:
        return None
    model_uri = detail.get("model_uri") or ""
    ns, name, uri = parse_model_uri(model_uri)
    repo = detail.get("repo")
    if not repo and ns:
        repo = f"{ns}/{name}" if name else ns
    finished = detail.get("finished_at") or ""
    if not finished:
        return None
    return AlbedoKingCoronation(
        king_version=int(king_version),
        model_uri=uri or model_uri,
        model_name=name,
        namespace=ns,
        repo=repo,
        coldkey=detail.get("coldkey"),
        hotkey=str(detail.get("hotkey") or ""),
        uid=int(detail.get("uid") or 0),
        finished_at=finished,
        eval_run_id=str(detail.get("eval_run_id") or ""),
        score_challenger=float(detail.get("score_challenger") or 0),
        score_king=float(detail.get("score_king") or 0),
        win_margin=float(detail.get("win_margin") or 0),
        defeated_king_version=detail.get("defeated_king_version"),
    )


async def backfill_crowns_from_alerts(
    session: AsyncSession,
    subnet: int,
    *,
    miner_lookup: MinerLookup | None = None,
) -> int:
    rows = (
        await session.execute(
            select(AlertNotification)
            .where(AlertNotification.subnet == subnet, AlertNotification.kind == "crown_won")
            .order_by(AlertNotification.created_at.asc())
        )
    ).scalars().all()
    coronations: list[AlbedoKingCoronation] = []
    for alert in rows:
        detail = alert.detail or {}
        cor = _coronation_from_alert_detail(detail, king_version=detail.get("king_version"))
        if not cor:
            continue
        if miner_lookup and cor.hotkey:
            ident = lookup.resolve(hotkey=cor.hotkey, uid=cor.uid, model_uri=cor.model_uri)
            if ident:
                cor = cor.model_copy(
                    update={
                        "repo": cor.repo or ident.repo,
                        "coldkey": cor.coldkey or ident.coldkey,
                    }
                )
        coronations.append(cor)
    return await upsert_coronations(session, subnet, coronations, source="alert")


async def load_archived_king_history(
    session: AsyncSession,
    subnet: int,
    *,
    miner_lookup: MinerLookup | None = None,
) -> list[AlbedoKingCoronation]:
    rows = (
        await session.execute(
            select(AlbedoKingCrownRecord)
            .where(AlbedoKingCrownRecord.subnet == subnet)
            .order_by(AlbedoKingCrownRecord.king_version.desc())
        )
    ).scalars().all()
    return [_record_to_coronation(row, lookup=miner_lookup) for row in rows]
