"""Payment model for payment transactions."""
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from billing.models.base import Base


class PaymentStatus(enum.Enum):
    """Payment transaction status."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Payment(Base):
    """
    Payment transaction for an invoice.

    Tracks Stripe payment intent and provides idempotency.
    """

    __tablename__ = "payments"

    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Amount in cents
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(SQLEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING, index=True)
    payment_gateway_transaction_id = Column(String, nullable=True, unique=True)  # Stripe payment intent ID
    payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id"), nullable=True)
    failure_message = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(String, nullable=True)  # ISO timestamp for next retry

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    payment_method = relationship("PaymentMethod", back_populates="payments")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Payment(id={self.id}, invoice_id={self.invoice_id}, status={self.status.value}, amount={self.amount})>"
