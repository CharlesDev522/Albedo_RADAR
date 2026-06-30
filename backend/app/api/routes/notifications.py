"""Alert notification history API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AlertNotification
from app.db.session import get_db
from app.notifications.slack import send_slack_alert
from app.schemas.notifications import AlertNotificationList, AlertNotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/status")
async def notification_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Check whether Slack notifications are configured (for debugging)."""
    settings = get_settings()
    webhook = (settings.slack_webhook_url or "").strip()
    total = (await db.execute(select(func.count()).select_from(AlertNotification))).scalar() or 0
    sent = (
        await db.execute(
            select(func.count()).select_from(AlertNotification).where(AlertNotification.slack_sent.is_(True))
        )
    ).scalar() or 0
    return {
        "enabled": settings.notifications_enabled,
        "webhook_configured": bool(webhook),
        "slack_channel": settings.slack_channel,
        "slack_app_name": settings.slack_app_name,
        "reg_fee_threshold_tao": settings.notification_reg_fee_threshold_tao,
        "grace_seconds": settings.notification_grace_seconds,
        "alerts_in_db": total,
        "alerts_slack_sent": sent,
        "hint": (
            "OK — collector will post new events to Slack after startup sync"
            if webhook and settings.notifications_enabled
            else "Set SLACK_WEBHOOK_URL in .env and restart: docker compose up -d --force-recreate collector"
        ),
    }


@router.post("/test-slack")
async def test_slack_notification() -> dict:
    """Send a test message to Slack (verifies webhook + channel)."""
    settings = get_settings()
    if not (settings.slack_webhook_url or "").strip():
        return {"status": "error", "detail": "SLACK_WEBHOOK_URL is not set in .env"}
    ok = await send_slack_alert(
        settings=settings,
        kind="reg_fee_low",
        title="[test] Albedo_Notification",
        message="MinerWatch Slack test — if you see this, notifications are working.",
        detail={"note": "Triggered manually via POST /api/v1/notifications/test-slack"},
        subnet=settings.default_subnet,
    )
    return {
        "status": "ok" if ok else "failed",
        "webhook_configured": True,
        "channel": settings.slack_channel,
        "app_name": settings.slack_app_name,
    }


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
