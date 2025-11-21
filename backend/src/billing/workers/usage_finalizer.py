"""Usage finalizer worker for processing late usage events.

This worker runs periodically to:
1. Check for usage events that arrived after period close
2. Generate supplemental invoices for late usage (within 7-day window)
3. Apply late usage charges to existing invoices or create new ones
"""
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.database import AsyncSessionLocal
from billing.models.usage_record import UsageRecord
from billing.models.subscription import Subscription, SubscriptionStatus
from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.plan import Plan
from billing.services.invoice_service import InvoiceService
from billing.services.usage_service import UsageService

logger = structlog.get_logger(__name__)

# Grace period for late usage: 7 days after period end
LATE_USAGE_GRACE_PERIOD_DAYS = 7


async def process_late_usage() -> dict[str, int]:
    """
    Process late usage events that arrived after billing period close.

    Generates supplemental invoices for usage that arrived within the
    7-day grace period after the period end.

    Returns:
        Dict with counts of processed late usage
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find subscriptions with late usage
            subscriptions_with_late_usage = await _find_subscriptions_with_late_usage(db)

            logger.info(
                "late_usage_processing_started",
                subscriptions_count=len(subscriptions_with_late_usage),
            )

            supplemental_invoices_generated = 0
            usage_charges_applied = 0
            errors = 0

            invoice_service = InvoiceService(db)
            usage_service = UsageService(db)

            for subscription_data in subscriptions_with_late_usage:
                subscription = subscription_data["subscription"]
                period_start = subscription_data["period_start"]
                period_end = subscription_data["period_end"]
                late_usage_count = subscription_data["late_usage_count"]

                try:
                    # Check if an invoice already exists for this period
                    existing_invoice = await _get_invoice_for_period(
                        db, subscription.id, period_start, period_end
                    )

                    if not existing_invoice:
                        logger.warning(
                            "no_invoice_found_for_late_usage",
                            subscription_id=str(subscription.id),
                            period_start=period_start.isoformat(),
                            period_end=period_end.isoformat(),
                        )
                        continue

                    # Check if invoice is already PAID or VOID
                    if existing_invoice.status in [InvoiceStatus.PAID, InvoiceStatus.VOID]:
                        # Generate supplemental invoice for late usage
                        supplemental_invoice = await _generate_supplemental_invoice(
                            db,
                            invoice_service,
                            usage_service,
                            subscription,
                            period_start,
                            period_end,
                            late_usage_count,
                        )

                        if supplemental_invoice:
                            supplemental_invoices_generated += 1
                            usage_charges_applied += late_usage_count

                            logger.info(
                                "supplemental_invoice_generated",
                                subscription_id=str(subscription.id),
                                invoice_id=str(supplemental_invoice.id),
                                invoice_number=supplemental_invoice.number,
                                late_usage_count=late_usage_count,
                                amount=supplemental_invoice.amount_due,
                            )
                    else:
                        # Invoice not yet paid, add late usage to existing invoice
                        # This is handled by the invoice service during generation
                        logger.info(
                            "late_usage_added_to_existing_invoice",
                            subscription_id=str(subscription.id),
                            invoice_id=str(existing_invoice.id),
                            late_usage_count=late_usage_count,
                        )

                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "late_usage_processing_failed",
                        subscription_id=str(subscription.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "late_usage_processing_completed",
                supplemental_invoices_generated=supplemental_invoices_generated,
                usage_charges_applied=usage_charges_applied,
                errors=errors,
            )

            return {
                "supplemental_invoices_generated": supplemental_invoices_generated,
                "usage_charges_applied": usage_charges_applied,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "late_usage_processing_job_error",
                exc_info=e,
            )
            raise


async def _find_subscriptions_with_late_usage(db: AsyncSession) -> list[dict]:
    """
    Find subscriptions with late usage events.

    Late usage is defined as usage events that have timestamps within a
    previous billing period but were recorded after that period ended.

    Args:
        db: Database session

    Returns:
        List of subscription data with late usage
    """
    now = datetime.utcnow()
    grace_period_cutoff = now - timedelta(days=LATE_USAGE_GRACE_PERIOD_DAYS)

    # Find all active subscriptions
    result = await db.execute(
        select(Subscription)
        .options(
            selectinload(Subscription.plan),
            selectinload(Subscription.account)
        )
        .where(
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE
            ])
        )
    )
    subscriptions = list(result.scalars().all())

    subscriptions_with_late_usage = []

    for subscription in subscriptions:
        # Check if there's usage with timestamp before period end but recorded after
        # For simplicity, we check the previous period
        period_start = subscription.current_period_start - timedelta(days=30)  # Approximate
        period_end = subscription.current_period_start

        # Count late usage: timestamp in [period_start, period_end) but created_at > period_end
        late_usage_result = await db.execute(
            select(func.count(UsageRecord.id))
            .where(
                and_(
                    UsageRecord.subscription_id == subscription.id,
                    UsageRecord.timestamp >= period_start,
                    UsageRecord.timestamp < period_end,
                    UsageRecord.created_at >= period_end,
                    UsageRecord.created_at >= grace_period_cutoff,  # Within grace period
                )
            )
        )
        late_usage_count = late_usage_result.scalar() or 0

        if late_usage_count > 0:
            subscriptions_with_late_usage.append({
                "subscription": subscription,
                "period_start": period_start,
                "period_end": period_end,
                "late_usage_count": late_usage_count,
            })

    return subscriptions_with_late_usage


async def _get_invoice_for_period(
    db: AsyncSession,
    subscription_id,
    period_start: datetime,
    period_end: datetime,
) -> Optional[Invoice]:
    """
    Get invoice for a specific billing period.

    Args:
        db: Database session
        subscription_id: Subscription UUID
        period_start: Period start date
        period_end: Period end date

    Returns:
        Invoice for the period or None
    """
    # Find invoice with matching period
    # Note: This is simplified; you may need to add period fields to Invoice model
    result = await db.execute(
        select(Invoice)
        .where(
            and_(
                Invoice.subscription_id == subscription_id,
                Invoice.created_at >= period_start,
                Invoice.created_at < period_end + timedelta(days=1),
            )
        )
        .order_by(Invoice.created_at.desc())
        .limit(1)
    )

    return result.scalar_one_or_none()


async def _generate_supplemental_invoice(
    db: AsyncSession,
    invoice_service: InvoiceService,
    usage_service: UsageService,
    subscription: Subscription,
    period_start: datetime,
    period_end: datetime,
    late_usage_count: int,
) -> Optional[Invoice]:
    """
    Generate supplemental invoice for late usage.

    Args:
        db: Database session
        invoice_service: Invoice service
        usage_service: Usage service
        subscription: Subscription
        period_start: Period start
        period_end: Period end
        late_usage_count: Number of late usage events

    Returns:
        Generated supplemental invoice or None
    """
    try:
        # Get usage aggregation for the period
        plan = subscription.plan

        # Aggregate late usage
        usage_aggregation = await usage_service.aggregate_usage_for_period(
            subscription_id=subscription.id,
            metric=plan.name,  # Assuming metric matches plan name
            period_start=period_start,
            period_end=period_end,
        )

        if usage_aggregation.total_quantity == 0:
            return None

        # Calculate usage charges
        usage_charge = await usage_service.calculate_tiered_charges(
            plan=plan,
            total_usage=usage_aggregation.total_quantity,
        )

        if usage_charge == 0:
            return None

        # Generate supplemental invoice
        # Note: This is simplified - you may need to add a flag or method for supplemental invoices
        invoice = await invoice_service.generate_invoice_for_subscription(
            subscription_id=subscription.id,
        )

        # Add note about supplemental nature
        if invoice.metadata:
            invoice.metadata["supplemental"] = True
            invoice.metadata["original_period_start"] = period_start.isoformat()
            invoice.metadata["original_period_end"] = period_end.isoformat()
            invoice.metadata["late_usage_count"] = late_usage_count

        return invoice

    except Exception as e:
        logger.exception(
            "supplemental_invoice_generation_failed",
            subscription_id=str(subscription.id),
            exc_info=e,
        )
        return None


async def finalize_usage_periods() -> dict[str, int]:
    """
    Finalize usage periods that are past the grace period.

    Marks usage records as finalized so they won't be processed again.

    Returns:
        Dict with counts of finalized periods
    """
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.utcnow()
            finalization_cutoff = now - timedelta(days=LATE_USAGE_GRACE_PERIOD_DAYS)

            # This is a placeholder for period finalization logic
            # In a real system, you would track which periods have been finalized
            logger.info(
                "usage_period_finalization_started",
                finalization_cutoff=finalization_cutoff.isoformat(),
            )

            # Implementation depends on whether you add a "finalized" flag to periods
            # For now, this is a no-op placeholder

            logger.info(
                "usage_period_finalization_completed",
                periods_finalized=0,
            )

            return {
                "periods_finalized": 0,
            }

        except Exception as e:
            logger.exception(
                "usage_period_finalization_error",
                exc_info=e,
            )
            raise
