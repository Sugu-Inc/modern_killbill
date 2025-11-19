"""Pydantic schemas for Plan model."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator

from billing.models.plan import PlanInterval, UsageType


class UsageTier(BaseModel):
    """Schema for usage billing tier."""

    up_to: int | None = Field(..., description="Upper bound for this tier (None for last tier)")
    unit_amount: int = Field(..., ge=0, description="Price per unit in this tier (in cents)")


class PlanBase(BaseModel):
    """Base plan schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Plan name")
    interval: PlanInterval = Field(..., description="Billing interval (month or year)")
    amount: int = Field(..., ge=0, description="Price in cents")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 currency code")
    trial_days: int = Field(default=0, ge=0, description="Number of trial days")
    usage_type: UsageType | None = Field(default=None, description="Usage billing type (None for flat-rate)")
    tiers: list[UsageTier] | None = Field(default=None, description="Usage tier configuration")
    active: bool = Field(default=True, description="Whether plan is available for new subscriptions")
    extra_metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible custom fields")

    @field_validator("tiers")
    @classmethod
    def validate_tiers(cls, v: list[UsageTier] | None, info) -> list[UsageTier] | None:
        """Validate that tiers are provided only for usage-based plans."""
        usage_type = info.data.get("usage_type")
        if usage_type is not None and v is None:
            raise ValueError("tiers must be provided for usage-based plans")
        if usage_type is None and v is not None:
            raise ValueError("tiers should not be provided for flat-rate plans")
        return v


class PlanCreate(PlanBase):
    """Schema for creating a new plan."""

    pass


class PlanUpdate(BaseModel):
    """Schema for updating a plan (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None
    extra_metadata: dict[str, Any] | None = None


class Plan(PlanBase):
    """Schema for returning plan data."""

    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlanList(BaseModel):
    """Schema for paginated plan list."""

    items: list[Plan]
    total: int
    page: int
    page_size: int


# Backward compatibility alias
PlanTier = UsageTier
