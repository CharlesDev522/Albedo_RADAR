"""Pydantic schemas for Hippius repo activity API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RepoTrackEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subnet: int
    repo: str
    repo_host: str = "hippius"
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
    pending_hub_poll: bool = False
    track_source: str | None = None


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
    tracked_miners: int
    unique_repos: int
    tracked_repos: int  # backwards-compatible alias for tracked_miners
    qwen36_35b_repos: int
    qwen3_4b_repos: int
    in_sync_count: int
    mismatch_count: int
    hub_updates_24h: int
    on_chain_events_24h: int
    last_poll_at: datetime | None
    hippius_count: int = 0
    huggingface_count: int = 0
    pending_hub_poll: int = 0
    hub_watch_count: int = 0
    slot_only_count: int = 0
    chain_committed_count: int = 0


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


class HippiusLatestRepo(BaseModel):
    repo: str
    model_family: str | None = None
    digest: str
    indexed_at: datetime | None = None
    file_count: int | None = None
    total_size_bytes: int | None = None
    hub_url: str


class HippiusLatestResponse(BaseModel):
    total_indexed: int
    repos: list[HippiusLatestRepo] = Field(default_factory=list)


class HuggingFaceLatestRepo(BaseModel):
    repo: str
    model_family: str | None = None
    digest: str
    indexed_at: datetime | None = None
    file_count: int | None = None
    total_size_bytes: int | None = None
    hub_url: str
    downloads: int = 0
    likes: int = 0
    tags: list[str] = Field(default_factory=list)
    is_tracked: bool = False
    digest_in_sync: bool | None = None
    pending_hub_poll: bool = False
    tracked_uid: int | None = None
    track_source: str | None = None


class HuggingFaceSortOption(BaseModel):
    key: str
    label: str


class HuggingFaceLatestResponse(BaseModel):
    total_indexed: int
    repos: list[HuggingFaceLatestRepo] = Field(default_factory=list)
    sort: str = "createdAt"
    tags: list[str] = Field(default_factory=list)
    hub_search_url: str | None = None
    error: str | None = None


class HuggingFaceSearchOptionsResponse(BaseModel):
    sort_options: list[HuggingFaceSortOption] = Field(default_factory=list)
    tag_options: list[str] = Field(default_factory=list)
    default_sort: str = "createdAt"
    default_tags: list[str] = Field(default_factory=list)
