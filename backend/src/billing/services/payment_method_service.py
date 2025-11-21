"""Payment method service for business logic."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.adapters.stripe_adapter import StripeAdapter
from billing.models.payment_method import PaymentMethod
from billing.schemas.payment_method import PaymentMethodCreate


class PaymentMethodService:
    """Service layer for payment method operations."""

    def __init__(self, db: AsyncSession, stripe_adapter: StripeAdapter):
        """Initialize payment method service."""
        self.db = db
        self.stripe = stripe_adapter

    async def create_payment_method(
        self, account_id: UUID, stripe_customer_id: str, payment_data: PaymentMethodCreate
    ) -> PaymentMethod:
        """
        Create and attach a payment method.

        Args:
            account_id: Account UUID
            stripe_customer_id: Stripe customer ID
            payment_data: Payment method creation data

        Returns:
            Created payment method
        """
        # Attach payment method to Stripe customer
        stripe_pm = await self.stripe.attach_payment_method(
            customer_id=stripe_customer_id,
            payment_method_id=payment_data.stripe_payment_method_id,
            set_default=payment_data.is_default,
        )

        # If setting as default, unset other payment methods
        if payment_data.is_default:
            await self.db.execute(
                select(PaymentMethod)
                .where(PaymentMethod.account_id == account_id)
                .update({"is_default": False})
            )

        # Create payment method record
        payment_method = PaymentMethod(
            account_id=account_id,
            stripe_payment_method_id=payment_data.stripe_payment_method_id,
            type=stripe_pm["type"],
            last4=stripe_pm["card"]["last4"] if stripe_pm["card"] else None,
            exp_month=stripe_pm["card"]["exp_month"] if stripe_pm["card"] else None,
            exp_year=stripe_pm["card"]["exp_year"] if stripe_pm["card"] else None,
            is_default=payment_data.is_default,
        )

        self.db.add(payment_method)
        await self.db.flush()
        await self.db.refresh(payment_method)

        return payment_method

    async def get_payment_method(self, payment_method_id: UUID) -> PaymentMethod | None:
        """
        Get payment method by ID.

        Args:
            payment_method_id: Payment method UUID

        Returns:
            Payment method or None
        """
        result = await self.db.execute(
            select(PaymentMethod).where(PaymentMethod.id == payment_method_id)
        )
        return result.scalar_one_or_none()

    async def list_payment_methods(self, account_id: UUID) -> list[PaymentMethod]:
        """
        List all payment methods for an account.

        Args:
            account_id: Account UUID

        Returns:
            List of payment methods
        """
        result = await self.db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.account_id == account_id)
            .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
        )
        return list(result.scalars().all())

    async def set_default_payment_method(
        self, account_id: UUID, payment_method_id: UUID
    ) -> PaymentMethod:
        """
        Set payment method as default.

        Args:
            account_id: Account UUID
            payment_method_id: Payment method UUID

        Returns:
            Updated payment method

        Raises:
            ValueError: If payment method not found or doesn't belong to account
        """
        payment_method = await self.get_payment_method(payment_method_id)
        if not payment_method:
            raise ValueError(f"Payment method {payment_method_id} not found")

        if payment_method.account_id != account_id:
            raise ValueError("Payment method does not belong to this account")

        # Unset other payment methods as default
        await self.db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.account_id == account_id)
            .update({"is_default": False})
        )

        # Set this one as default
        payment_method.is_default = True
        await self.db.flush()
        await self.db.refresh(payment_method)

        return payment_method

    async def delete_payment_method(self, payment_method_id: UUID) -> None:
        """
        Delete payment method.

        Args:
            payment_method_id: Payment method UUID

        Raises:
            ValueError: If payment method not found or is the default
        """
        payment_method = await self.get_payment_method(payment_method_id)
        if not payment_method:
            raise ValueError(f"Payment method {payment_method_id} not found")

        if payment_method.is_default:
            raise ValueError("Cannot delete default payment method. Set another as default first.")

        # Detach from Stripe
        await self.stripe.detach_payment_method(payment_method.stripe_payment_method_id)

        # Delete from database
        await self.db.delete(payment_method)
        await self.db.flush()

    async def get_default_payment_method(self, account_id: UUID) -> PaymentMethod | None:
        """
        Get default payment method for account.

        Args:
            account_id: Account UUID

        Returns:
            Default payment method or None
        """
        result = await self.db.execute(
            select(PaymentMethod).where(
                PaymentMethod.account_id == account_id, PaymentMethod.is_default == True  # noqa: E712
            )
        )
        return result.scalar_one_or_none()
