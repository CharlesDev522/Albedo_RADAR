"""Schemas for Albedo eval queue, pipeline stages, and DQ failures."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.albedo_analysis import AlbedoCurrentEval


class AlbedoEvalParticipant(BaseModel):
    position: int | None = None
    uid: int | None = None
    hotkey: str | None = None
    repo: str | None = None
    model_uri: str | None = None
    model_name: str | None = None
    namespace: str | None = None
    state: str | None = None
    submission_id: str | None = None
    eval_run_id: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    commit_block: int | None = None


class AlbedoPipelineBucket(BaseModel):
    stage: str
    label: str
    running_count: int = 0
    queued_count: int = 0
    running: list[AlbedoEvalParticipant] = Field(default_factory=list)
    queued: list[AlbedoEvalParticipant] = Field(default_factory=list)


class AlbedoEvalFail(BaseModel):
    submission_id: str | None = None
    eval_run_id: str | None = None
    uid: int | None = None
    hotkey: str | None = None
    repo: str | None = None
    model_uri: str | None = None
    state: str | None = None
    fault_class: str | None = None
    fault_code: str | None = None
    fault_message: str | None = None
    updated_at: str | None = None


class AlbedoEvalQueueOverview(BaseModel):
    subnet: int = 97
    source_url: str = ""
    updated_at: str | None = None
    dashboard_updated_at: str | None = None
    state_updated_at: str | None = None
    current_eval: AlbedoCurrentEval | None = None
    queue: list[AlbedoEvalParticipant] = Field(default_factory=list)
    pipeline: list[AlbedoPipelineBucket] = Field(default_factory=list)
    fails: list[AlbedoEvalFail] = Field(default_factory=list)
    fail_counts_by_class: dict[str, int] = Field(default_factory=dict)
    queue_length: int = 0
    fail_count: int = 0
    note: str = ""
