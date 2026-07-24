"""Persist and merge king coronation history beyond the albedo.tech dashboard window."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
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


async def purge_voided_coronations(
    session: AsyncSession,
    subnet: int,
    voided_versions: set[int],
) -> int:
    """Remove illegitimate kings that were rolled back from the reign chain."""
    if not voided_versions:
        return 0
    result = await session.execute(
        delete(AlbedoKingCrownRecord).where(
            AlbedoKingCrownRecord.subnet == subnet,
            AlbedoKingCrownRecord.king_version.in_(sorted(voided_versions)),
        )
    )
    removed = int(result.rowcount or 0)
    if removed:
        logger.info("purged %d voided king crown records subnet=%d versions=%s", removed, subnet, sorted(voided_versions))
    return removed


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


def _coronation_from_seed_raw(raw: dict[str, Any]) -> AlbedoKingCoronation | None:
    from app.services.albedo_analysis_service import parse_model_uri

    king_version = raw.get("king_version")
    finished_at = raw.get("finished_at") or raw.get("crowned_at")
    model_uri = raw.get("model_uri") or ""
    if king_version is None or not finished_at or not model_uri:
        return None
    ns, name, uri = parse_model_uri(model_uri)
    repo = raw.get("repo")
    if not repo and ns:
        repo = f"{ns}/{name}" if name else ns
    return AlbedoKingCoronation(
        king_version=int(king_version),
        model_uri=uri or model_uri,
        model_name=name or raw.get("model_name") or "",
        namespace=ns or raw.get("namespace") or "",
        repo=repo,
        coldkey=raw.get("coldkey"),
        hotkey=str(raw.get("hotkey") or ""),
        uid=int(raw.get("uid") or 0),
        finished_at=str(finished_at),
        eval_run_id=str(raw.get("eval_run_id") or f"seed-v{king_version}"),
        score_challenger=float(raw.get("score_challenger") or 0),
        score_king=float(raw.get("score_king") or 0),
        win_margin=float(raw.get("win_margin") or 0),
        defeated_king_version=raw.get("defeated_king_version"),
        defeated_model_uri=raw.get("defeated_model_uri"),
        defeated_repo=raw.get("defeated_repo"),
        defeated_coldkey=raw.get("defeated_coldkey"),
    )


def coronations_from_seed_payload(payload: Any) -> list[AlbedoKingCoronation]:
    rows = payload if isinstance(payload, list) else payload.get("coronations", [])
    out: list[AlbedoKingCoronation] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        cor = _coronation_from_seed_raw(raw)
        if cor:
            out.append(cor)
    return out


def resolve_crown_seed_path(settings: Settings | None = None) -> Path | None:
    settings = settings or get_settings()
    candidates: list[Path] = []
    if settings.albedo_crown_seed_path:
        candidates.append(Path(settings.albedo_crown_seed_path))
    candidates.extend(
        [
            Path("data/albedo_crown_seed_sn97.json"),
            Path("/app/data/albedo_crown_seed_sn97.json"),
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


async def import_crown_seed_file(
    session: AsyncSession,
    subnet: int,
    path: Path,
    *,
    miner_lookup: MinerLookup | None = None,
) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    coronations = coronations_from_seed_payload(payload)
    if miner_lookup:
        enriched: list[AlbedoKingCoronation] = []
        for cor in coronations:
            ident = lookup.resolve(hotkey=cor.hotkey or None, uid=cor.uid, model_uri=cor.model_uri)
            if ident:
                cor = cor.model_copy(
                    update={"repo": cor.repo or ident.repo, "coldkey": cor.coldkey or ident.coldkey}
                )
            enriched.append(cor)
        coronations = enriched
    count = await upsert_coronations(session, subnet, coronations, source="seed")
    logger.info("imported %d crown seed records from %s", count, path)
    return count


async def import_crown_seed_if_configured(
    session: AsyncSession,
    subnet: int,
    *,
    settings: Settings | None = None,
    miner_lookup: MinerLookup | None = None,
) -> int:
    path = resolve_crown_seed_path(settings)
    if path is None:
        return 0
    return await import_crown_seed_file(session, subnet, path, miner_lookup=miner_lookup)


async def archived_crown_count(session: AsyncSession, subnet: int) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(AlbedoKingCrownRecord)
                .where(AlbedoKingCrownRecord.subnet == subnet)
            )
        ).scalar()
        or 0
    )
