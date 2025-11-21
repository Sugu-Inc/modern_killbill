"""Payment retry worker for handling failed payment retries.

This worker runs periodically to:
1. Check for failed payments that need retry
2. Attempt payment according to retry schedule (days 3, 5, 7, 10)
3. Mark accounts as overdue after all retries failed
"""
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.database import AsyncSessionLocal
from billing.models.payment import Payment, PaymentStatus
from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.account import Account, AccountStatus
from billing.services.payment_service import PaymentService

logger = structlog.get_logger(__name__)


async def process_payment_retries() -> dict[str, int]:
    """
    Process payment retries for failed payments.

    Checks for payments that are due for retry based on the retry schedule:
    - Day 3: First retry
    - Day 5: Second retry
    - Day 7: Third retry
    - Day 10: Final retry

    If all retries fail, mark account as OVERDUE and invoice as OVERDUE.

    Returns:
        Dict with counts of processed retries
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find payments due for retry
            payments_to_retry = await _find_payments_due_for_retry(db)

            logger.info(
                "payment_retry_started",
                payments_count=len(payments_to_retry),
            )

            retries_attempted = 0
            retries_succeeded = 0
            retries_failed = 0
            accounts_marked_overdue = 0
            errors = 0

            payment_service = PaymentService(db)

            for payment in payments_to_retry:
                try:
                    # Attempt retry
                    result = await payment_service.retry_payment(payment_id=payment.id)

                    retries_attempted += 1

                    if result.status == PaymentStatus.SUCCEEDED:
                        retries_succeeded += 1
                        logger.info(
                            "payment_retry_succeeded",
                            payment_id=str(payment.id),
                            invoice_id=str(payment.invoice_id),
                            retry_count=result.retry_count,
                        )
                    else:
                        retries_failed += 1

                        # Check if this was the final retry
                        if result.retry_count >= len(PaymentService.RETRY_SCHEDULE_DAYS):
                            # Mark account as overdue
                            await _mark_account_overdue(db, payment)
                            accounts_marked_overdue += 1

                        logger.warning(
                            "payment_retry_failed",
                            payment_id=str(payment.id),
                            invoice_id=str(payment.invoice_id),
                            retry_count=result.retry_count,
                            failure_message=result.failure_message,
                        )

                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "payment_retry_error",
                        payment_id=str(payment.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "payment_retry_completed",
                retries_attempted=retries_attempted,
                retries_succeeded=retries_succeeded,
                retries_failed=retries_failed,
                accounts_marked_overdue=accounts_marked_overdue,
                errors=errors,
            )

            return {
                "retries_attempted": retries_attempted,
                "retries_succeeded": retries_succeeded,
                "retries_failed": retries_failed,
                "accounts_marked_overdue": accounts_marked_overdue,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "payment_retry_job_error",
                exc_info=e,
            )
            raise


async def _find_payments_due_for_retry(db: AsyncSession) -> list[Payment]:
    """
    Find payments that are due for retry.

    A payment is due for retry if:
    - Status is FAILED
    - next_retry_at is in the past or now
    - retry_count < max retries (4)

    Args:
        db: Database session

    Returns:
        List of payments due for retry
    """
    now = datetime.utcnow().isoformat()
    max_retries = len(PaymentService.RETRY_SCHEDULE_DAYS)

    result = await db.execute(
        select(Payment)
        .options(
            selectinload(Payment.invoice).selectinload(Invoice.account)
        )
        .where(
            and_(
                Payment.status == PaymentStatus.FAILED,
                Payment.next_retry_at.isnot(None),
                Payment.next_retry_at <= now,
                Payment.retry_count < max_retries,
            )
        )
        .order_by(Payment.next_retry_at)
    )

    return list(result.scalars().all())


async def _mark_account_overdue(db: AsyncSession, payment: Payment) -> None:
    """
    Mark account as OVERDUE after all payment retries failed.

    Also marks the invoice as OVERDUE.

    Args:
        db: Database session
        payment: Failed payment
    """
    # Get invoice
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == payment.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()

    if not invoice:
        logger.warning(
            "invoice_not_found_for_overdue",
            payment_id=str(payment.id),
            invoice_id=str(payment.invoice_id),
        )
        return

    # Mark invoice as OVERDUE
    if invoice.status != InvoiceStatus.OVERDUE:
        invoice.status = InvoiceStatus.OVERDUE

    # Get account
    account_result = await db.execute(
        select(Account).where(Account.id == invoice.account_id)
    )
    account = account_result.scalar_one_or_none()

    if not account:
        logger.warning(
            "account_not_found_for_overdue",
            payment_id=str(payment.id),
            invoice_id=str(payment.invoice_id),
        )
        return

    # Mark account as BLOCKED (final step after all retries)
    if account.status != AccountStatus.BLOCKED:
        account.status = AccountStatus.BLOCKED

        logger.info(
            "account_marked_overdue",
            account_id=str(account.id),
            invoice_id=str(invoice.id),
            payment_id=str(payment.id),
        )


async def process_pending_payments() -> dict[str, int]:
    """
    Process pending payments that haven't been attempted yet.

    This is for payments created but not yet sent to payment gateway.

    Returns:
        Dict with counts of processed payments
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find pending payments
            result = await db.execute(
                select(Payment)
                .options(
                    selectinload(Payment.invoice).selectinload(Invoice.account)
                )
                .where(
                    Payment.status == PaymentStatus.PENDING,
                    Payment.payment_gateway_transaction_id.is_(None),
                )
                .order_by(Payment.created_at)
                .limit(100)  # Process in batches
            )
            pending_payments = list(result.scalars().all())

            logger.info(
                "pending_payments_processing_started",
                payments_count=len(pending_payments),
            )

            processed = 0
            succeeded = 0
            failed = 0
            errors = 0

            payment_service = PaymentService(db)

            for payment in pending_payments:
                try:
                    # Attempt payment
                    result = await payment_service.retry_payment(payment_id=payment.id)

                    processed += 1

                    if result.status == PaymentStatus.SUCCEEDED:
                        succeeded += 1
                    else:
                        failed += 1

                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "pending_payment_processing_error",
                        payment_id=str(payment.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "pending_payments_processing_completed",
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                errors=errors,
            )

            return {
                "processed": processed,
                "succeeded": succeeded,
                "failed": failed,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "pending_payments_processing_job_error",
                exc_info=e,
            )
            raise
