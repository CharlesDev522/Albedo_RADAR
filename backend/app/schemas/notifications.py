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
