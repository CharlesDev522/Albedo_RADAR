"""Alert notification history API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertNotification
from app.db.session import get_db
from app.schemas.notifications import AlertNotificationList, AlertNotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=AlertNotificationList)
async def list_notifications(
    since_id: int = Query(default=0, ge=0, description="Return alerts with id > since_id"),
    limit: int = Query(default=50, ge=1, le=200),
    kinds: str | None = Query(default=None, description="Comma-separated alert kinds"),
    db: AsyncSession = Depends(get_db),
) -> AlertNotificationList:
    q = select(AlertNotification).where(AlertNotification.id > since_id)
    if kinds:
        kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
        if kind_list:
            q = q.where(AlertNotification.kind.in_(kind_list))
    q = q.order_by(AlertNotification.id.asc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    items = [AlertNotificationResponse.model_validate(r) for r in rows]
    latest_id = items[-1].id if items else (since_id if since_id else None)
    return AlertNotificationList(items=items, latest_id=latest_id)
