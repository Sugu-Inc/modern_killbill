"""Pydantic schemas for WebhookEvent model."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from billing.models.webhook_event import WebhookStatus


class WebhookEventBase(BaseModel):
    """Base webhook event schema with common fields."""

    event_type: str = Field(..., min_length=1, description="Webhook event type (stripe.invoice.paid, etc.)")
    payload: dict[str, Any] = Field(..., description="Webhook payload data")


class WebhookEventCreate(WebhookEventBase):
    """Schema for creating a new webhook event."""

    pass


class WebhookEvent(WebhookEventBase):
    """Schema for returning webhook event data."""

    id: UUID
    status: WebhookStatus
    retry_count: int
    next_retry_at: datetime | None
    processed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEventList(BaseModel):
    """Schema for paginated webhook event list."""

    items: list[WebhookEvent]
    total: int
    page: int
    page_size: int
