"""Pydantic schemas for UsageRecord model."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class UsageRecordBase(BaseModel):
    """Base usage record schema with common fields."""

    subscription_id: UUID = Field(..., description="Subscription ID this usage belongs to")
    metric: str = Field(..., min_length=1, description="Usage metric name (api_calls, storage_gb, etc.)")
    quantity: int = Field(..., gt=0, description="Number of units consumed")
    timestamp: datetime = Field(..., description="When usage occurred")
    extra_metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible custom fields")


class UsageRecordCreate(UsageRecordBase):
    """Schema for creating a new usage record."""

    idempotency_key: str = Field(..., min_length=1, description="Idempotency key to prevent duplicates")


class UsageRecord(UsageRecordBase):
    """Schema for returning usage record data."""

    id: UUID
    idempotency_key: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UsageRecordList(BaseModel):
    """Schema for paginated usage record list."""

    items: list[UsageRecord]
    total: int
    page: int
    page_size: int


class UsageAggregation(BaseModel):
    """Schema for aggregated usage data."""

    subscription_id: UUID
    metric: str
    total_quantity: int
    period_start: datetime
    period_end: datetime
