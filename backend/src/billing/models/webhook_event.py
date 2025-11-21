"""Webhook event model for event delivery tracking."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Enum as SQLEnum, DateTime
from sqlalchemy.dialects.postgresql import JSONB
import enum

from billing.models.base import Base


class WebhookStatus(enum.Enum):
    """Webhook delivery status."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


# Alias for test compatibility
WebhookEventStatus = WebhookStatus


class WebhookEvent(Base):
    """
    Webhook event for customer integrations.

    Tracks event delivery with retry logic.
    """

    __tablename__ = "webhook_events"

    event_type = Column(String, nullable=False, index=True)  # invoice.created, payment.succeeded, etc.
    payload = Column(JSONB, nullable=False)  # Full event payload
    endpoint_url = Column(String, nullable=False)
    status = Column(SQLEnum(WebhookStatus), nullable=False, default=WebhookStatus.PENDING, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    delivered_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        """String representation."""
        return f"<WebhookEvent(id={self.id}, event_type={self.event_type}, status={self.status.value}, retries={self.retry_count})>"
