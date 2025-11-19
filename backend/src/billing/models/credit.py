"""Credit model for account credits and refunds."""
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from billing.models.base import Base


class Credit(Base):
    """
    Account credit for discounts, refunds, or goodwill.

    Auto-applies to next invoice during generation.
    """

    __tablename__ = "credits"

    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Credit amount in cents
    currency = Column(String(3), nullable=False, default="USD")
    reason = Column(String, nullable=True)  # Refund, discount, goodwill, etc.
    applied_to_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True)

    # Relationships
    account = relationship("Account", back_populates="credits")
    applied_invoice = relationship("Invoice", foreign_keys=[applied_to_invoice_id], back_populates="applied_credits")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Credit(id={self.id}, account_id={self.account_id}, amount={self.amount}, applied={self.applied_to_invoice_id is not None})>"
