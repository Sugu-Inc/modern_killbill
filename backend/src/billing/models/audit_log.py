"""Audit log model for tracking all changes."""
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID, JSONB

from billing.models.base import Base


class AuditLog(Base):
    """
    Audit log for compliance and security.

    Tracks all create/update/delete operations with user context.
    """

    __tablename__ = "audit_logs"

    entity_type = Column(String, nullable=False, index=True)  # account, subscription, invoice, payment
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    action = Column(String, nullable=False)  # create, update, delete
    user_id = Column(String, nullable=True)  # User who performed action
    changes = Column(JSONB, nullable=False, default=dict)  # {field: {old: X, new: Y}}
    request_id = Column(String, nullable=True)  # Correlation ID from request

    def __repr__(self) -> str:
        """String representation."""
        return f"<AuditLog(entity_type={self.entity_type}, entity_id={self.entity_id}, action={self.action})>"
