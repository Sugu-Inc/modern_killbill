"""Integration tests for credit management (User Story 9)."""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import PlanInterval
from billing.models.invoice import InvoiceStatus
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate
from billing.schemas.credit import CreditCreate


@pytest.mark.asyncio
async def test_create_credit_auto_applies_to_next_invoice(db_session: AsyncSession) -> None:
    """Test that credits automatically apply to the next generated invoice."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.credit_service import CreditService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="credits1@example.com", name="Credits Account 1")
    )

    # Create plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Standard Plan",
            interval=PlanInterval.MONTH,
            amount=5000,  # $50
            currency="USD",
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Apply a $20 credit to the account
    credit_service = CreditService(db_session)
    credit = await credit_service.create_credit(
        CreditCreate(
            account_id=account.id,
            amount=2000,  # $20
            currency="USD",
            reason="Customer satisfaction goodwill credit",
        )
    )
    await db_session.commit()

    assert credit.id is not None
    assert credit.account_id == account.id
    assert credit.amount == 2000
    assert credit.applied_to_invoice_id is None  # Not yet applied

    # Generate invoice for the subscription
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Verify credit was auto-applied to invoice
    await db_session.refresh(credit)
    await db_session.refresh(invoice)

    assert credit.applied_to_invoice_id == invoice.id
    assert invoice.status == InvoiceStatus.OPEN

    # Invoice should be $50 - $20 credit = $30
    assert invoice.subtotal == 5000  # Original amount
    assert invoice.amount_due == 3000  # After credit applied


@pytest.mark.asyncio
async def test_void_invoice_creates_credit(db_session: AsyncSession) -> None:
    """Test that voiding a paid invoice creates a credit for the account."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService
    from billing.services.credit_service import CreditService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="void@example.com", name="Void Account")
    )

    # Create plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Premium Plan",
            interval=PlanInterval.MONTH,
            amount=10000,  # $100
            currency="USD",
        )
    )
    await db_session.commit()

    # Create subscription and generate invoice
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Pay the invoice
    payment_service = PaymentService(db_session)
    payment = await payment_service.attempt_payment(
        invoice_id=invoice.id,
        payment_method_id=None,  # Mock payment
    )
    await db_session.commit()

    await db_session.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID

    # Void the invoice (refund scenario)
    voided_invoice = await invoice_service.void_invoice(invoice.id, reason="Refund requested")
    await db_session.commit()

    assert voided_invoice.status == InvoiceStatus.VOID

    # Verify credit was created
    credit_service = CreditService(db_session)
    credits = await credit_service.get_available_credits_for_account(account.id)

    assert len(credits) >= 1
    refund_credit = credits[0]
    assert refund_credit.amount == 10000  # Full invoice amount
    assert refund_credit.reason is not None
    assert "void" in refund_credit.reason.lower() or "refund" in refund_credit.reason.lower()


@pytest.mark.asyncio
async def test_credit_reduces_invoice_balance(db_session: AsyncSession) -> None:
    """Test that credit correctly reduces the invoice balance."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.credit_service import CreditService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="balance@example.com", name="Balance Account")
    )

    # Create plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Basic Plan",
            interval=PlanInterval.MONTH,
            amount=3000,  # $30
            currency="USD",
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Apply multiple credits totaling $25
    credit_service = CreditService(db_session)

    credit1 = await credit_service.create_credit(
        CreditCreate(
            account_id=account.id,
            amount=1500,  # $15
            currency="USD",
            reason="First credit",
        )
    )

    credit2 = await credit_service.create_credit(
        CreditCreate(
            account_id=account.id,
            amount=1000,  # $10
            currency="USD",
            reason="Second credit",
        )
    )
    await db_session.commit()

    # Generate invoice - should apply credits in order
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    await db_session.refresh(invoice)
    await db_session.refresh(credit1)
    await db_session.refresh(credit2)

    # Invoice $30 - $15 credit1 - $10 credit2 = $5
    assert invoice.subtotal == 3000
    assert invoice.amount_due == 500  # $5 remaining

    # Both credits should be applied
    assert credit1.applied_to_invoice_id == invoice.id
    assert credit2.applied_to_invoice_id == invoice.id


@pytest.mark.asyncio
async def test_partial_credit_application(db_session: AsyncSession) -> None:
    """Test that large credit partially applies and leaves balance for future invoices."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.credit_service import CreditService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="partial@example.com", name="Partial Credit Account")
    )

    # Create plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Small Plan",
            interval=PlanInterval.MONTH,
            amount=1000,  # $10
            currency="USD",
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Apply large credit ($50) - more than invoice amount
    credit_service = CreditService(db_session)
    large_credit = await credit_service.create_credit(
        CreditCreate(
            account_id=account.id,
            amount=5000,  # $50
            currency="USD",
            reason="Large promotional credit",
        )
    )
    await db_session.commit()

    # Generate invoice - should apply partial credit
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    await db_session.refresh(invoice)

    # Invoice should be fully covered by credit
    assert invoice.subtotal == 1000
    assert invoice.amount_due == 0  # Fully covered

    # Verify remaining credit balance
    available_credits = await credit_service.get_available_credits_for_account(account.id)
    total_available = sum(c.amount for c in available_credits if c.applied_to_invoice_id is None)

    # Should have $40 remaining credit
    assert total_available == 4000


