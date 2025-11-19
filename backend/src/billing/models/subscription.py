"""Subscription model for customer subscriptions to plans."""
from datetime import datetime
from sqlalchemy import Column, Integer, Boolean, Enum as SQLEnum, ForeignKey, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from billing.models.base import Base


class SubscriptionStatus(enum.Enum):
    """Subscription lifecycle status."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class Subscription(Base):
    """
    Customer subscription to a pricing plan.

    Handles billing cycles, trial periods, cancellations, and pausing.
    """

    __tablename__ = "subscriptions"

    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False, index=True)
    status = Column(SQLEnum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ACTIVE, index=True)
    quantity = Column(Integer, nullable=False, default=1)  # Per-seat billing
    current_period_start = Column(DateTime, nullable=False, default=datetime.utcnow)
    current_period_end = Column(DateTime, nullable=False, index=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    cancelled_at = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    pause_resumes_at = Column(DateTime, nullable=True)  # Auto-resume date for paused subscriptions
    pending_plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True)  # For scheduled plan changes

    # Relationships
    account = relationship("Account", back_populates="subscriptions")
    plan = relationship("Plan", foreign_keys=[plan_id], back_populates="subscriptions")
    pending_plan = relationship("Plan", foreign_keys=[pending_plan_id])
    invoices = relationship("Invoice", back_populates="subscription")
    usage_records = relationship("UsageRecord", back_populates="subscription")
    history = relationship("SubscriptionHistory", back_populates="subscription", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Subscription(id={self.id}, account_id={self.account_id}, status={self.status.value})>"


class SubscriptionHistory(Base):
    """
    Audit trail for subscription changes.

    Tracks status changes, plan changes, and quantity changes.
    """

    __tablename__ = "subscription_history"

    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False)  # status_change, plan_change, quantity_change
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=False)
    reason = Column(String, nullable=True)

    # Relationships
    subscription = relationship("Subscription", back_populates="history")

    def __repr__(self) -> str:
        """String representation."""
        return f"<SubscriptionHistory(subscription_id={self.subscription_id}, event={self.event_type})>"
