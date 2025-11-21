"""Integration tests for dunning process (User Story 8)."""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.account import AccountStatus
from billing.models.invoice import InvoiceStatus
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate


@pytest.mark.asyncio
async def test_3_day_reminder_sent(db_session: AsyncSession) -> None:
    """Test that a reminder is sent 3 days after invoice becomes overdue."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.dunning_service import DunningService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="reminder@example.com", name="Reminder Account")
    )

    # Create plan and subscription
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Test Plan", interval="month", amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)

    # Simulate invoice being 3 days overdue
    invoice.due_date = datetime.utcnow() - timedelta(days=3)
    invoice.status = InvoiceStatus.OPEN
    await db_session.commit()

    # Run dunning process
    dunning_service = DunningService(db_session)
    notifications = await dunning_service.check_overdue_invoices()
    await db_session.commit()

    # Verify reminder was sent
    assert len(notifications) >= 1
    reminder = next((n for n in notifications if n["type"] == "reminder"), None)
    assert reminder is not None
    assert reminder["invoice_id"] == invoice.id
    assert reminder["days_overdue"] == 3
    assert "reminder" in reminder["message"].lower()

    # Account status should still be ACTIVE
    await db_session.refresh(account)
    assert account.status == AccountStatus.ACTIVE


@pytest.mark.asyncio
async def test_7_day_warning_with_account_warning_status(db_session: AsyncSession) -> None:
    """Test that a warning is sent and account status changes to WARNING at 7 days."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.dunning_service import DunningService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="warning@example.com", name="Warning Account")
    )

    # Create plan and subscription
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Test Plan", interval="month", amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)

    # Simulate invoice being 7 days overdue
    invoice.due_date = datetime.utcnow() - timedelta(days=7)
    invoice.status = InvoiceStatus.OPEN
    await db_session.commit()

    # Run dunning process
    dunning_service = DunningService(db_session)
    notifications = await dunning_service.check_overdue_invoices()
    await db_session.commit()

    # Verify warning was sent
    assert len(notifications) >= 1
    warning = next((n for n in notifications if n["type"] == "warning"), None)
    assert warning is not None
    assert warning["invoice_id"] == invoice.id
    assert warning["days_overdue"] == 7
    assert "warning" in warning["message"].lower()

    # Account status should be WARNING
    await db_session.refresh(account)
    assert account.status == AccountStatus.WARNING


@pytest.mark.asyncio
async def test_14_day_service_blocking(db_session: AsyncSession) -> None:
    """Test that account is blocked after 14 days of non-payment."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.dunning_service import DunningService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="blocked@example.com", name="Blocked Account")
    )

    # Create plan and subscription
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Test Plan", interval="month", amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)

    # Simulate invoice being 14 days overdue
    invoice.due_date = datetime.utcnow() - timedelta(days=14)
    invoice.status = InvoiceStatus.OPEN
    await db_session.commit()

    # Run dunning process
    dunning_service = DunningService(db_session)
    notifications = await dunning_service.check_overdue_invoices()
    await db_session.commit()

    # Verify blocking notification was sent
    assert len(notifications) >= 1
    block_notice = next((n for n in notifications if n["type"] == "service_blocked"), None)
    assert block_notice is not None
    assert block_notice["invoice_id"] == invoice.id
    assert block_notice["days_overdue"] == 14

    # Account status should be BLOCKED
    await db_session.refresh(account)
    assert account.status == AccountStatus.BLOCKED


@pytest.mark.asyncio
async def test_payment_unblocks_account(db_session: AsyncSession) -> None:
    """Test that paying an overdue invoice unblocks the account."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService
    from billing.services.dunning_service import DunningService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="unblock@example.com", name="Unblock Account")
    )

    # Create plan and subscription
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Test Plan", interval="month", amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)

    # Simulate invoice being 14 days overdue and account blocked
    invoice.due_date = datetime.utcnow() - timedelta(days=14)
    invoice.status = InvoiceStatus.OPEN
    account.status = AccountStatus.BLOCKED
    await db_session.commit()

    # Process payment
    payment_service = PaymentService(db_session)
    payment = await payment_service.attempt_payment(
        invoice_id=invoice.id,
        idempotency_key=f"unblock_payment_{uuid4()}",
    )

    # Mark payment as succeeded
    await payment_service.mark_payment_succeeded(
        payment.id,
        gateway_transaction_id="test_unblock_123"
    )
    await db_session.commit()

    # Run dunning service to check for unblocking
    dunning_service = DunningService(db_session)
    await dunning_service.unblock_on_payment(account.id)
    await db_session.commit()

    # Account should be unblocked
    await db_session.refresh(account)
    assert account.status == AccountStatus.ACTIVE


@pytest.mark.asyncio
async def test_multiple_overdue_invoices_escalation(db_session: AsyncSession) -> None:
    """Test dunning process escalation with multiple overdue invoices."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.dunning_service import DunningService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="multi@example.com", name="Multi Overdue")
    )

    # Create plan and subscription
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Test Plan", interval="month", amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice service
    invoice_service = InvoiceService(db_session)

    # Create multiple invoices with different overdue periods
    invoice1 = await invoice_service.generate_invoice_for_subscription(subscription.id)
    invoice1.due_date = datetime.utcnow() - timedelta(days=5)  # 5 days overdue
    invoice1.status = InvoiceStatus.OPEN

    # Manually create second invoice (simulate next billing period)
    from billing.models.invoice import Invoice
    invoice_number2 = await invoice_service.generate_invoice_number()
    invoice2 = Invoice(
        account_id=account.id,
        subscription_id=subscription.id,
        number=invoice_number2,
        status=InvoiceStatus.OPEN,
        amount_due=1000,
        amount_paid=0,
        tax=0,
        currency="USD",
        due_date=datetime.utcnow() - timedelta(days=3),  # 3 days overdue
        line_items=[],
    )
    db_session.add(invoice2)
    await db_session.commit()

    # Run dunning process
    dunning_service = DunningService(db_session)
    notifications = await dunning_service.check_overdue_invoices()
    await db_session.commit()

    # Should send notifications for both invoices
    assert len(notifications) >= 2

    # Most overdue invoice should determine account status
    # 5 days overdue -> should still be in reminder stage
    await db_session.refresh(account)
    assert account.status == AccountStatus.ACTIVE  # Not yet at WARNING (7 days)


# API endpoint tests (if dunning status/history endpoints exist)


@pytest.mark.asyncio
async def test_dunning_prevents_new_subscriptions_when_blocked(db_session: AsyncSession) -> None:
    """Test that blocked accounts cannot create new subscriptions."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    # Create blocked account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="blocked_new@example.com", name="Blocked New Sub")
    )
    account.status = AccountStatus.BLOCKED
    await db_session.commit()

    # Create plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Test Plan", interval="month", amount=1000, currency="USD")
    )
    await db_session.commit()

    # Attempt to create subscription
    subscription_service = SubscriptionService(db_session)

    with pytest.raises(ValueError, match="blocked|cannot create"):
        await subscription_service.create_subscription(
            SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
        )
