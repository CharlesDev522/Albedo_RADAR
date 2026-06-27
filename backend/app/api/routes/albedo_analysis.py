"""Albedo duel and king-of-the-hill analysis from Hippius dashboard JSON."""

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.schemas.albedo_analysis import AlbedoAnalysisOverview
from app.services.albedo_analysis_service import get_albedo_analysis_overview

router = APIRouter(prefix="/albedo", tags=["albedo"])


@router.get("/analysis", response_model=AlbedoAnalysisOverview)
async def albedo_analysis_overview(
    subnet: int = Query(default=97, ge=0),
) -> AlbedoAnalysisOverview:
    """Cross-dimensional duel analytics: win rates, king history, judges, timeline."""
    if subnet != 97:
        raise HTTPException(status_code=400, detail="Albedo duel analysis is only available for SN97")
    settings = get_settings()
    try:
        return await get_albedo_analysis_overview(subnet, settings=settings)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch Albedo dashboard: {exc}",
        ) from exc
