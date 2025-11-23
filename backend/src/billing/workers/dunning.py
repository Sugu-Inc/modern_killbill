"""Dunning process worker for handling overdue payments.

This worker runs daily to:
1. Check for overdue invoices
2. Send reminders at day 3, warnings at day 7
3. Block accounts at day 14 after multiple failed payments
4. Unblock accounts when payment is successful
"""
from datetime import datetime, timedelta
from typing import List

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.database import AsyncSessionLocal
from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.account import Account, AccountStatus
from billing.services.dunning_service import DunningService
from billing.integrations.notification_service import NotificationService

logger = structlog.get_logger(__name__)

# Dunning schedule (days after invoice due date)
REMINDER_DAY = 3
WARNING_DAY = 7
BLOCK_DAY = 14


async def process_dunning() -> dict[str, int]:
    """
    Process dunning for overdue invoices.

    Implements a progressive dunning strategy:
    - Day 3: Send friendly reminder
    - Day 7: Send warning and mark account as WARNING
    - Day 14: Block account (mark as BLOCKED)

    Returns:
        Dict with counts of dunning actions taken
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find overdue invoices
            overdue_invoices = await _find_overdue_invoices(db)

            logger.info(
                "dunning_process_started",
                overdue_invoices_count=len(overdue_invoices),
            )

            reminders_sent = 0
            warnings_sent = 0
            accounts_blocked = 0
            accounts_warned = 0
            errors = 0

            dunning_service = DunningService(db)

            for invoice in overdue_invoices:
                try:
                    days_overdue = _calculate_days_overdue(invoice)

                    if days_overdue >= BLOCK_DAY:
                        # Day 14+: Block account
                        await _block_account(db, dunning_service, invoice)
                        accounts_blocked += 1

                        logger.info(
                            "account_blocked",
                            account_id=str(invoice.account_id),
                            invoice_id=str(invoice.id),
                            days_overdue=days_overdue,
                        )

                    elif days_overdue >= WARNING_DAY:
                        # Day 7-13: Send warning and mark account as WARNING
                        await _send_warning(db, dunning_service, invoice)
                        warnings_sent += 1
                        accounts_warned += 1

                        logger.info(
                            "warning_sent",
                            account_id=str(invoice.account_id),
                            invoice_id=str(invoice.id),
                            days_overdue=days_overdue,
                        )

                    elif days_overdue >= REMINDER_DAY:
                        # Day 3-6: Send friendly reminder
                        await _send_reminder(db, dunning_service, invoice)
                        reminders_sent += 1

                        logger.info(
                            "reminder_sent",
                            account_id=str(invoice.account_id),
                            invoice_id=str(invoice.id),
                            days_overdue=days_overdue,
                        )

                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "dunning_process_failed",
                        invoice_id=str(invoice.id),
                        account_id=str(invoice.account_id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "dunning_process_completed",
                reminders_sent=reminders_sent,
                warnings_sent=warnings_sent,
                accounts_blocked=accounts_blocked,
                accounts_warned=accounts_warned,
                errors=errors,
            )

            return {
                "reminders_sent": reminders_sent,
                "warnings_sent": warnings_sent,
                "accounts_blocked": accounts_blocked,
                "accounts_warned": accounts_warned,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "dunning_process_job_error",
                exc_info=e,
            )
            raise


async def process_payment_unblocking() -> dict[str, int]:
    """
    Unblock accounts that have successfully paid overdue invoices.

    Returns:
        Dict with counts of unblocked accounts
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find blocked or warning accounts that have paid all overdue invoices
            result = await db.execute(
                select(Account)
                .where(
                    Account.status.in_([AccountStatus.BLOCKED, AccountStatus.WARNING])
                )
            )
            affected_accounts = list(result.scalars().all())

            logger.info(
                "payment_unblocking_started",
                affected_accounts_count=len(affected_accounts),
            )

            accounts_unblocked = 0
            errors = 0

            dunning_service = DunningService(db)

            for account in affected_accounts:
                try:
                    # Check if account has any overdue invoices
                    has_overdue = await _has_overdue_invoices(db, account.id)

                    if not has_overdue:
                        # No overdue invoices, unblock account
                        await dunning_service.unblock_account(account_id=account.id)
                        accounts_unblocked += 1

                        logger.info(
                            "account_unblocked",
                            account_id=str(account.id),
                            previous_status=account.status.value,
                        )

                        await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "payment_unblocking_failed",
                        account_id=str(account.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "payment_unblocking_completed",
                accounts_unblocked=accounts_unblocked,
                errors=errors,
            )

            return {
                "accounts_unblocked": accounts_unblocked,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "payment_unblocking_job_error",
                exc_info=e,
            )
            raise


