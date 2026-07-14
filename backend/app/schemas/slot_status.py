"""Schemas for per-UID slot commitment status."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.chain_reader.albedo_model_family import infer_albedo_model_family, repo_from_slot_detail


class SlotStatusEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: int
    hotkey: str
    coldkey: str | None
    registered_at_block: int | None
    commitment_type: str
    commit_block: int | None
    deposit: int | None
    reveal_round: int | None
    detail: str | None
    last_updated: datetime | None = None
    is_published: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def model_family(self) -> str | None:
        repo = repo_from_slot_detail(self.detail, self.commitment_type)
        return infer_albedo_model_family(repo)


class SlotStatusSummary(BaseModel):
    subnet: int
    total_slots: int
    v6: int = 0
    v7: int = 0
    json: int = 0
    timelock_encrypted: int = 0
    binary: int = 0
    other: int = 0
    unknown: int = 0
    none: int = 0
    committed: int = 0
    unpublished: int = 0
    qwen36_35b: int = 0
    qwen3_4b: int = 0
    last_scan_at: datetime | None = None


class SlotStatusResponse(BaseModel):
    subnet: int
    slots: list[SlotStatusEntry]
    summary: SlotStatusSummary
    filter: str | None = None
    sort: str | None = None
    source: str = "db"
