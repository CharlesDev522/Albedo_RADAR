"""TAO price and subnet registration economics."""

from fastapi import APIRouter, Query

from app.config import get_settings
from app.integrations.market_client import build_market_overview
from app.schemas.market import MarketOverviewResponse

router = APIRouter(prefix="/market", tags=["market"])
settings = get_settings()


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview(
    subnet: int = Query(default=97, ge=0),
) -> MarketOverviewResponse:
    """TAO/USD price (CoinGecko; optional TaoMarketCap) and on-chain SN reg burn."""
    data = await build_market_overview(subnet)
    return MarketOverviewResponse.model_validate(data)
