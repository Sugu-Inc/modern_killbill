"""Pydantic schemas for Subscription model."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from billing.models.subscription import SubscriptionStatus


class SubscriptionBase(BaseModel):
    """Base subscription schema with common fields."""

    account_id: UUID = Field(..., description="Account ID this subscription belongs to")
    plan_id: UUID = Field(..., description="Plan ID for this subscription")
    quantity: int = Field(default=1, ge=1, description="Number of seats/licenses")


class SubscriptionCreate(SubscriptionBase):
    """Schema for creating a new subscription."""

    trial_end: datetime | None = Field(default=None, description="Trial end date (overrides plan trial_days)")


class SubscriptionUpdate(BaseModel):
    """Schema for updating a subscription."""

    quantity: int | None = Field(default=None, ge=1, description="Update quantity")
    cancel_at_period_end: bool | None = Field(default=None, description="Cancel at end of current period")


class SubscriptionPlanChange(BaseModel):
    """Schema for scheduling a plan change."""

    new_plan_id: UUID = Field(..., description="New plan to switch to")
    immediate: bool = Field(default=False, description="Apply change immediately or at period end")


class SubscriptionPause(BaseModel):
    """Schema for pausing a subscription."""

    resumes_at: datetime | None = Field(default=None, description="Auto-resume date (None for indefinite)")


class Subscription(SubscriptionBase):
    """Schema for returning subscription data."""

    id: UUID
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None
    trial_end: datetime | None
    pause_resumes_at: datetime | None
    pending_plan_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionWithPlan(Subscription):
    """Schema for subscription with embedded plan data."""

    plan: "Plan"  # Forward reference

    model_config = ConfigDict(from_attributes=True)


class SubscriptionList(BaseModel):
    """Schema for paginated subscription list."""

    items: list[Subscription]
    total: int
    page: int
    page_size: int


# Import Plan at the end to avoid circular imports
from billing.schemas.plan import Plan  # noqa: E402

SubscriptionWithPlan.model_rebuild()
