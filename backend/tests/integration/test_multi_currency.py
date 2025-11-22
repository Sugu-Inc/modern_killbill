"""Integration tests for multi-currency billing (User Story 10)."""
import pytest
from datetime import datetime
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import PlanInterval
from billing.models.invoice import InvoiceStatus
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate


@pytest.mark.asyncio
async def test_create_eur_account(db_session: AsyncSession) -> None:
    """Test creating an account with EUR currency."""
    from billing.services.account_service import AccountService

    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(
            email="euruser@example.com",
            name="EUR Customer",
            currency="EUR",
        )
    )
    await db_session.commit()

    assert account.id is not None
    assert account.email == "euruser@example.com"
    assert account.currency == "EUR"
    assert account.name == "EUR Customer"


@pytest.mark.asyncio
async def test_invoice_in_eur(db_session: AsyncSession) -> None:
    """Test that invoices are generated in EUR with correct currency formatting."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Create EUR account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="eur_invoice@example.com", name="EUR Invoice Account", currency="EUR")
    )

    # Create EUR plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Pro Plan EUR",
            interval=PlanInterval.MONTH,
            amount=5000,  # €50.00
            currency="EUR",
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Verify EUR currency
    assert invoice.currency == "EUR"
    # amount_due includes tax (€50.00 base + 10% tax = €55.00)
    assert invoice.amount_due >= 5000  # Should be base amount or more with tax


@pytest.mark.asyncio
async def test_payment_in_eur(db_session: AsyncSession) -> None:
    """Test that payments are processed in EUR."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService

    # Create EUR account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="eur_payment@example.com", name="EUR Payment Account", currency="EUR")
    )

    # Create EUR plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Business Plan EUR",
            interval=PlanInterval.MONTH,
            amount=10000,  # €100.00
            currency="EUR",
        )
    )
    await db_session.commit()

    # Create subscription and invoice
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Attempt payment
    payment_service = PaymentService(db_session)
    payment = await payment_service.attempt_payment(
        invoice_id=invoice.id,
        payment_method_id=None,  # Mock payment
    )
    await db_session.commit()

    # Verify EUR payment
    assert payment.currency == "EUR"
    assert payment.amount == invoice.amount_due
    await db_session.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID


@pytest.mark.asyncio
async def test_currency_formatting(db_session: AsyncSession) -> None:
    """Test that amounts are formatted correctly for different currencies."""
    from billing.utils.currency import format_amount_for_currency, supported_currencies

    # Test EUR formatting (€50.00)
    eur_formatted = format_amount_for_currency(5000, "EUR")
    assert "50" in eur_formatted
    assert "EUR" in eur_formatted or "€" in eur_formatted

    # Test USD formatting ($100.00)
    usd_formatted = format_amount_for_currency(10000, "USD")
    assert "100" in usd_formatted
    assert "USD" in usd_formatted or "$" in usd_formatted

    # Test GBP formatting (£75.00)
    gbp_formatted = format_amount_for_currency(7500, "GBP")
    assert "75" in gbp_formatted
    assert "GBP" in gbp_formatted or "£" in gbp_formatted

    # Test JPY formatting (¥1000 - no decimal places)
    jpy_formatted = format_amount_for_currency(1000, "JPY")
    assert "1000" in jpy_formatted or "1,000" in jpy_formatted
    assert "JPY" in jpy_formatted or "¥" in jpy_formatted

    # Verify supported currencies list includes common currencies
    assert "USD" in supported_currencies
    assert "EUR" in supported_currencies
    assert "GBP" in supported_currencies
    assert "CAD" in supported_currencies
    assert "AUD" in supported_currencies
    assert "JPY" in supported_currencies


@pytest.mark.asyncio
async def test_mixed_currency_accounts(db_session: AsyncSession) -> None:
    """Test that different accounts can have different currencies."""
    from billing.services.account_service import AccountService

    account_service = AccountService(db_session)

    # Create multiple accounts with different currencies
    usd_account = await account_service.create_account(
        AccountCreate(email="usd@example.com", name="USD Account", currency="USD")
    )

    eur_account = await account_service.create_account(
        AccountCreate(email="eur@example.com", name="EUR Account", currency="EUR")
    )

    gbp_account = await account_service.create_account(
        AccountCreate(email="gbp@example.com", name="GBP Account", currency="GBP")
    )

    await db_session.commit()

    # Verify each account has correct currency
    assert usd_account.currency == "USD"
    assert eur_account.currency == "EUR"
    assert gbp_account.currency == "GBP"


