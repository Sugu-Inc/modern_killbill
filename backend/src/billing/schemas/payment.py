"""Pydantic schemas for payment entities."""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List

from billing.models.payment import PaymentStatus


class PaymentResponse(BaseModel):
    """Schema for payment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    amount: int = Field(..., description="Amount in cents")
    currency: str
    status: PaymentStatus
    payment_gateway_transaction_id: Optional[str] = Field(None, description="Stripe payment intent ID")
    payment_method_id: Optional[UUID] = None
    failure_message: Optional[str] = None
    idempotency_key: str
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PaymentCreate(BaseModel):
    """Schema for creating a payment."""

    invoice_id: UUID
    amount: int = Field(..., description="Amount in cents", gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    payment_method_id: Optional[UUID] = None
    idempotency_key: str = Field(..., description="Idempotency key for duplicate prevention")


class PaymentRetryResponse(BaseModel):
    """Schema for payment retry schedule response."""

    payment_id: UUID
    retry_at: datetime
    retry_count: int
    max_retries: int = 4  # Days 3, 5, 7, 10


# Alias for backward compatibility
Payment = PaymentResponse

class PaymentList(BaseModel):
    """Schema for paginated list of payments."""

    items: List[PaymentResponse]
    total: int
    page: int
    page_size: int


class PaymentRetry(BaseModel):
    """Schema for payment retry information."""

    payment_id: UUID
    retry_at: Optional[datetime] = None
    max_retries: int = 4