async def _find_overdue_invoices(db: AsyncSession) -> List[Invoice]:
    """
    Find invoices that are overdue and need dunning.

    Args:
        db: Database session

    Returns:
        List of overdue invoices
    """
    now = datetime.utcnow()

    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.account)
        )
        .where(
            and_(
                Invoice.status == InvoiceStatus.OVERDUE,
                Invoice.due_date < now,
            )
        )
        .order_by(Invoice.due_date)
    )

    return list(result.scalars().all())


def _calculate_days_overdue(invoice: Invoice) -> int:
    """
    Calculate number of days an invoice is overdue.

    Args:
        invoice: Invoice to check

    Returns:
        Number of days overdue
    """
    if not invoice.due_date:
        return 0

    now = datetime.utcnow()
    delta = now - invoice.due_date

    return delta.days


async def _send_reminder(
    db: AsyncSession,
    dunning_service: DunningService,
    invoice: Invoice,
) -> None:
    """
    Send friendly payment reminder.

    Args:
        db: Database session
        dunning_service: Dunning service
        invoice: Overdue invoice
    """
    # Check if reminder already sent for this invoice
    # (You might want to track this in metadata or a separate table)
    if invoice.metadata and invoice.metadata.get("reminder_sent"):
        return

    # Send reminder
    await dunning_service.send_reminder(
        account_id=invoice.account_id,
        invoice_id=invoice.id,
    )

    # Mark reminder as sent
    if not invoice.metadata:
        invoice.metadata = {}
    invoice.metadata["reminder_sent"] = True
    invoice.metadata["reminder_sent_at"] = datetime.utcnow().isoformat()


async def _send_warning(
    db: AsyncSession,
    dunning_service: DunningService,
    invoice: Invoice,
) -> None:
    """
    Send warning about impending service blocking.

    Args:
        db: Database session
        dunning_service: Dunning service
        invoice: Overdue invoice
    """
    # Check if warning already sent
    if invoice.metadata and invoice.metadata.get("warning_sent"):
        return

    # Send warning
    await dunning_service.send_warning(
        account_id=invoice.account_id,
        invoice_id=invoice.id,
    )

    # Update account status to WARNING
    account = invoice.account
    if account and account.status == AccountStatus.ACTIVE:
        account.status = AccountStatus.WARNING

    # Mark warning as sent
    if not invoice.metadata:
        invoice.metadata = {}
    invoice.metadata["warning_sent"] = True
    invoice.metadata["warning_sent_at"] = datetime.utcnow().isoformat()


async def _block_account(
    db: AsyncSession,
    dunning_service: DunningService,
    invoice: Invoice,
) -> None:
    """
    Block account due to persistent non-payment.

    Args:
        db: Database session
        dunning_service: Dunning service
        invoice: Overdue invoice
    """
    # Check if already blocked
    account = invoice.account
    if account and account.status == AccountStatus.BLOCKED:
        return

    # Block account
    await dunning_service.block_account(
        account_id=invoice.account_id,
        reason=f"Payment overdue for invoice {invoice.number}",
    )

    # Mark in invoice metadata
    if not invoice.metadata:
        invoice.metadata = {}
    invoice.metadata["account_blocked"] = True
    invoice.metadata["account_blocked_at"] = datetime.utcnow().isoformat()


async def _has_overdue_invoices(db: AsyncSession, account_id) -> bool:
    """
    Check if account has any overdue invoices.

    Args:
        db: Database session
        account_id: Account UUID

    Returns:
        True if account has overdue invoices
    """
    result = await db.execute(
        select(Invoice)
        .where(
            and_(
                Invoice.account_id == account_id,
                Invoice.status == InvoiceStatus.OVERDUE,
            )
        )
        .limit(1)
    )

    return result.scalar_one_or_none() is not None
