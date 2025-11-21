"""Integration tests for subscription management endpoints."""
import pytest
from datetime import datetime, timedelta
from uuid import UUID
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.subscription import Subscription, SubscriptionStatus
from billing.models.plan import PlanInterval
from billing.schemas.subscription import SubscriptionCreate, SubscriptionPause, SubscriptionPlanChange
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate


@pytest.mark.asyncio
async def test_create_subscription_with_payment(db_session: AsyncSession) -> None:
    """Test creating a subscription that requires immediate payment."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Create account
    account_service = AccountService(db_session)
    account_data = AccountCreate(email="sub@example.com", name="Sub Account")
    account = await account_service.create_account(account_data)

    # Create plan (no trial)
    plan_service = PlanService(db_session)
    plan_data = PlanCreate(
        name="Paid Plan",
        interval=PlanInterval.MONTH,
        amount=2900,
        currency="USD",
        trial_days=0,
    )
    plan = await plan_service.create_plan(plan_data)
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    assert subscription.id is not None
    assert isinstance(subscription.id, UUID)
    assert subscription.account_id == account.id
    assert subscription.plan_id == plan.id
    assert subscription.status == SubscriptionStatus.ACTIVE  # No trial
    assert subscription.quantity == 1
    assert subscription.current_period_start is not None
    assert subscription.current_period_end is not None
    assert subscription.trial_end is None


@pytest.mark.asyncio
async def test_create_subscription_with_trial(db_session: AsyncSession) -> None:
    """Test creating a subscription with trial period."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Create account
    account_service = AccountService(db_session)
    account_data = AccountCreate(email="trial@example.com", name="Trial Account")
    account = await account_service.create_account(account_data)

    # Create plan with trial
    plan_service = PlanService(db_session)
    plan_data = PlanCreate(
        name="Trial Plan",
        interval=PlanInterval.MONTH,
        amount=4900,
        currency="USD",
        trial_days=14,
    )
    plan = await plan_service.create_plan(plan_data)
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    assert subscription.status == SubscriptionStatus.TRIALING
    assert subscription.trial_end is not None
    # Trial should end in ~14 days
    expected_trial_end = datetime.utcnow() + timedelta(days=14)
    assert abs((subscription.trial_end - expected_trial_end).total_seconds()) < 60


@pytest.mark.asyncio
async def test_cancel_subscription_immediate(db_session: AsyncSession) -> None:
    """Test canceling a subscription immediately."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="cancel@example.com", name="Cancel Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Cancel Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    assert subscription.status == SubscriptionStatus.ACTIVE

    # Cancel immediately
    cancelled = await subscription_service.cancel_subscription(subscription.id, immediate=True)
    await db_session.commit()

    assert cancelled.status == SubscriptionStatus.CANCELLED
    assert cancelled.cancelled_at is not None


@pytest.mark.asyncio
async def test_cancel_subscription_at_period_end(db_session: AsyncSession) -> None:
    """Test scheduling subscription cancellation at period end."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="cancelend@example.com", name="Cancel End Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Cancel End Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Cancel at period end
    cancelled = await subscription_service.cancel_subscription(subscription.id, immediate=False)
    await db_session.commit()

    assert cancelled.status == SubscriptionStatus.ACTIVE  # Still active
    assert cancelled.cancel_at_period_end is True


@pytest.mark.asyncio
async def test_pause_subscription(db_session: AsyncSession) -> None:
    """Test pausing a subscription."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="pause@example.com", name="Pause Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Pause Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Pause subscription
    pause_data = SubscriptionPause(resumes_at=datetime.utcnow() + timedelta(days=30))
    paused = await subscription_service.pause_subscription(subscription.id, pause_data)
    await db_session.commit()

    assert paused.status == SubscriptionStatus.PAUSED
    assert paused.pause_resumes_at is not None


@pytest.mark.asyncio
async def test_resume_subscription(db_session: AsyncSession) -> None:
    """Test resuming a paused subscription."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Setup and pause
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="resume@example.com", name="Resume Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Resume Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    pause_data = SubscriptionPause(resumes_at=datetime.utcnow() + timedelta(days=30))
    paused = await subscription_service.pause_subscription(subscription.id, pause_data)
    await db_session.commit()

    assert paused.status == SubscriptionStatus.PAUSED

    # Resume
    resumed = await subscription_service.resume_subscription(subscription.id)
    await db_session.commit()

    assert resumed.status == SubscriptionStatus.ACTIVE
    assert resumed.pause_resumes_at is None


@pytest.mark.asyncio
async def test_change_plan_immediate(db_session: AsyncSession) -> None:
    """Test changing plan immediately with proration."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="changeplan@example.com", name="Change Plan Account")
    )

    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Old Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="New Plan", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    assert subscription.plan_id == old_plan.id

    # Change plan immediately
    plan_change = SubscriptionPlanChange(
        new_plan_id=new_plan.id,
        immediate=True,
    )
    changed = await subscription_service.change_plan(subscription.id, plan_change)
    await db_session.commit()

    assert changed.plan_id == new_plan.id
    assert changed.pending_plan_id is None


@pytest.mark.asyncio
async def test_change_plan_at_period_end(db_session: AsyncSession) -> None:
    """Test scheduling plan change at period end."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="changedelay@example.com", name="Change Delay Account")
    )

    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Current Plan", interval=PlanInterval.MONTH, amount=3000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="Future Plan", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Schedule plan change
    plan_change = SubscriptionPlanChange(
        new_plan_id=new_plan.id,
        change_at_period_end=True,
    )
    changed = await subscription_service.change_plan(subscription.id, plan_change)
    await db_session.commit()

    assert changed.plan_id == old_plan.id  # Still on old plan
    assert changed.pending_plan_id == new_plan.id  # Pending change


# API endpoint tests


@pytest.mark.asyncio
async def test_create_subscription_via_api(async_client: AsyncClient) -> None:
    """Test creating subscription via REST API."""
    # Create account first
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "subapi@example.com", "name": "Sub API Account"},
    )
    account_id = account_response.json()["id"]

    # Create plan
    plan_response = await async_client.post(
        "/v1/plans",
        json={
            "name": "API Sub Plan",
            "interval": "month",
            "amount": 1999,
            "currency": "USD",
        },
    )
    plan_id = plan_response.json()["id"]

    # Create subscription
    response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": plan_id, "quantity": 1},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["account_id"] == account_id
    assert data["plan_id"] == plan_id
    assert "id" in data


@pytest.mark.asyncio
async def test_get_subscription_via_api(async_client: AsyncClient) -> None:
    """Test retrieving subscription via REST API."""
    # Setup
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "getsubapi@example.com", "name": "Get Sub API"},
    )
    account_id = account_response.json()["id"]

    plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "Get Sub Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    plan_id = plan_response.json()["id"]

    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Get subscription
    response = await async_client.get(f"/v1/subscriptions/{subscription_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == subscription_id


@pytest.mark.asyncio
async def test_cancel_subscription_via_api(async_client: AsyncClient) -> None:
    """Test canceling subscription via REST API."""
    # Setup
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "cancelapi@example.com", "name": "Cancel API"},
    )
    account_id = account_response.json()["id"]

    plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "Cancel API Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    plan_id = plan_response.json()["id"]

    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Cancel subscription
    response = await async_client.post(
        f"/v1/subscriptions/{subscription_id}/cancel?immediate=true",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"
