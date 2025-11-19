"""Pydantic schemas for Account model."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from billing.models.account import AccountStatus


class AccountBase(BaseModel):
    """Base account schema with common fields."""

    email: EmailStr = Field(..., description="Customer email address")
    name: str = Field(..., min_length=1, max_length=255, description="Customer or company name")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 currency code")
    timezone: str = Field(default="UTC", description="IANA timezone identifier")
    tax_exempt: bool = Field(default=False, description="Whether customer is exempt from tax")
    tax_id: str | None = Field(default=None, description="Tax ID for invoicing")
    vat_id: str | None = Field(default=None, description="EU VAT ID for reverse charge")
    extra_metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible custom fields")


class AccountCreate(AccountBase):
    """Schema for creating a new account."""

    pass


class AccountUpdate(BaseModel):
    """Schema for updating an account (all fields optional)."""

    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = None
    tax_exempt: bool | None = None
    tax_id: str | None = None
    vat_id: str | None = None
    extra_metadata: dict[str, Any] | None = None


class Account(AccountBase):
    """Schema for returning account data."""

    id: UUID
    status: AccountStatus
    deleted_at: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountList(BaseModel):
    """Schema for paginated account list."""

    items: list[Account]
    total: int
    page: int
    page_size: int
