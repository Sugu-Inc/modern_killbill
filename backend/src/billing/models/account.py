"""Account model for customer billing management."""
from sqlalchemy import Column, String, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
import enum

from billing.models.base import Base


class AccountStatus(enum.Enum):
    """Account status for dunning process."""

    ACTIVE = "active"
    WARNING = "warning"
    BLOCKED = "blocked"


class Account(Base):
    """
    Customer account for billing.

    Represents a customer who can have subscriptions, invoices, and payments.
    """

    __tablename__ = "accounts"

    email = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")  # ISO 4217 currency code
    timezone = Column(String, nullable=False, default="UTC")
    tax_exempt = Column(Boolean, nullable=False, default=False)
    tax_id = Column(String, nullable=True)  # Tax ID for invoicing (e.g., VAT number)
    vat_id = Column(String, nullable=True)  # EU VAT ID for reverse charge
    status = Column(SQLEnum(AccountStatus), nullable=False, default=AccountStatus.ACTIVE)
    deleted_at = Column(String, nullable=True)  # Soft delete timestamp
    metadata = Column(JSONB, nullable=False, default=dict)  # Extensible custom fields

    # Relationships
    payment_methods = relationship("PaymentMethod", back_populates="account", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="account")
    invoices = relationship("Invoice", back_populates="account")
    credits = relationship("Credit", back_populates="account")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Account(id={self.id}, email={self.email}, status={self.status.value})>"
