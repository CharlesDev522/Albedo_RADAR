"""Quasar SN24 status — king, eval phase, submissions (no duel history)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import get_settings
from app.integrations.quasar_client import fetch_quasar_dashboard
from app.integrations.quasar_normalize import normalize_status
from app.schemas.quasar import (
    QuasarChainKing,
    QuasarEvalPhase,
    QuasarKing,
    QuasarStatusResponse,
)

router = APIRouter(prefix="/quasar", tags=["quasar"])
settings = get_settings()


@router.get("/status", response_model=QuasarStatusResponse)
async def quasar_status(
    subnet: int = Query(default=24, ge=0),
) -> QuasarStatusResponse:
    """Current king, chain vs state king, eval phase, submission counts."""
    dashboard = await fetch_quasar_dashboard()
    if not dashboard:
        return QuasarStatusResponse(
            subnet=subnet,
            source_url=settings.quasar_dashboard_url,
        )

    normalized = normalize_status(dashboard)
    king_raw = normalized.get("king")
    chain_raw = normalized.get("consensus_king")
    phase_raw = normalized.get("eval_phase")

    return QuasarStatusResponse(
        subnet=subnet,
        source_url=settings.quasar_dashboard_url,
        king=QuasarKing(**king_raw) if king_raw else None,
        consensus_king=QuasarChainKing(**chain_raw) if chain_raw else None,
        state_king_uid=normalized.get("state_king_uid"),
        eval_phase=QuasarEvalPhase(**phase_raw) if phase_raw else None,
        current_eval=normalized.get("current_eval"),
        queue_len=int(normalized.get("queue_len") or 0),
        submission_counts=normalized.get("submission_counts") or {},
        policy=normalized.get("policy"),
    )
