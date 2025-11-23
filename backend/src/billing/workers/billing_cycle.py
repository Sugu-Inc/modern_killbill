"""Billing cycle worker for automatic invoice generation.

This worker runs periodically to:
1. Check for subscriptions reaching their billing cycle end
2. Generate invoices for active subscriptions
3. Attempt automatic payment collection
4. Handle subscription renewals
"""
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.database import AsyncSessionLocal
from billing.models.subscription import Subscription, SubscriptionStatus
from billing.models.invoice import InvoiceStatus
from billing.services.invoice_service import InvoiceService
from billing.services.subscription_service import SubscriptionService

logger = structlog.get_logger(__name__)


async def process_billing_cycles() -> dict[str, int]:
    """
    Process billing cycles for all subscriptions due for renewal.

    This function should be called by a scheduler (e.g., ARQ, Celery, or cron) every hour.

    Returns:
        Dict with counts of processed subscriptions and generated invoices
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find subscriptions that need billing
            subscriptions_to_bill = await _find_subscriptions_due_for_billing(db)

            logger.info(
                "billing_cycle_started",
                subscriptions_count=len(subscriptions_to_bill),
            )

            invoices_generated = 0
            subscriptions_renewed = 0
            errors = 0

            for subscription in subscriptions_to_bill:
                try:
                    # Generate invoice for subscription
                    invoice = await _generate_invoice_for_subscription(db, subscription)

                    if invoice:
                        invoices_generated += 1

                        # Renew subscription to next period
                        await _renew_subscription(db, subscription)
                        subscriptions_renewed += 1

                        logger.info(
                            "subscription_billed",
                            subscription_id=str(subscription.id),
                            invoice_id=str(invoice.id),
                            invoice_number=invoice.number,
                            amount=invoice.amount_due,
                        )

                    # Commit each subscription individually to avoid partial failures
                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "subscription_billing_failed",
                        subscription_id=str(subscription.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "billing_cycle_completed",
                subscriptions_processed=len(subscriptions_to_bill),
                invoices_generated=invoices_generated,
                subscriptions_renewed=subscriptions_renewed,
                errors=errors,
            )

            return {
                "subscriptions_processed": len(subscriptions_to_bill),
                "invoices_generated": invoices_generated,
                "subscriptions_renewed": subscriptions_renewed,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "billing_cycle_error",
                exc_info=e,
            )
            raise


async def process_trial_expirations() -> dict[str, int]:
    """
    Process subscriptions with expiring trials.

    Transitions subscriptions from TRIALING to ACTIVE status and generates first invoice.

    Returns:
        Dict with counts of processed trials
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find trials expiring today
            now = datetime.utcnow()
            result = await db.execute(
                select(Subscription)
                .options(selectinload(Subscription.plan), selectinload(Subscription.account))
                .where(
                    Subscription.status == SubscriptionStatus.TRIALING,
                    Subscription.trial_end <= now,
                )
            )
            expiring_trials = result.scalars().all()

            logger.info(
                "trial_expiration_started",
                trials_count=len(expiring_trials),
            )

            transitions = 0
            invoices_generated = 0
            errors = 0

            subscription_service = SubscriptionService(db)
            invoice_service = InvoiceService(db)

            for subscription in expiring_trials:
                try:
                    # Transition to ACTIVE
                    subscription.status = SubscriptionStatus.ACTIVE

                    # Create history record
                    await subscription_service._create_history(
                        subscription_id=subscription.id,
                        event_type="trial_ended",
                        old_value="trialing",
                        new_value="active",
                    )

                    transitions += 1

                    # Generate first invoice
                    invoice = await invoice_service.generate_invoice_for_subscription(
                        subscription_id=subscription.id,
                    )
                    invoices_generated += 1

                    await db.commit()

                    logger.info(
                        "trial_expired",
                        subscription_id=str(subscription.id),
                        invoice_id=str(invoice.id),
                    )

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "trial_expiration_failed",
                        subscription_id=str(subscription.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "trial_expiration_completed",
                transitions=transitions,
                invoices_generated=invoices_generated,
                errors=errors,
            )

            return {
                "transitions": transitions,
                "invoices_generated": invoices_generated,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "trial_expiration_error",
                exc_info=e,
            )
            raise