@pytest.mark.asyncio
async def test_expired_credits_not_applied(db_session: AsyncSession) -> None:
    """Test that expired credits are not applied to invoices."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.credit_service import CreditService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="expired@example.com", name="Expired Credit Account")
    )

    # Create plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Test Plan",
            interval=PlanInterval.MONTH,
            amount=2000,  # $20
            currency="USD",
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Create expired credit
    credit_service = CreditService(db_session)
    expired_credit = await credit_service.create_credit(
        CreditCreate(
            account_id=account.id,
            amount=1000,  # $10
            currency="USD",
            reason="Expired promotional credit",
            expires_at=datetime.utcnow() - timedelta(days=1),  # Expired yesterday
        )
    )
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    await db_session.refresh(invoice)
    await db_session.refresh(expired_credit)

    # Expired credit should NOT be applied
    assert expired_credit.applied_to_invoice_id is None
    assert invoice.amount_due == 2000  # Full amount, no credit applied


# API endpoint tests


@pytest.mark.asyncio
async def test_create_credit_via_api(async_client: AsyncClient) -> None:
    """Test creating credits via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "apicredit@example.com", "name": "API Credit Account"},
    )
    account_id = account_response.json()["id"]

    # Create credit
    credit_response = await async_client.post(
        "/v1/credits",
        json={
            "account_id": account_id,
            "amount": 2500,
            "currency": "USD",
            "reason": "Support ticket resolution credit",
        },
    )

    assert credit_response.status_code == 201
    credit_data = credit_response.json()
    assert credit_data["account_id"] == account_id
    assert credit_data["amount"] == 2500
    assert credit_data["reason"] == "Support ticket resolution credit"
    assert credit_data["applied_to_invoice_id"] is None


@pytest.mark.asyncio
async def test_get_account_credits_via_api(async_client: AsyncClient) -> None:
    """Test retrieving account credits via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "getcredits@example.com", "name": "Get Credits Account"},
    )
    account_id = account_response.json()["id"]

    # Create multiple credits
    for i in range(3):
        await async_client.post(
            "/v1/credits",
            json={
                "account_id": account_id,
                "amount": 1000 * (i + 1),
                "currency": "USD",
                "reason": f"Credit {i+1}",
            },
        )

    # Get account credits
    credits_response = await async_client.get(f"/v1/accounts/{account_id}/credits")

    assert credits_response.status_code == 200
    credits_data = credits_response.json()
    assert "items" in credits_data
    assert len(credits_data["items"]) == 3
    assert credits_data["items"][0]["amount"] == 1000
    assert credits_data["items"][1]["amount"] == 2000
    assert credits_data["items"][2]["amount"] == 3000


@pytest.mark.asyncio
async def test_get_account_credit_balance_via_api(async_client: AsyncClient) -> None:
    """Test retrieving account credit balance via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "balance_api@example.com", "name": "Balance API Account"},
    )
    account_id = account_response.json()["id"]

    # Create credits
    await async_client.post(
        "/v1/credits",
        json={
            "account_id": account_id,
            "amount": 5000,
            "currency": "USD",
            "reason": "Available credit",
        },
    )

    # Get credit balance
    balance_response = await async_client.get(f"/v1/accounts/{account_id}/credits/balance")

    assert balance_response.status_code == 200
    balance_data = balance_response.json()
    assert balance_data["account_id"] == account_id
    assert balance_data["available_credits"] >= 5000
    assert balance_data["currency"] == "USD"
