"""Pydantic schemas for AuditLog model."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class AuditLogBase(BaseModel):
    """Base audit log schema with common fields."""

    action: str = Field(..., min_length=1, description="Action performed (create, update, delete)")
    entity_type: str = Field(..., min_length=1, description="Type of entity (account, invoice, etc.)")
    entity_id: UUID = Field(..., description="ID of the entity")
    changes: dict[str, Any] = Field(..., description="Changes made to the entity")


class AuditLogCreate(AuditLogBase):
    """Schema for creating a new audit log entry."""

    user_id: UUID | None = Field(default=None, description="User who performed the action")
    ip_address: str | None = Field(default=None, description="IP address of the request")
    user_agent: str | None = Field(default=None, description="User agent of the request")


class AuditLog(AuditLogBase):
    """Schema for returning audit log data."""

    id: UUID
    user_id: UUID | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogList(BaseModel):
    """Schema for paginated audit log list."""

    items: list[AuditLog]
    total: int
    page: int
    page_size: int
