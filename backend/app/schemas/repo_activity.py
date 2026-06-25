"""Pydantic schemas for Hippius repo activity API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RepoTrackEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subnet: int
    repo: str
    uid: int | None
    hotkey: str | None
    coldkey: str | None
    model_family: str | None
    chain_digest: str | None
    hub_digest: str | None
    hub_revision: str
    hub_commit_message: str | None
    hub_updated_at: datetime | None
    file_count: int | None
    total_bytes: int | None
    digest_in_sync: bool | None
    last_checked_at: datetime | None
    last_hub_change_at: datetime | None
    first_tracked_at: datetime
    last_updated: datetime


class RepoActivityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subnet: int
    event_type: str
    repo: str
    uid: int | None
    hotkey: str | None
    coldkey: str | None
    model_family: str | None
    chain_digest: str | None
    hub_digest: str | None
    previous_digest: str | None
    revision: str | None
    commit_block: int | None
    commit_message: str | None
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    detected_at: datetime
    meta: dict[str, Any] = Field(default_factory=dict)


class RepoActivityOverview(BaseModel):
    subnet: int
    tracked_repos: int
    qwen36_35b_repos: int
    qwen3_4b_repos: int
    in_sync_count: int
    mismatch_count: int
    hub_updates_24h: int
    on_chain_events_24h: int
    last_poll_at: datetime | None


class RepoRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo: str
    revision: str
    manifest_digest: str
    commit_message: str | None
    hub_created_at: datetime | None
    file_count: int
    total_bytes: int
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    detected_at: datetime
