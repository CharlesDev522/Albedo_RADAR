"""Pydantic schemas for v6 commitment API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommitmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subnet: int
    uid: int | None
    hotkey: str
    coldkey: str | None
    registered_at_block: int | None
    commit_block: int
    block_hash: str | None
    reveal_string: str
    version: str
    repo: str
    digest: str
    model_uri: str
    payload_hash: str
    commit_payload: dict[str, Any]
    commit_source: str = "active"
    first_seen: datetime
    last_updated: datetime

    @field_validator("commit_source", mode="before")
    @classmethod
    def default_commit_source(cls, v: str | None) -> str:
        return v or "active"


class CommitmentListResponse(BaseModel):
    commitments: list[CommitmentResponse]
    total: int
    subnet: int
    committed_count: int
    uncommitted_uids: list[int] = Field(default_factory=list)


class CommitmentStatsResponse(BaseModel):
    subnet: int
    total_neurons: int
    committed_miners: int
    uncommitted_miners: int
    coverage_pct: float
    latest_commit_block: int | None
    last_scan_at: datetime | None


class MinerRegistryEntry(BaseModel):
    uid: int
    hotkey: str
    coldkey: str
    registered_at_block: int | None
    has_v6: bool
    version: str | None = None
    commit_block: int | None = None
    repo: str | None = None
    model_uri: str | None = None
    commit_source: str | None = None
    last_updated: datetime | None = None


class MinerRegistryResponse(BaseModel):
    subnet: int
    miners: list[MinerRegistryEntry]
    total: int
    v6_count: int = 0
    uncommitted_count: int


class CommitmentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subnet: int
    uid: int | None
    hotkey: str
    coldkey: str | None
    commit_block: int
    repo: str
    digest: str
    model_uri: str
    reveal_string: str
    revealed_at: datetime
