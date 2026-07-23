"""Schemas for SN97 data-driven merge recommendations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MergeAdvisorMode = Literal["current_king", "multi_king"]


class AlbedoMergeGlobalBtRow(BaseModel):
    rank: int
    model_uri: str
    label: str
    repo: str | None = None
    bt_strength: float


class AlbedoMergeDonorCandidate(BaseModel):
    model_uri: str
    repo: str | None = None
    label: str
    mergekit_ref: str
    model_family: str | None = None
    sources: list[str] = Field(default_factory=list)
    duels: int
    wins: int
    losses: int
    win_pct: float
    historical_duels: int = 0
    avg_margin: float | None = None
    bt_strength: float
    global_bt_rank: int | None = None
    coronations: int = 0
    reign_slots: int = 0
    judge_reliability: float | None = None
    merge_weight: float
    density: float | None = None


class AlbedoMergeMethodOption(BaseModel):
    method: str
    score: float
    rationale: str


class AlbedoMergeMethodRecommendation(BaseModel):
    method: str
    pretty_name: str
    parameters: dict[str, float | bool | str] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)
    alternatives: list[AlbedoMergeMethodOption] = Field(default_factory=list)


class AlbedoMergeMethodYaml(BaseModel):
    method: str
    pretty_name: str
    score: float
    is_primary: bool = False
    yaml: str


class AlbedoMergeLayerHint(BaseModel):
    """Optional per-layer density gradient for mergekit YAML comments."""

    layer_fraction_start: float
    layer_fraction_end: float
    density: float
    note: str


class AlbedoMergeAdvisorRecommendation(BaseModel):
    subnet: int = 97
    generated_at: str | None = None
    mode: MergeAdvisorMode = "current_king"
    king_versions_scanned: list[int] = Field(default_factory=list)
    include_past_kings: bool = False
    min_duels: int = 2
    base_model_uri: str
    base_repo: str | None = None
    base_mergekit_ref: str
    base_label: str
    base_model_family: str | None = None
    donors: list[AlbedoMergeDonorCandidate] = Field(default_factory=list)
    method: AlbedoMergeMethodRecommendation
    layer_hints: list[AlbedoMergeLayerHint] = Field(default_factory=list)
    mergekit_yaml: str
    method_yamls: list[AlbedoMergeMethodYaml] = Field(default_factory=list)
    global_bt_leaderboard: list[AlbedoMergeGlobalBtRow] = Field(default_factory=list)
    architecture_warnings: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    duels_analyzed: int = 0
    binary_duels_analyzed: int = 0
    judge_consensus_duels: int = 0
    note: str | None = None