async def process_scheduled_plan_changes() -> dict[str, int]:
    """
    Process scheduled plan changes (downgrades at period end).

    Returns:
        Dict with counts of processed plan changes
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find subscriptions with pending plan changes
            now = datetime.utcnow()
            result = await db.execute(
                select(Subscription)
                .options(
                    selectinload(Subscription.plan),
                    selectinload(Subscription.account),
                )
                .where(
                    Subscription.pending_plan_id.isnot(None),
                    Subscription.current_period_end <= now,
                )
            )
            subscriptions_to_change = result.scalars().all()

            logger.info(
                "scheduled_plan_changes_started",
                changes_count=len(subscriptions_to_change),
            )

            changes_processed = 0
            errors = 0

            subscription_service = SubscriptionService(db)

            for subscription in subscriptions_to_change:
                try:
                    # Apply pending plan change
                    old_plan_id = subscription.plan_id
                    new_plan_id = subscription.pending_plan_id

                    subscription.plan_id = new_plan_id
                    subscription.pending_plan_id = None

                    # Create history record
                    await subscription_service._create_history(
                        subscription_id=subscription.id,
                        event_type="plan_changed",
                        old_value=str(old_plan_id),
                        new_value=str(new_plan_id),
                    )

                    changes_processed += 1
                    await db.commit()

                    logger.info(
                        "scheduled_plan_change_applied",
                        subscription_id=str(subscription.id),
                        old_plan_id=str(old_plan_id),
                        new_plan_id=str(new_plan_id),
                    )

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "scheduled_plan_change_failed",
                        subscription_id=str(subscription.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "scheduled_plan_changes_completed",
                changes_processed=changes_processed,
                errors=errors,
            )

            return {
                "changes_processed": changes_processed,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "scheduled_plan_changes_error",
                exc_info=e,
            )
            raise


async def _find_subscriptions_due_for_billing(db: AsyncSession) -> list[Subscription]:
    """
    Find subscriptions that are due for billing.

    Args:
        db: Database session

    Returns:
        List of subscriptions due for billing
    """
    # Find subscriptions where current_period_end is today or earlier
    now = datetime.utcnow()

    result = await db.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan), selectinload(Subscription.account))
        .where(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]),
            Subscription.current_period_end <= now,
            Subscription.cancel_at_period_end == False,  # noqa: E712
        )
    )

    return list(result.scalars().all())


async def _generate_invoice_for_subscription(
    db: AsyncSession,
    subscription: Subscription,
) -> "Invoice | None":
    """
    Generate invoice for a subscription.

    Args:
        db: Database session
        subscription: Subscription to generate invoice for

    Returns:
        Generated invoice or None if already exists
    """
    invoice_service = InvoiceService(db)

    try:
        invoice = await invoice_service.generate_invoice_for_subscription(
            subscription_id=subscription.id,
        )
        return invoice
    except ValueError as e:
        # Invoice might already exist for this period
        if "already exists" in str(e):
            logger.warning(
                "invoice_already_exists",
                subscription_id=str(subscription.id),
                period_start=subscription.current_period_start.isoformat(),
            )
            return None
        raise


async def _renew_subscription(db: AsyncSession, subscription: Subscription) -> None:
    """
    Renew subscription to next billing period.

    Args:
        db: Database session
        subscription: Subscription to renew
    """
    plan = subscription.plan

    # Calculate next period
    current_end = subscription.current_period_end

    if plan.interval.value == "month":
        next_period_end = current_end + timedelta(days=30)
    else:  # year
        next_period_end = current_end + timedelta(days=365)

    # Update subscription period
    subscription.current_period_start = current_end
    subscription.current_period_end = next_period_end

    # Create history record
    subscription_service = SubscriptionService(db)
    await subscription_service._create_history(
        subscription_id=subscription.id,
        event_type="renewed",
        old_value=current_end.isoformat(),
        new_value=next_period_end.isoformat(),
    )

    logger.info(
        "subscription_renewed",
        subscription_id=str(subscription.id),
        new_period_start=current_end.isoformat(),
        new_period_end=next_period_end.isoformat(),
    )


async def process_auto_resume_subscriptions(db: AsyncSession | None = None) -> dict[str, int]:
    """
    Process subscriptions that should be automatically resumed.

    Also handles auto-cancellation for subscriptions paused > 90 days.

    Args:
        db: Optional database session (for testing). If None, creates new session.

    Returns:
        Dict with counts of resumed and cancelled subscriptions
    """
    # Use provided session or create new one
    should_close_db = db is None
    if db is None:
        db = AsyncSessionLocal()

    try:
        try:
            now = datetime.utcnow()
            ninety_days_ago = now - timedelta(days=90)

            # Find paused subscriptions that should be resumed
            result = await db.execute(
                select(Subscription)
                .options(
                    selectinload(Subscription.plan),
                    selectinload(Subscription.account)
                )
                .where(
                    Subscription.status == SubscriptionStatus.PAUSED,
                )
            )
            paused_subscriptions = result.scalars().all()

            logger.info(
                "auto_resume_started",
                paused_count=len(paused_subscriptions),
            )

            resumed = 0
            cancelled = 0
            errors = 0

            subscription_service = SubscriptionService(db)

            for subscription in paused_subscriptions:
                try:
                    # Check if should auto-cancel (paused > 90 days)
                    # Determine when subscription was paused by looking at updated_at
                    pause_duration = now - subscription.updated_at
                    if pause_duration.days >= 90:
                        # Auto-cancel
                        subscription.status = SubscriptionStatus.CANCELLED
                        subscription.cancelled_at = now

                        await subscription_service._create_history(
                            subscription_id=subscription.id,
                            event_type="auto_cancelled",
                            old_value="paused",
                            new_value="cancelled",
                        )

                        cancelled += 1
                        logger.info(
                            "subscription_auto_cancelled",
                            subscription_id=str(subscription.id),
                            pause_duration_days=pause_duration.days,
                        )

                    # Check if should auto-resume
                    elif subscription.pause_resumes_at and subscription.pause_resumes_at <= now:
                        await subscription_service.resume_subscription(subscription.id)
                        resumed += 1

                        logger.info(
                            "subscription_auto_resumed",
                            subscription_id=str(subscription.id),
                            resumed_at=now.isoformat(),
                        )

                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    errors += 1
                    logger.exception(
                        "auto_resume_failed",
                        subscription_id=str(subscription.id),
                        exc_info=e,
                    )
                    continue

            logger.info(
                "auto_resume_completed",
                resumed=resumed,
                cancelled=cancelled,
                errors=errors,
            )

            return {
                "resumed": resumed,
                "cancelled": cancelled,
                "errors": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.exception(
                "auto_resume_error",
                exc_info=e,
            )
            raise
    finally:
        # Close session only if it was created by this function
        if should_close_db and db is not None:
            await db.close()
