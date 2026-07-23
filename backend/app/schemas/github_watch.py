"""Schemas for GitHub repo watch API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GithubRepoWatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    owner: str
    repo: str
    branch: str
    tree_url: str
    seeded_at: datetime | None = None
    seeded_sha: str | None = None
    last_seen_sha: str | None = None
    last_commit_subject: str | None = None
    last_commit_url: str | None = None
    last_checked_at: datetime | None = None


class GithubCommitAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    owner: str
    repo: str
    branch: str
    commit_sha: str
    commit_subject: str
    commit_body: str | None = None
    commit_url: str
    title: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    slack_sent: bool
    created_at: datetime


class GithubWatchTargetResponse(BaseModel):
    owner: str
    repo: str
    branch: str
    tree_url: str
    full_name: str


class GithubWatchOverviewResponse(BaseModel):
    enabled: bool
    poll_interval_seconds: int
    configured_targets: list[GithubWatchTargetResponse]
    watch_states: list[GithubRepoWatchResponse]
    recent_alerts: list[GithubCommitAlertResponse]
