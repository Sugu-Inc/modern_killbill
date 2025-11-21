"""Pydantic schemas for Invoice model."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from billing.models.invoice import InvoiceStatus


class InvoiceLineItem(BaseModel):
    """Schema for invoice line item."""

    description: str = Field(..., min_length=1, description="Line item description")
    amount: int = Field(..., description="Amount in cents")
    quantity: int = Field(default=1, ge=1, description="Quantity")
    type: str = Field(default="subscription", description="Line item type (subscription, usage, credit, etc.)")


class InvoiceBase(BaseModel):
    """Base invoice schema with common fields."""

    account_id: UUID = Field(..., description="Account ID this invoice belongs to")
    subscription_id: UUID | None = Field(default=None, description="Subscription ID (if applicable)")
    amount_due: int = Field(..., ge=0, description="Total amount due in cents")
    tax: int = Field(default=0, ge=0, description="Tax amount in cents")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 currency code")
    due_date: datetime = Field(..., description="Payment due date")
    line_items: list[InvoiceLineItem] = Field(default_factory=list, description="Invoice line items")
    extra_metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible custom fields")


class InvoiceCreate(InvoiceBase):
    """Schema for creating a new invoice."""

    pass


class InvoiceVoid(BaseModel):
    """Schema for voiding an invoice."""

    reason: str = Field(..., min_length=1, description="Reason for voiding invoice")


class Invoice(InvoiceBase):
    """Schema for returning invoice data."""

    id: UUID
    number: str
    status: InvoiceStatus
    amount_paid: int
    paid_at: datetime | None
    voided_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceWithPayments(Invoice):
    """Schema for invoice with embedded payment data."""

    payments: list["Payment"]  # Forward reference

    model_config = ConfigDict(from_attributes=True)


class InvoiceList(BaseModel):
    """Schema for paginated invoice list."""

    items: list[Invoice]
    total: int
    page: int
    page_size: int


# Import Payment at the end to avoid circular imports
from billing.schemas.payment import Payment  # noqa: E402

InvoiceWithPayments.model_rebuild()
