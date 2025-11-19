"""Pydantic schemas for Credit model."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class CreditBase(BaseModel):
    """Base credit schema with common fields."""

    account_id: UUID = Field(..., description="Account ID this credit belongs to")
    amount: int = Field(..., gt=0, description="Credit amount in cents")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 currency code")
    reason: str = Field(..., min_length=1, description="Reason for credit")


class CreditCreate(CreditBase):
    """Schema for creating a new credit."""

    expires_at: datetime | None = Field(default=None, description="Credit expiration date (None for no expiration)")


class Credit(CreditBase):
    """Schema for returning credit data."""

    id: UUID
    expires_at: datetime | None
    applied_to_invoice_id: UUID | None
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreditList(BaseModel):
    """Schema for paginated credit list."""

    items: list[Credit]
    total: int
    page: int
    page_size: int


class CreditBalance(BaseModel):
    """Schema for account credit balance."""

    account_id: UUID
    total_credits: int
    currency: str
    available_credits: int  # Excludes expired/applied credits
    expired_credits: int
    applied_credits: int
