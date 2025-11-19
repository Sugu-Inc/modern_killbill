"""Payment method model for storing customer payment information."""
from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from billing.models.base import Base


class PaymentMethod(Base):
    """
    Customer payment method (credit card, bank account, etc.).

    Stores reference to payment gateway (Stripe) payment method ID.
    """

    __tablename__ = "payment_methods"

    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    gateway_payment_method_id = Column(String, nullable=False, unique=True)  # Stripe PM ID
    type = Column(String, nullable=False)  # card, bank_account, etc.
    card_last4 = Column(String(4), nullable=True)
    card_brand = Column(String, nullable=True)  # visa, mastercard, amex
    card_exp_month = Column(String(2), nullable=True)
    card_exp_year = Column(String(4), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)

    # Relationships
    account = relationship("Account", back_populates="payment_methods")
    payments = relationship("Payment", back_populates="payment_method")

    def __repr__(self) -> str:
        """String representation."""
        return f"<PaymentMethod(id={self.id}, type={self.type}, last4={self.card_last4})>"
