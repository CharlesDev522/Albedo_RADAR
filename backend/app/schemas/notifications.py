"""Pydantic schemas for alert notifications API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    severity: str
    title: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    source_key: str
    subnet: int | None
    slack_sent: bool
    created_at: datetime


class AlertNotificationList(BaseModel):
    items: list[AlertNotificationResponse]
    latest_id: int | None = None


class NotificationKindSetting(BaseModel):
    enabled: bool
    label: str
    default_enabled: bool


class NotificationKindGroup(BaseModel):
    id: str
    label: str
    kinds: list[str]


class NotificationSettingsResponse(BaseModel):
    notifications_enabled: bool
    env_notifications_enabled: bool
    stored_notifications_enabled: bool | None = None
    webhook_configured: bool
    slack_channel: str | None = None
    kinds: dict[str, NotificationKindSetting]
    groups: list[NotificationKindGroup]
    updated_at: str | None = None


class NotificationSettingsUpdate(BaseModel):
    notifications_enabled: bool | None = None
    kinds: dict[str, bool] | None = None
