"""Schemas for Quasar SN24 validator dashboard (status only — no duel history)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuasarKing(BaseModel):
    uid: int | None = None
    hf_repo: str | None = None
    king_revision: str | None = None
    reign_number: int | None = None
    crowned_at: str | None = None
    weights_block: int | None = None


class QuasarChainKing(BaseModel):
    uid: int | None = None
    hf_repo: str | None = None
    revision: str | None = None
    support_fraction: float | None = None
    block: int | None = None


class QuasarEvalPhase(BaseModel):
    active: bool = False
    phase: str | None = None
    label: str | None = None
    detail: str | None = None
    state_king_uid: int | None = None
    chain_king_uid: int | None = None
    winner_uid: int | None = None
    weight_reveal_pending: bool = False
    current_block: int | None = None


class QuasarStatusResponse(BaseModel):
    subnet: int = 24
    source_url: str
    dashboard_url: str = "https://sn24.quasarcopilot.com"
    king: QuasarKing | None = None
    consensus_king: QuasarChainKing | None = None
    state_king_uid: int | None = None
    eval_phase: QuasarEvalPhase | None = None
    current_eval: str | None = None
    queue_len: int = 0
    submission_counts: dict[str, int] = Field(default_factory=dict)
    policy: dict[str, Any] | None = None
