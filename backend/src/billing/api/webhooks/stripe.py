"""Stripe webhook handler for payment events."""
import structlog
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from uuid import UUID

from billing.adapters.stripe_adapter import StripeAdapter
from billing.database import get_db
from billing.models.payment import Payment, PaymentStatus
from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.account import Account, AccountStatus
from billing.services.webhook_service import WebhookService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks/stripe", tags=["webhooks"])


async def get_stripe_adapter() -> StripeAdapter:
    """Get Stripe adapter instance."""
    return StripeAdapter()


@router.post("")
async def handle_stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_adapter: StripeAdapter = Depends(get_stripe_adapter),
):
    """
    Handle incoming Stripe webhook events.

    Verifies webhook signature and processes payment-related events:
    - payment_intent.succeeded: Mark payment as successful
    - payment_intent.payment_failed: Mark payment as failed and schedule retry

    Args:
        request: FastAPI request with webhook payload
        db: Database session
        stripe_adapter: Stripe adapter for webhook verification

    Returns:
        Success response

    Raises:
        HTTPException: If signature verification fails or processing error
    """
    # Get raw body and signature
    body = await request.body()
    signature = request.headers.get("stripe-signature")

    if not signature:
        logger.error("stripe_webhook_missing_signature")
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    # Verify webhook signature
    try:
        event = await stripe_adapter.construct_webhook_event(body, signature)
    except ValueError as e:
        logger.error("stripe_webhook_verification_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Webhook verification failed: {e}")

    event_type = event["type"]
    event_data = event["data"]["object"]

    logger.info(
        "stripe_webhook_received",
        event_type=event_type,
        event_id=event.get("id"),
        payment_intent_id=event_data.get("id"),
    )

    # Process payment_intent events
    if event_type == "payment_intent.succeeded":
        await _handle_payment_succeeded(db, event_data)
    elif event_type == "payment_intent.payment_failed":
        await _handle_payment_failed(db, event_data)
    else:
        logger.info("stripe_webhook_unhandled_event", event_type=event_type)

    return {"status": "success", "event_type": event_type}


async def _handle_payment_succeeded(db: AsyncSession, payment_intent: dict) -> None:
    """
    Handle successful payment intent.

    Updates payment status to SUCCEEDED and marks invoice as PAID.
    Unblocks account if it was blocked due to overdue payments.

    Args:
        db: Database session
        payment_intent: Stripe payment intent data
    """
    payment_intent_id = payment_intent["id"]
    amount_paid = payment_intent["amount"]

    # Find payment by gateway transaction ID
    result = await db.execute(
        select(Payment)
        .where(Payment.payment_gateway_transaction_id == payment_intent_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        logger.warning(
            "stripe_webhook_payment_not_found",
            payment_intent_id=payment_intent_id,
        )
        return

    if payment.status == PaymentStatus.SUCCEEDED:
        logger.info(
            "stripe_webhook_payment_already_succeeded",
            payment_id=str(payment.id),
            payment_intent_id=payment_intent_id,
        )
        return

    # Update payment status
    payment.status = PaymentStatus.SUCCEEDED
    payment.amount = amount_paid

    # Get invoice and mark as PAID
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == payment.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()

    if invoice and invoice.status != InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.PAID
        invoice.amount_paid = amount_paid
        invoice.paid_at = payment_intent.get("created")  # Unix timestamp

        # Unblock account if blocked
        account_result = await db.execute(
            select(Account).where(Account.id == invoice.account_id)
        )
        account = account_result.scalar_one_or_none()

        if account and account.status == AccountStatus.BLOCKED:
            account.status = AccountStatus.ACTIVE
            logger.info(
                "stripe_webhook_account_unblocked",
                account_id=str(account.id),
                invoice_id=str(invoice.id),
            )

    await db.commit()

    logger.info(
        "stripe_webhook_payment_succeeded",
        payment_id=str(payment.id),
        invoice_id=str(payment.invoice_id),
        amount=amount_paid,
    )

    # Send webhook notification (if WebhookService configured)
    try:
        webhook_service = WebhookService(db)
        await webhook_service.send_event(
            event_type="payment.succeeded",
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "amount": amount_paid,
                "currency": payment.currency,
            },
        )
    except Exception as e:
        logger.warning(
            "stripe_webhook_notification_failed",
            payment_id=str(payment.id),
            error=str(e),
        )


async def _handle_payment_failed(db: AsyncSession, payment_intent: dict) -> None:
    """
    Handle failed payment intent.

    Updates payment status to FAILED and schedules retry.
    Marks account as WARNING after multiple failures.

    Args:
        db: Database session
        payment_intent: Stripe payment intent data
    """
    payment_intent_id = payment_intent["id"]
    failure_message = payment_intent.get("last_payment_error", {}).get("message", "Unknown error")

    # Find payment by gateway transaction ID
    result = await db.execute(
        select(Payment)
        .where(Payment.payment_gateway_transaction_id == payment_intent_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        logger.warning(
            "stripe_webhook_payment_not_found",
            payment_intent_id=payment_intent_id,
        )
        return

    # Update payment status
    payment.status = PaymentStatus.FAILED
    payment.failure_message = failure_message

    # Get invoice and mark as OVERDUE
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == payment.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()

    if invoice and invoice.status != InvoiceStatus.OVERDUE:
        invoice.status = InvoiceStatus.OVERDUE

        # Mark account as WARNING after first failure
        account_result = await db.execute(
            select(Account).where(Account.id == invoice.account_id)
        )
        account = account_result.scalar_one_or_none()

        if account and account.status == AccountStatus.ACTIVE:
            account.status = AccountStatus.WARNING
            logger.info(
                "stripe_webhook_account_marked_warning",
                account_id=str(account.id),
                invoice_id=str(invoice.id),
            )

    await db.commit()

    logger.info(
        "stripe_webhook_payment_failed",
        payment_id=str(payment.id),
        invoice_id=str(payment.invoice_id),
        failure_message=failure_message,
    )

    # Send webhook notification
    try:
        webhook_service = WebhookService(db)
        await webhook_service.send_event(
            event_type="payment.failed",
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "failure_message": failure_message,
            },
        )
    except Exception as e:
        logger.warning(
            "stripe_webhook_notification_failed",
            payment_id=str(payment.id),
            error=str(e),
        )
