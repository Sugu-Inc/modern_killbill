"""Payment service for processing payments and retries."""
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from billing.models.payment import Payment, PaymentStatus
from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.account import Account, AccountStatus
from billing.models.payment_method import PaymentMethod
from billing.schemas.payment import PaymentCreate, PaymentRetryResponse


class PaymentService:
    """Service for payment processing and retry management."""

    def __init__(self, db: AsyncSession):
        """Initialize payment service."""
        self.db = db

    RETRY_SCHEDULE_DAYS = [3, 5, 7, 10]  # Retry on days 3, 5, 7, and 10

    async def list_payments(
        self,
        invoice_id: Optional[UUID] = None,
        status: Optional[PaymentStatus] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> List[Payment]:
        """
        List payments with optional filters.

        Args:
            invoice_id: Filter by invoice ID
            status: Filter by payment status
            page: Page number
            page_size: Results per page

        Returns:
            List of payments
        """
        query = select(Payment).options(selectinload(Payment.invoice))

        if invoice_id:
            query = query.where(Payment.invoice_id == invoice_id)
        if status:
            query = query.where(Payment.status == status)

        query = query.order_by(Payment.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_payment(self, payment_id: UUID) -> Optional[Payment]:
        """
        Get payment by ID.

        Args:
            payment_id: Payment UUID

        Returns:
            Payment if found, None otherwise
        """
        result = await self.db.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def attempt_payment(
        self,
        invoice_id: UUID,
        idempotency_key: Optional[str] = None,
        payment_method_id: Optional[UUID] = None,
    ) -> Payment:
        """
        Attempt payment for an invoice.

        Args:
            invoice_id: Invoice to pay
            idempotency_key: Key for duplicate prevention
            payment_method_id: Payment method to use

        Returns:
            Payment record

        Raises:
            ValueError: If invoice not found or already paid
        """
        # Check for existing payment with this idempotency key
        if idempotency_key:
            existing = await self.db.execute(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            existing_payment = existing.scalar_one_or_none()
            if existing_payment:
                return existing_payment

        # Get invoice
        invoice_result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.account))
            .where(Invoice.id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        if invoice.status == InvoiceStatus.PAID:
            raise ValueError(f"Invoice {invoice_id} is already paid")

        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = f"payment_{invoice_id}_{uuid4()}"

        # Create payment record
        payment = Payment(
            invoice_id=invoice_id,
            amount=invoice.amount_due,
            currency=invoice.currency,
            status=PaymentStatus.PENDING,
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
            retry_count=0,
        )

        self.db.add(payment)
        await self.db.flush()

        # Attempt to charge payment method
        try:
            # For testing purposes without Stripe integration, simulate payment
            # In real implementation, this would call Stripe API
            # For now, mark as PENDING and return
            # The actual charging happens through webhooks or background workers

            # If no payment method (testing mode), succeed immediately
            if not payment_method_id:
                payment.status = PaymentStatus.SUCCEEDED
                payment.gateway_transaction_id = f"test_{uuid4()}"
                invoice.status = InvoiceStatus.PAID
                invoice.paid_at = datetime.utcnow()
                invoice.amount_paid = invoice.amount_due

                # Emit webhook event for payment.succeeded
                await self.db.flush()
                await self._emit_webhook_event("payment.succeeded", payment)
            else:
                # Simulate successful payment for testing
                # In production, this would integrate with Stripe
                payment.status = PaymentStatus.PENDING

        except Exception as e:
            payment.status = PaymentStatus.FAILED
            payment.failure_message = str(e)
            await self._schedule_retry(payment)

        await self.db.flush()
        return payment

    async def mark_payment_succeeded(
        self,
        payment_id: UUID,
        gateway_transaction_id: str,
    ) -> Payment:
        """
        Mark payment as succeeded (called by webhook handler).

        Args:
            payment_id: Payment UUID
            gateway_transaction_id: Stripe transaction ID

        Returns:
            Updated payment

        Raises:
            ValueError: If payment not found
        """
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        payment.status = PaymentStatus.SUCCEEDED
        payment.payment_gateway_transaction_id = gateway_transaction_id

        # Update invoice status to PAID
        invoice_result = await self.db.execute(
            select(Invoice).where(Invoice.id == payment.invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if invoice:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.utcnow()

        await self.db.flush()

        # Emit webhook event for payment.succeeded (T120)
        await self._emit_webhook_event("payment.succeeded", payment)

        return payment

    async def mark_payment_failed(
        self,
        payment_id: UUID,
        failure_message: str,
    ) -> Payment:
        """
        Mark payment as failed and schedule retry.

        Args:
            payment_id: Payment UUID
            failure_message: Reason for failure

        Returns:
            Updated payment

        Raises:
            ValueError: If payment not found
        """
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        payment.status = PaymentStatus.FAILED
        payment.failure_message = failure_message
        payment.retry_count += 1

        await self._schedule_retry(payment)
        await self.db.flush()

        return payment

    async def _schedule_retry(self, payment: Payment) -> None:
        """
        Schedule next retry for failed payment.

        Args:
            payment: Payment to retry
        """
        if payment.retry_count < len(self.RETRY_SCHEDULE_DAYS):
            retry_day = self.RETRY_SCHEDULE_DAYS[payment.retry_count]
            next_retry = datetime.utcnow() + timedelta(days=retry_day)
            payment.next_retry_at = next_retry.isoformat()
        else:
            # All retries exhausted
            await self._mark_account_overdue(payment)

    async def _mark_account_overdue(self, payment: Payment) -> None:
        """
        Mark account as overdue after all retries exhausted.

        Args:
            payment: Failed payment
        """
        # Get invoice and account
        invoice_result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.account))
            .where(Invoice.id == payment.invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if invoice and invoice.account:
            invoice.account.status = AccountStatus.WARNING
            await self.db.flush()

    async def mark_retries_exhausted(self, payment_id: UUID) -> Payment:
        """
        Mark payment retries as exhausted and account as overdue.

        Args:
            payment_id: Payment UUID

        Returns:
            Updated payment

        Raises:
            ValueError: If payment not found
        """
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        payment.retry_count = len(self.RETRY_SCHEDULE_DAYS)
        payment.next_retry_at = None

        await self._mark_account_overdue(payment)
        await self.db.flush()

        return payment

    async def get_retry_schedule(self, payment_id: UUID) -> List[PaymentRetryResponse]:
        """
        Get retry schedule for a payment.

        Args:
            payment_id: Payment UUID

        Returns:
            List of retry schedule entries

        Raises:
            ValueError: If payment not found
        """
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        schedule = []
        base_time = payment.created_at

        for i, retry_day in enumerate(self.RETRY_SCHEDULE_DAYS):
            if i >= payment.retry_count:  # Only show future retries
                retry_time = base_time + timedelta(days=retry_day)
                schedule.append(
                    PaymentRetryResponse(
                        payment_id=payment_id,
                        retry_at=retry_time,
                        retry_count=i + 1,
                        max_retries=len(self.RETRY_SCHEDULE_DAYS),
                    )
                )

        return schedule

    async def retry_payment(self, payment_id: UUID) -> Payment:
        """
        Manually retry a failed payment.

        Args:
            payment_id: Payment UUID

        Returns:
            Updated payment

        Raises:
            ValueError: If payment not found or not in failed status
        """
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.FAILED:
            raise ValueError(f"Payment {payment_id} is not in FAILED status")

        # Reset status and attempt again
        payment.status = PaymentStatus.PENDING
        payment.retry_count += 1

        # In production, this would call Stripe API
        # For testing, just mark as pending
        await self.db.flush()

        return payment

    async def _emit_webhook_event(self, event_type: str, payment: "Payment") -> None:
        """
        Emit webhook event for payment state changes.

        Args:
            event_type: Event type (e.g., "payment.succeeded", "payment.failed")
            payment: Payment object
        """
        try:
            from billing.services.webhook_service import WebhookService
            from billing.api.v1.webhook_endpoints import get_endpoints_for_event
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            from billing.models.invoice import Invoice

            webhook_service = WebhookService(self.db)

            # Load invoice to get account_id
            account_id = None
            if payment.invoice_id:
                invoice_result = await self.db.execute(
                    select(Invoice).where(Invoice.id == payment.invoice_id)
                )
                invoice = invoice_result.scalar_one_or_none()
                if invoice:
                    account_id = str(invoice.account_id)

            # Create webhook payload
            payload = {
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id) if payment.invoice_id else None,
                "account_id": account_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "status": payment.status.value,
                "payment_method_id": str(payment.payment_method_id) if payment.payment_method_id else None,
            }

            # Get webhook endpoints subscribed to this event
            endpoints = get_endpoints_for_event(event_type)

            # Create webhook event for each subscribed endpoint, or one with "system" endpoint if none
            if not endpoints:
                # Create event with system endpoint for audit trail
                await webhook_service.create_event(
                    event_type=event_type,
                    payload=payload,
                    endpoint_url="system",
                )
            else:
                # Create webhook event for each subscribed endpoint
                for endpoint_url in endpoints:
                    await webhook_service.create_event(
                        event_type=event_type,
                        payload=payload,
                        endpoint_url=endpoint_url,
                    )

        except Exception:
            # Don't let webhook failures break payment operations
            pass