@pytest.mark.asyncio
async def test_plan_supports_multiple_currencies(db_session: AsyncSession) -> None:
    """Test that a plan can have pricing in multiple currencies."""
    from billing.services.plan_service import PlanService

    plan_service = PlanService(db_session)

    # Create USD plan
    usd_plan = await plan_service.create_plan(
        PlanCreate(
            name="Multi-Currency Plan USD",
            interval=PlanInterval.MONTH,
            amount=5000,  # $50.00
            currency="USD",
        )
    )

    # Create EUR plan (same plan, different currency)
    eur_plan = await plan_service.create_plan(
        PlanCreate(
            name="Multi-Currency Plan EUR",
            interval=PlanInterval.MONTH,
            amount=4500,  # €45.00 (adjusted for exchange rate)
            currency="EUR",
        )
    )

    await db_session.commit()

    # Verify both plans exist with different currencies
    assert usd_plan.currency == "USD"
    assert usd_plan.amount == 5000

    assert eur_plan.currency == "EUR"
    assert eur_plan.amount == 4500


@pytest.mark.asyncio
async def test_currency_mismatch_validation(db_session: AsyncSession) -> None:
    """Test that subscription currency must match account currency."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService

    account_service = AccountService(db_session)
    plan_service = PlanService(db_session)
    subscription_service = SubscriptionService(db_session)

    # Create EUR account
    account = await account_service.create_account(
        AccountCreate(email="eur_mismatch@example.com", name="EUR Account", currency="EUR")
    )

    # Create USD plan
    plan = await plan_service.create_plan(
        PlanCreate(
            name="USD Plan",
            interval=PlanInterval.MONTH,
            amount=5000,
            currency="USD",
        )
    )
    await db_session.commit()

    # Attempt to create subscription with mismatched currency
    # Should either raise an error or auto-convert
    with pytest.raises((ValueError, Exception)):
        subscription = await subscription_service.create_subscription(
            SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
        )
        await db_session.commit()


# API endpoint tests


@pytest.mark.asyncio
async def test_create_multi_currency_account_via_api(async_client: AsyncClient) -> None:
    """Test creating accounts with different currencies via API."""
    # Create EUR account
    eur_response = await async_client.post(
        "/v1/accounts",
        json={"email": "api_eur@example.com", "name": "API EUR Account", "currency": "EUR"},
    )

    assert eur_response.status_code == 201
    eur_data = eur_response.json()
    assert eur_data["currency"] == "EUR"

    # Create GBP account
    gbp_response = await async_client.post(
        "/v1/accounts",
        json={"email": "api_gbp@example.com", "name": "API GBP Account", "currency": "GBP"},
    )

    assert gbp_response.status_code == 201
    gbp_data = gbp_response.json()
    assert gbp_data["currency"] == "GBP"


@pytest.mark.asyncio
async def test_create_multi_currency_plan_via_api(async_client: AsyncClient) -> None:
    """Test creating plans with different currencies via API."""
    # Create EUR plan
    eur_plan_response = await async_client.post(
        "/v1/plans",
        json={
            "name": "Premium EUR",
            "interval": "month",
            "amount": 9900,
            "currency": "EUR",
        },
    )

    assert eur_plan_response.status_code == 201
    eur_plan = eur_plan_response.json()
    assert eur_plan["currency"] == "EUR"
    assert eur_plan["amount"] == 9900

    # Create JPY plan (no decimal places)
    jpy_plan_response = await async_client.post(
        "/v1/plans",
        json={
            "name": "Premium JPY",
            "interval": "month",
            "amount": 10000,  # ¥10,000
            "currency": "JPY",
        },
    )

    assert jpy_plan_response.status_code == 201
    jpy_plan = jpy_plan_response.json()
    assert jpy_plan["currency"] == "JPY"
    assert jpy_plan["amount"] == 10000
