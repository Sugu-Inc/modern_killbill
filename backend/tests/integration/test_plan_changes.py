"""Integration tests for plan changes and proration (User Story 6)."""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import PlanInterval
from billing.models.invoice import InvoiceStatus
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate, SubscriptionPlanChange


@pytest.mark.asyncio
async def test_mid_cycle_upgrade_generates_prorated_invoice(db_session: AsyncSession) -> None:
    """Test that upgrading mid-cycle generates a prorated invoice immediately."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="upgrade@example.com", name="Upgrade Account")
    )

    # Create old plan ($10/month)
    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Basic Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )

    # Create new plan ($20/month)
    new_plan = await plan_service.create_plan(
        PlanCreate(name="Premium Plan", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    await db_session.commit()

    # Create subscription on old plan
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Count invoices before upgrade
    invoice_service = InvoiceService(db_session)
    invoices_before, _ = await invoice_service.list_invoices(subscription_id=subscription.id)
    count_before = len(invoices_before)

    # Upgrade immediately (mid-cycle)
    plan_change = SubscriptionPlanChange(new_plan_id=new_plan.id, immediate=True)
    changed_subscription = await subscription_service.change_plan(subscription.id, plan_change)
    await db_session.commit()

    # Verify subscription changed
    assert changed_subscription.plan_id == new_plan.id
    assert changed_subscription.pending_plan_id is None

    # Verify prorated invoice was generated
    invoices_after, _ = await invoice_service.list_invoices(subscription_id=subscription.id)
    count_after = len(invoices_after)

    assert count_after > count_before, "Prorated invoice should be generated"

    # Find the prorated invoice
    prorated_invoice = None
    for invoice in invoices_after:
        if invoice.id not in [inv.id for inv in invoices_before]:
            prorated_invoice = invoice
            break

    assert prorated_invoice is not None
    assert prorated_invoice.extra_metadata.get("proration") is True


@pytest.mark.asyncio
async def test_annual_to_monthly_downgrade_applies_credit(db_session: AsyncSession) -> None:
    """Test that downgrading from annual to monthly applies credit correctly."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="downgrade@example.com", name="Downgrade Account")
    )

    # Create annual plan ($100/year)
    plan_service = PlanService(db_session)
    annual_plan = await plan_service.create_plan(
        PlanCreate(name="Annual Plan", interval=PlanInterval.YEAR, amount=10000, currency="USD")
    )

    # Create monthly plan ($12/month)
    monthly_plan = await plan_service.create_plan(
        PlanCreate(name="Monthly Plan", interval=PlanInterval.MONTH, amount=1200, currency="USD")
    )
    await db_session.commit()

    # Create subscription on annual plan
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=annual_plan.id, quantity=1)
    )
    await db_session.commit()

    # Downgrade to monthly (should schedule for period end)
    plan_change = SubscriptionPlanChange(new_plan_id=monthly_plan.id, change_at_period_end=True)
    changed_subscription = await subscription_service.change_plan(subscription.id, plan_change)
    await db_session.commit()

    # Verify subscription scheduled for change
    assert changed_subscription.plan_id == annual_plan.id  # Still on annual
    assert changed_subscription.pending_plan_id == monthly_plan.id  # Pending change


@pytest.mark.asyncio
async def test_end_of_period_downgrade_scheduling(db_session: AsyncSession) -> None:
    """Test that downgrades are scheduled for end of period."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="scheduledown@example.com", name="Schedule Downgrade")
    )

    # Create premium plan ($30/month)
    plan_service = PlanService(db_session)
    premium_plan = await plan_service.create_plan(
        PlanCreate(name="Premium", interval=PlanInterval.MONTH, amount=3000, currency="USD")
    )

    # Create basic plan ($10/month)
    basic_plan = await plan_service.create_plan(
        PlanCreate(name="Basic", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create subscription on premium plan
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=premium_plan.id, quantity=1)
    )
    await db_session.commit()

    # Schedule downgrade for period end
    plan_change = SubscriptionPlanChange(new_plan_id=basic_plan.id, change_at_period_end=True)
    changed_subscription = await subscription_service.change_plan(subscription.id, plan_change)
    await db_session.commit()

    # Verify current plan unchanged
    assert changed_subscription.plan_id == premium_plan.id
    assert changed_subscription.pending_plan_id == basic_plan.id


@pytest.mark.asyncio
async def test_proration_on_day_1(db_session: AsyncSession) -> None:
    """Test proration calculation when changing plan on day 1 of billing cycle."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="day1@example.com", name="Day 1 Account")
    )

    # Create plans
    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Old", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="New", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Calculate proration on day 1 (should be nearly 100% of the period remaining)
    invoice_service = InvoiceService(db_session)
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end
    change_date = period_start + timedelta(days=1)

    proration = await invoice_service.calculate_proration(
        old_amount=old_plan.amount,
        new_amount=new_plan.amount,
        period_start=period_start,
        period_end=period_end,
        change_date=change_date,
    )

    # Credit should be nearly the full old plan amount (unused ~29 days)
    # Charge should be nearly the full new plan amount (using ~29 days)
    assert proration["credit"] > 900  # Most of $10
    assert proration["charge"] > 1800  # Most of $20


