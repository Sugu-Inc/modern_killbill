"""Invoice model for billing invoices."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from billing.models.base import Base


class InvoiceStatus(enum.Enum):
    """Invoice lifecycle status."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    PAST_DUE = "past_due"


class Invoice(Base):
    """
    Billing invoice for subscriptions.

    Immutable after PAID status. Contains line items, tax, and payment tracking.
    """

    __tablename__ = "invoices"

    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True, index=True)
    number = Column(String, nullable=False, unique=True, index=True)  # INV-0001, INV-0002, etc.
    status = Column(SQLEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT, index=True)
    amount_due = Column(Integer, nullable=False)  # Total amount in cents
    amount_paid = Column(Integer, nullable=False, default=0)  # Amount paid in cents
    tax = Column(Integer, nullable=False, default=0)  # Tax amount in cents
    currency = Column(String(3), nullable=False, default="USD")
    due_date = Column(DateTime, nullable=False, index=True)
    paid_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    line_items = Column(JSONB, nullable=False, default=list)  # [{description, amount, quantity, type}]
    extra_metadata = Column(JSONB, nullable=False, default=dict)

    # Relationships
    account = relationship("Account", back_populates="invoices")
    subscription = relationship("Subscription", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")
    applied_credits = relationship("Credit", foreign_keys="Credit.applied_to_invoice_id", back_populates="applied_invoice")

    @property
    def subtotal(self) -> int:
        """Calculate subtotal (total before tax) from line items."""
        if isinstance(self.line_items, list):
            return sum(item.get("amount", 0) * item.get("quantity", 1) for item in self.line_items)
        return 0

    @property
    def total(self) -> int:
        """Calculate total (subtotal + tax)."""
        return self.subtotal + self.tax

    def __repr__(self) -> str:
        """String representation."""
        return f"<Invoice(id={self.id}, number={self.number}, status={self.status.value}, amount_due={self.amount_due})>"
