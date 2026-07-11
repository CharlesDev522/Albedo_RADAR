"""Schemas for SN97 data-driven merge recommendations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoMergeDonorCandidate(BaseModel):
    model_uri: str
    repo: str | None = None
    label: str
    mergekit_ref: str
    duels: int
    wins: int
    losses: int
    win_pct: float
    avg_margin: float | None = None
    bt_strength: float
    coronations: int = 0
    reign_slots: int = 0
    sample_mass: float | None = None
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


class AlbedoMergeLayerHint(BaseModel):
    """Optional per-layer density gradient for mergekit YAML comments."""

    layer_fraction_start: float
    layer_fraction_end: float
    density: float
    note: str


class AlbedoMergeAdvisorRecommendation(BaseModel):
    subnet: int = 97
    generated_at: str | None = None
    base_model_uri: str
    base_repo: str | None = None
    base_mergekit_ref: str
    base_label: str
    donors: list[AlbedoMergeDonorCandidate] = Field(default_factory=list)
    method: AlbedoMergeMethodRecommendation
    layer_hints: list[AlbedoMergeLayerHint] = Field(default_factory=list)
    mergekit_yaml: str
    rationale: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    duels_analyzed: int = 0
    binary_duels_analyzed: int = 0
    sample_mass_duels: int = 0
    judge_consensus_duels: int = 0
    note: str | None = None