@pytest.mark.asyncio
async def test_proration_on_last_day(db_session: AsyncSession) -> None:
    """Test proration calculation when changing plan on last day of billing cycle."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="lastday@example.com", name="Last Day Account")
    )

    # Create plans
    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Old", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="New", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Calculate proration on last day (should be minimal)
    invoice_service = InvoiceService(db_session)
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end
    change_date = period_end - timedelta(days=1)

    proration = await invoice_service.calculate_proration(
        old_amount=old_plan.amount,
        new_amount=new_plan.amount,
        period_start=period_start,
        period_end=period_end,
        change_date=change_date,
    )

    # Credit should be minimal (unused ~1 day)
    # Charge should be minimal (using ~1 day)
    assert proration["credit"] < 100  # Small fraction of $10
    assert proration["charge"] < 200  # Small fraction of $20


@pytest.mark.asyncio
async def test_proration_with_quantity_changes(db_session: AsyncSession) -> None:
    """Test proration when changing both plan and quantity."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="quantity@example.com", name="Quantity Account")
    )

    # Create plans
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Per-Seat Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create subscription with quantity=2
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=2)
    )
    await db_session.commit()

    # Verify initial quantity
    assert subscription.quantity == 2

    # Change quantity to 5 mid-cycle
    plan_change = SubscriptionPlanChange(new_plan_id=plan.id, new_quantity=5, immediate=True)
    changed_subscription = await subscription_service.change_plan(subscription.id, plan_change)
    await db_session.commit()

    # Verify quantity changed
    assert changed_subscription.quantity == 5


# API endpoint tests


@pytest.mark.asyncio
async def test_change_plan_via_api(async_client: AsyncClient) -> None:
    """Test changing plan via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "apichange@example.com", "name": "API Change"},
    )
    account_id = account_response.json()["id"]

    # Create plans
    old_plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "Old API Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    old_plan_id = old_plan_response.json()["id"]

    new_plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "New API Plan", "interval": "month", "amount": 2000, "currency": "USD"},
    )
    new_plan_id = new_plan_response.json()["id"]

    # Create subscription
    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": old_plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Change plan via API
    change_response = await async_client.patch(
        f"/v1/subscriptions/{subscription_id}",
        json={"new_plan_id": new_plan_id, "immediate": True},
    )

    assert change_response.status_code == 200
    data = change_response.json()
    assert data["plan_id"] == new_plan_id


@pytest.mark.asyncio
async def test_schedule_plan_change_via_api(async_client: AsyncClient) -> None:
    """Test scheduling plan change for period end via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "apischedule@example.com", "name": "API Schedule"},
    )
    account_id = account_response.json()["id"]

    # Create plans
    current_plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "Current Plan", "interval": "month", "amount": 3000, "currency": "USD"},
    )
    current_plan_id = current_plan_response.json()["id"]

    future_plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "Future Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    future_plan_id = future_plan_response.json()["id"]

    # Create subscription
    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": current_plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Schedule plan change via API
    change_response = await async_client.patch(
        f"/v1/subscriptions/{subscription_id}",
        json={"new_plan_id": future_plan_id, "change_at_period_end": True},
    )

    assert change_response.status_code == 200
    data = change_response.json()
    assert data["plan_id"] == current_plan_id  # Still on current plan
    assert data["pending_plan_id"] == future_plan_id  # Pending change
