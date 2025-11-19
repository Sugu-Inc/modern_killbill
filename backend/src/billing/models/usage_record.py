"""Usage record model for usage-based billing."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from billing.models.base import Base


class UsageRecord(Base):
    """
    Usage event for usage-based billing.

    Tracks metered usage (API calls, storage, bandwidth) with idempotency.
    """

    __tablename__ = "usage_records"

    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    metric = Column(String, nullable=False, index=True)  # api_calls, storage_gb, bandwidth_gb
    quantity = Column(Integer, nullable=False)  # Number of units consumed
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)  # Prevents duplicates
    metadata = Column(JSONB, nullable=False, default=dict)

    # Relationships
    subscription = relationship("Subscription", back_populates="usage_records")

    def __repr__(self) -> str:
        """String representation."""
        return f"<UsageRecord(id={self.id}, subscription_id={self.subscription_id}, metric={self.metric}, quantity={self.quantity})>"
