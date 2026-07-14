"""Market / network economics schemas."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketOverviewResponse(BaseModel):
    subnet: int
    tao_price_usd: float | None = None
    tao_price_source: str | None = None
    tao_price_updated_at: datetime | None = None
    registration_burn_tao: float | None = None
    registration_burn_usd: float | None = None
    alpha_price_tao: float | None = None
    chain_block: int | None = None
    network: str
    fetched_at: datetime = Field(default_factory=_utcnow)
