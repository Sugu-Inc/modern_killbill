"""Pydantic schemas for PaymentMethod model."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class PaymentMethodBase(BaseModel):
    """Base payment method schema with common fields."""

    account_id: UUID = Field(..., description="Account ID this payment method belongs to")
    stripe_payment_method_id: str = Field(..., min_length=1, description="Stripe payment method ID")


class PaymentMethodCreate(PaymentMethodBase):
    """Schema for creating a new payment method."""

    is_default: bool = Field(default=False, description="Set as default payment method")


class PaymentMethodUpdate(BaseModel):
    """Schema for updating a payment method."""

    is_default: bool = Field(..., description="Set as default payment method")


class PaymentMethod(PaymentMethodBase):
    """Schema for returning payment method data."""

    id: UUID
    type: str  # card, us_bank_account, etc.
    last4: str | None
    exp_month: int | None
    exp_year: int | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentMethodList(BaseModel):
    """Schema for paginated payment method list."""

    items: list[PaymentMethod]
    total: int
    page: int
    page_size: int
