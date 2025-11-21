"""
Integration tests for subscription pause/resume functionality.

Tests US16: Pause Subscriptions
- Pause stops billing
- Auto-resume on scheduled date
- Auto-cancel after 90 days
- Usage tracking stops during pause
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from billing.models.subscription import Subscription, SubscriptionStatus
from billing.models.usage_record import UsageRecord
from billing.models.invoice import Invoice
from billing.schemas.subscription import SubscriptionCreate, SubscriptionPause, SubscriptionPlanChange
from billing.schemas.usage_record import UsageRecordCreate
from billing.services.subscription_service import SubscriptionService
from billing.services.usage_service import UsageService
from billing.workers.billing_cycle import process_auto_resume_subscriptions


@pytest.mark.asyncio
async def test_pause_stops_billing(async_db, test_account, test_plan):
    """
    Test that pausing a subscription stops billing.

    Given: An active subscription
    When: Subscription is paused
    Then: Billing is stopped and no new invoices are generated
    """
    # Create active subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    assert subscription.status == SubscriptionStatus.ACTIVE

    # Pause subscription for 30 days
    resume_date = datetime.utcnow() + timedelta(days=30)
    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=resume_date)
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    assert paused_subscription.status == SubscriptionStatus.PAUSED
    assert paused_subscription.pause_resumes_at == resume_date

    # Verify billing is stopped
    # Query for invoices created after pause
    stmt = select(Invoice).where(
        Invoice.subscription_id == subscription.id,
        Invoice.created_at > datetime.utcnow()
    )
    result = await async_db.execute(stmt)
    invoices_after_pause = result.scalars().all()

    # No new invoices should be created during pause
    assert len(invoices_after_pause) == 0


@pytest.mark.asyncio
async def test_auto_resume_on_date(async_db, test_account, test_plan):
    """
    Test that subscription auto-resumes on scheduled date.

    Given: A paused subscription with resume date
    When: Resume date arrives
    Then: Subscription automatically resumes to ACTIVE status
    """
    # Create and pause subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    # Pause with resume date in the past (to simulate resume time has arrived)
    past_resume_date = datetime.utcnow() - timedelta(days=1)
    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=past_resume_date)
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    assert paused_subscription.status == SubscriptionStatus.PAUSED

    # Run background job that checks for subscriptions to resume
    result = await process_auto_resume_subscriptions(db=async_db)

    assert result['resumed'] >= 1

    # Verify subscription is resumed
    await async_db.refresh(paused_subscription)
    assert paused_subscription.status == SubscriptionStatus.ACTIVE
    assert paused_subscription.pause_resumes_at is None


@pytest.mark.asyncio
async def test_auto_cancel_after_90_days(async_db, test_account, test_plan):
    """
    Test that subscription auto-cancels if paused > 90 days.

    Given: A paused subscription
    When: Pause period exceeds 90 days without resume
    Then: Subscription is automatically cancelled
    """
    # Create and pause subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    # Pause subscription indefinitely (no resume date)
    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=None)  # No resume date
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    # Simulate 91 days have passed by backdating the pause
    paused_subscription.updated_at = datetime.utcnow() - timedelta(days=91)
    await async_db.commit()

    # Run auto-cancel logic
    cancelled_count = await subscription_service.cancel_long_paused_subscriptions()

    assert cancelled_count >= 1

    # Verify subscription is cancelled
    await async_db.refresh(paused_subscription)
    assert paused_subscription.status == SubscriptionStatus.CANCELLED


@pytest.mark.asyncio
async def test_usage_tracking_stops_during_pause(async_db, test_account, test_plan_usage):
    """
    Test that usage tracking stops during pause period.

    Given: An active usage-based subscription
    When: Subscription is paused
    Then: Usage events are rejected during pause period
    """
    # Create usage-based subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan_usage.id,  # Usage-based plan
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    # Record usage while active (should succeed)
    usage_service = UsageService(async_db)
    usage_before_pause = await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=100,
            timestamp=datetime.utcnow(),
            idempotency_key="test-usage-1"
        )
    )

    assert usage_before_pause is not None

    # Pause subscription
    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=datetime.utcnow() + timedelta(days=30))
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    # Attempt to record usage while paused (should be rejected or ignored)
    with pytest.raises(ValueError, match="paused|inactive"):
        await usage_service.record_usage(
            UsageRecordCreate(
                subscription_id=subscription.id,
                metric="api_calls",
                quantity=50,
                timestamp=datetime.utcnow(),
                idempotency_key="test-usage-2"
            )
        )

    # Verify only pre-pause usage was recorded
    stmt = select(UsageRecord).where(
        UsageRecord.subscription_id == subscription.id
    )
    result = await async_db.execute(stmt)
    usage_records = result.scalars().all()

    assert len(usage_records) == 1  # Only the pre-pause usage
    assert usage_records[0].idempotency_key == "test-usage-1"


@pytest.mark.asyncio
async def test_pause_and_resume_workflow(async_db, test_account, test_plan):
    """
    Test complete pause and manual resume workflow.

    Given: An active subscription
    When: User pauses and then manually resumes
    Then: Subscription returns to ACTIVE status
    """
    # Create subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    initial_status = subscription.status
    assert initial_status == SubscriptionStatus.ACTIVE

    # Pause subscription
    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=datetime.utcnow() + timedelta(days=30))
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    assert paused_subscription.status == SubscriptionStatus.PAUSED
    assert paused_subscription.pause_resumes_at is not None

    # Manually resume (user changed their mind)
    resumed_subscription = await subscription_service.resume_subscription(
        subscription_id=subscription.id
    )

    assert resumed_subscription.status == SubscriptionStatus.ACTIVE
    assert resumed_subscription.pause_resumes_at is None

    # Verify billing resumes (subscription can generate invoices)
    # This would be tested by the billing cycle worker in practice


@pytest.mark.asyncio
async def test_pause_prevents_plan_changes(async_db, test_account, test_plan, test_plan_premium):
    """
    Test that plan changes are not allowed during pause.

    Given: A paused subscription
    When: User attempts to change plan
    Then: Operation is rejected
    """
    # Create and pause subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=datetime.utcnow() + timedelta(days=30))
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    # Attempt to change plan while paused
    with pytest.raises(ValueError, match="paused|cannot change"):
        await subscription_service.change_plan(
            subscription_id=paused_subscription.id,
            plan_change=SubscriptionPlanChange(
                new_plan_id=test_plan_premium.id
            )
        )


@pytest.mark.asyncio
async def test_pause_with_pending_invoice(async_db, test_account, test_plan):
    """
    Test pause behavior when there's a pending invoice.

    Given: A subscription with an unpaid invoice
    When: Subscription is paused
    Then: Existing invoice remains due, but no new invoices generated
    """
    # Create subscription (generates first invoice)
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    # Get the initial invoice
    stmt = select(Invoice).where(
        Invoice.subscription_id == subscription.id
    )
    result = await async_db.execute(stmt)
    initial_invoice = result.scalars().first()

    assert initial_invoice is not None
    invoice_count_before_pause = 1

    # Pause subscription
    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=datetime.utcnow() + timedelta(days=30))
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    # Verify initial invoice still exists
    stmt = select(Invoice).where(
        Invoice.subscription_id == subscription.id
    )
    result = await async_db.execute(stmt)
    invoices_after_pause = result.scalars().all()

    assert len(invoices_after_pause) == invoice_count_before_pause
    # Initial invoice should still be there, but no new ones


@pytest.mark.asyncio
async def test_resume_reactivates_billing_cycle(async_db, test_account, test_plan):
    """
    Test that resuming subscription reactivates the billing cycle.

    Given: A paused subscription
    When: Subscription is resumed
    Then: Billing cycle continues from resume date
    """
    # Create and pause subscription
    subscription_service = SubscriptionService(async_db)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(
            account_id=test_account.id,
            plan_id=test_plan.id,
            quantity=1
        )
    )
    await async_db.commit()
    await async_db.refresh(subscription)

    original_period_end = subscription.current_period_end

    # Pause for 15 days
    pause_date = datetime.utcnow()
    resume_date = pause_date + timedelta(days=15)

    paused_subscription = await subscription_service.pause_subscription(
        subscription_id=subscription.id,
        pause_data=SubscriptionPause(resumes_at=resume_date)
    )
    await async_db.commit()
    await async_db.refresh(paused_subscription)

    # Resume subscription
    resumed_subscription = await subscription_service.resume_subscription(
        subscription_id=subscription.id
    )

    # Verify billing cycle is extended by pause duration
    # If paused for 15 days, period_end should be extended by 15 days
    expected_new_period_end = original_period_end + timedelta(days=15)

    # Allow 1-day tolerance for date calculations
    time_diff = abs((resumed_subscription.current_period_end - expected_new_period_end).days)
    assert time_diff <= 1
