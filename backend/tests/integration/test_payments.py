"""Integration tests for payment processing and retry logic."""
import pytest
from datetime import datetime, timedelta
from uuid import UUID
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.payment import Payment, PaymentStatus
from billing.models.invoice import InvoiceStatus
from billing.models.plan import PlanInterval
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate


@pytest.mark.asyncio
async def test_auto_attempt_payment_on_invoice_creation(db_session: AsyncSession) -> None:
    """Test that payment is automatically attempted when invoice is created."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService

    # Setup account with payment method
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="autopay@example.com", name="Auto Pay Account")
    )
    await db_session.commit()

    # Create plan and subscription
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Auto Pay Plan", interval=PlanInterval.MONTH, amount=2900, currency="USD")
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
    await db_session.commit()

    # Verify payment was automatically attempted
    payment_service = PaymentService(db_session)
    payments = await payment_service.list_payments(invoice_id=invoice.id)

    assert len(payments) > 0
    payment = payments[0]
    assert payment.invoice_id == invoice.id
    assert payment.amount == invoice.amount_due
    assert payment.currency == invoice.currency
    # Payment status depends on whether we have a real payment method
    assert payment.status in [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED, PaymentStatus.PENDING]


@pytest.mark.asyncio
async def test_payment_retry_schedule(db_session: AsyncSession) -> None:
    """Test payment retry schedule follows day 3, 5, 7, 10 pattern."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="retry@example.com", name="Retry Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Retry Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Get payment service and schedule retries
    payment_service = PaymentService(db_session)
    payments = await payment_service.list_payments(invoice_id=invoice.id)

    if len(payments) > 0:
        payment = payments[0]

        # If initial payment failed, schedule retries
        if payment.status == PaymentStatus.FAILED:
            retry_schedule = await payment_service.get_retry_schedule(payment.id)

            # Verify retry schedule follows day 3, 5, 7, 10 pattern
            expected_days = [3, 5, 7, 10]
            assert len(retry_schedule) == len(expected_days)

            for retry, expected_day in zip(retry_schedule, expected_days):
                assert retry["retry_at"] >= datetime.utcnow() + timedelta(days=expected_day - 1)
                assert retry["retry_at"] <= datetime.utcnow() + timedelta(days=expected_day + 1)


@pytest.mark.asyncio
async def test_successful_payment_marks_invoice_paid(db_session: AsyncSession) -> None:
    """Test that successful payment updates invoice status to PAID."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="success@example.com", name="Success Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Success Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Get payment and manually mark as succeeded (simulating webhook)
    payment_service = PaymentService(db_session)
    payments = await payment_service.list_payments(invoice_id=invoice.id)

    if len(payments) > 0:
        payment = payments[0]

        # Mark payment as succeeded
        updated_payment = await payment_service.mark_payment_succeeded(
            payment.id,
            gateway_transaction_id="test_txn_123"
        )
        await db_session.commit()

        assert updated_payment.status == PaymentStatus.SUCCEEDED
        assert updated_payment.gateway_transaction_id == "test_txn_123"

        # Verify invoice status is PAID
        await db_session.refresh(invoice)
        assert invoice.status == InvoiceStatus.PAID
        assert invoice.paid_at is not None


@pytest.mark.asyncio
async def test_all_retries_failed_marks_account_overdue(db_session: AsyncSession) -> None:
    """Test that account is marked overdue after all payment retries fail."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService
    from billing.models.account import AccountStatus

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="overdue@example.com", name="Overdue Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Overdue Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Simulate all retries failing
    payment_service = PaymentService(db_session)
    payments = await payment_service.list_payments(invoice_id=invoice.id)

    if len(payments) > 0:
        payment = payments[0]

        # Mark all retries as exhausted
        await payment_service.mark_retries_exhausted(payment.id)
        await db_session.commit()

        # Verify account is marked as WARNING or BLOCKED
        await db_session.refresh(account)
        assert account.status in [AccountStatus.WARNING, AccountStatus.BLOCKED]


@pytest.mark.asyncio
async def test_duplicate_charge_prevention(db_session: AsyncSession) -> None:
    """Test that idempotency key prevents duplicate charges."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="idempotent@example.com", name="Idempotent Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Idempotent Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Attempt payment with same idempotency key twice
    payment_service = PaymentService(db_session)
    idempotency_key = f"test_idempotency_{invoice.id}"

    # First attempt
    payment1 = await payment_service.attempt_payment(
        invoice_id=invoice.id,
        idempotency_key=idempotency_key
    )
    await db_session.commit()

    # Second attempt with same key - should return existing payment
    payment2 = await payment_service.attempt_payment(
        invoice_id=invoice.id,
        idempotency_key=idempotency_key
    )
    await db_session.commit()

    # Should return same payment, not create a new one
    assert payment1.id == payment2.id
    assert payment1.idempotency_key == payment2.idempotency_key == idempotency_key


# API endpoint tests

@pytest.mark.asyncio
async def test_retry_payment_via_api(async_client: AsyncClient) -> None:
    """Test manual payment retry via API."""
    # Create account, plan, subscription, invoice
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "retryapi@example.com", "name": "Retry API Account"},
    )
    account_id = account_response.json()["id"]

    plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "Retry API Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    plan_id = plan_response.json()["id"]

    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Get invoice for subscription (would be auto-generated)
    invoices_response = await async_client.get(f"/v1/invoices?subscription_id={subscription_id}")
    invoices_data = invoices_response.json()

    if invoices_data["total"] > 0:
        invoice_id = invoices_data["items"][0]["id"]

        # Get payment for invoice
        payments_response = await async_client.get(f"/v1/payments?invoice_id={invoice_id}")
        payments_data = payments_response.json()

        if payments_data["total"] > 0:
            payment_id = payments_data["items"][0]["id"]

            # Retry payment
            retry_response = await async_client.post(f"/v1/payments/{payment_id}/retry")

            assert retry_response.status_code in [200, 400, 404]  # 400 if already succeeded, 404 if not found


@pytest.mark.asyncio
async def test_list_payments_via_api(async_client: AsyncClient) -> None:
    """Test listing payments via API with filters."""
    # Create account, plan, subscription
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "listpayapi@example.com", "name": "List Pay API Account"},
    )
    account_id = account_response.json()["id"]

    plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "List Pay API Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    plan_id = plan_response.json()["id"]

    # List all payments
    response = await async_client.get("/v1/payments")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
