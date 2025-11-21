"""Plan model for pricing plans and subscription products."""
from sqlalchemy import Column, String, Integer, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum

from billing.models.base import Base


class PlanInterval(enum.Enum):
    """Billing interval for plans."""

    MONTH = "month"
    YEAR = "year"


class UsageType(enum.Enum):
    """Usage billing type."""

    LICENSED = "licensed"  # Flat-rate per-seat licensing
    METERED = "metered"  # Usage-based metered billing
    TIERED = "tiered"  # Tiered pricing
    VOLUME = "volume"  # Volume-based pricing
    GRADUATED = "graduated"  # Graduated pricing


class Plan(Base):
    """
    Pricing plan for subscriptions.

    Supports recurring billing (monthly/annual) and usage-based pricing.
    """

    __tablename__ = "plans"

    name = Column(String, nullable=False)
    interval = Column(SQLEnum(PlanInterval), nullable=False)
    amount = Column(Integer, nullable=False)  # Amount in cents
    currency = Column(String(3), nullable=False, default="USD")
    trial_days = Column(Integer, nullable=False, default=0)
    usage_type = Column(SQLEnum(UsageType), nullable=True)  # NULL for flat-rate plans
    tiers = Column(JSONB, nullable=True)  # Usage tier configuration [{up_to, unit_amount}]
    active = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    extra_metadata = Column(JSONB, nullable=False, default=dict)

    # Relationships
    subscriptions = relationship("Subscription", foreign_keys="Subscription.plan_id", back_populates="plan")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Plan(id={self.id}, name={self.name}, interval={self.interval.value}, amount={self.amount})>"
