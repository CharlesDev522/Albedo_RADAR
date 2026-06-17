"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import EventType, MinerStatus


class MinerBase(BaseModel):
    uid: int
    hotkey: str
    coldkey: str
    subnet: int


class MinerResponse(MinerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    registered_at_block: int | None = None
    first_seen: datetime
    last_seen: datetime
    status: MinerStatus
    is_validator: bool
    current_stake: float
    current_alpha_stake: float
    current_tao_stake: float
    current_emission: float
    current_incentive: float
    current_rank: float
    current_trust: float
    rank_position: int | None = None


class MinerListResponse(BaseModel):
    miners: list[MinerResponse]
    total: int
    subnet: int


class MinerTimelineEvent(BaseModel):
    event_type: EventType
    timestamp: datetime
    block: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MinerTimelineResponse(BaseModel):
    miner: MinerResponse
    timeline: list[MinerTimelineEvent]


class EmissionPoint(BaseModel):
    block: int
    emission: float
    incentive: float
    timestamp: datetime


class StakePoint(BaseModel):
    block: int
    stake: float
    alpha_stake: float
    tao_stake: float
    timestamp: datetime


class RankPoint(BaseModel):
    block: int
    rank: float
    rank_position: int
    trust: float
    timestamp: datetime


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EventType
    miner_id: int | None
    subnet: int
    block: int | None
    data: dict[str, Any]
    timestamp: datetime


class EventFeedResponse(BaseModel):
    events: list[EventResponse]
    total: int


class HotkeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hotkey: str
    coldkey: str | None
    subnet: int
    uid: int | None
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    uid_history: list[dict[str, Any]]


class ColdkeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    coldkey: str
    miner_count: int
    validator_count: int
    total_stake: float
    total_emission: float
    hotkeys: list[str]
    subnets: list[int]
    first_seen: datetime
    last_seen: datetime


class ColdkeyDetailResponse(ColdkeyResponse):
    miners: list[MinerResponse]


class LeaderboardEntry(BaseModel):
    rank: int
    miner_id: int
    uid: int
    hotkey: str
    coldkey: str
    value: float
    change_7d: float | None = None


class LeaderboardResponse(BaseModel):
    category: str
    subnet: int
    entries: list[LeaderboardEntry]
    updated_at: datetime


class SubnetStatsResponse(BaseModel):
    subnet: int
    block: int
    neuron_count: int
    active_miners: int
    active_validators: int
    total_stake: float
    total_emission: float
    last_updated: datetime


class HealthResponse(BaseModel):
    status: str
    version: str
    network: str
    default_subnet: int
