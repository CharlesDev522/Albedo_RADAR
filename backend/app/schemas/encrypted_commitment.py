"""Pydantic schemas for TimelockEncrypted commitment API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EncryptedCommitmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subnet: int
    uid: int | None
    hotkey: str
    coldkey: str | None
    registered_at_block: int | None
    commit_block: int
    deposit: int
    reveal_round: int
    encrypted_hash: str
    encrypted_preview: str
    commitment_kind: str
    status: str
    first_seen: datetime
    last_updated: datetime


class EncryptedCommitmentListResponse(BaseModel):
    commitments: list[EncryptedCommitmentResponse]
    total: int
    subnet: int
    pending_count: int


class EncryptedCommitmentStatsResponse(BaseModel):
    subnet: int
    pending_encrypted: int
    revealed_total: int
    latest_commit_block: int | None
    latest_reveal_round: int | None
    last_scan_at: datetime | None
