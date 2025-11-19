"""Pydantic schemas for Payment model."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from billing.models.payment import PaymentStatus


class PaymentBase(BaseModel):
    """Base payment schema with common fields."""

    invoice_id: UUID = Field(..., description="Invoice ID this payment is for")
    amount: int = Field(..., gt=0, description="Payment amount in cents")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 currency code")


class PaymentCreate(PaymentBase):
    """Schema for creating a new payment."""

    payment_method_id: UUID | None = Field(default=None, description="Payment method to use (or default)")
    idempotency_key: str = Field(..., min_length=1, description="Idempotency key to prevent duplicate payments")


class PaymentRetry(BaseModel):
    """Schema for retrying a failed payment."""

    payment_method_id: UUID | None = Field(default=None, description="New payment method to use (optional)")


class Payment(PaymentBase):
    """Schema for returning payment data."""

    id: UUID
    status: PaymentStatus
    payment_gateway_transaction_id: str | None
    payment_method_id: UUID | None
    failure_message: str | None
    idempotency_key: str
    retry_count: int
    next_retry_at: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentList(BaseModel):
    """Schema for paginated payment list."""

    items: list[Payment]
    total: int
    page: int
    page_size: int
