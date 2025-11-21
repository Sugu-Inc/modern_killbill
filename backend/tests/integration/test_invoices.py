"""Integration tests for invoice generation and management."""
import pytest
from datetime import datetime, timedelta
from uuid import UUID
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.plan import PlanInterval
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate
from billing.schemas.invoice import InvoiceVoid


@pytest.mark.asyncio
async def test_auto_generate_invoice_from_subscription(db_session: AsyncSession) -> None:
    """Test automatically generating an invoice from a subscription."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="invoice@example.com", name="Invoice Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Invoice Plan", interval=PlanInterval.MONTH, amount=2900, currency="USD")
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

    assert invoice.id is not None
    assert isinstance(invoice.id, UUID)
    assert invoice.account_id == account.id
    assert invoice.subscription_id == subscription.id
    assert invoice.status == InvoiceStatus.OPEN
    assert invoice.amount_due > 0
    assert invoice.currency == "USD"
    assert len(invoice.line_items) > 0
    assert invoice.number.startswith("INV-")


@pytest.mark.asyncio
async def test_invoice_number_sequential(db_session: AsyncSession) -> None:
    """Test that invoice numbers are sequential."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup multiple subscriptions
    account_service = AccountService(db_session)
    plan_service = PlanService(db_session)
    subscription_service = SubscriptionService(db_session)
    invoice_service = InvoiceService(db_session)

    account = await account_service.create_account(
        AccountCreate(email="sequential@example.com", name="Sequential Account")
    )

    plan = await plan_service.create_plan(
        PlanCreate(name="Seq Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create multiple subscriptions and invoices
    invoice_numbers = []
    for i in range(3):
        subscription = await subscription_service.create_subscription(
            SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
        )
        invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
        await db_session.commit()
        invoice_numbers.append(invoice.number)

    # Verify sequential numbering
    assert len(invoice_numbers) == 3
    assert all(num.startswith("INV-") for num in invoice_numbers)
    # Extract numbers and verify they increment
    nums = [int(n.split("-")[1]) for n in invoice_numbers]
    assert nums == sorted(nums)


@pytest.mark.asyncio
async def test_proration_on_mid_cycle_upgrade(db_session: AsyncSession) -> None:
    """Test proration calculation when upgrading mid-cycle."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="prorate@example.com", name="Prorate Account")
    )

    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Basic", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="Pro", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Calculate proration
    invoice_service = InvoiceService(db_session)
    change_date = datetime.utcnow()
    proration = await invoice_service.calculate_proration(
        old_amount=1000,
        new_amount=2000,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        change_date=change_date,
    )

    assert "credit" in proration
    assert "charge" in proration
    assert "net" in proration
    assert proration["net"] == proration["charge"] - proration["credit"]
    # Upgrade should result in positive net (more to pay)
    assert proration["net"] >= 0


@pytest.mark.asyncio
async def test_proration_on_mid_cycle_downgrade(db_session: AsyncSession) -> None:
    """Test proration calculation when downgrading mid-cycle."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="downgrade@example.com", name="Downgrade Account")
    )

    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Pro", interval=PlanInterval.MONTH, amount=2000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="Basic", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Calculate proration
    invoice_service = InvoiceService(db_session)
    change_date = datetime.utcnow()
    proration = await invoice_service.calculate_proration(
        old_amount=2000,
        new_amount=1000,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        change_date=change_date,
    )

    # Downgrade should result in negative or zero net (credit owed)
    assert proration["net"] <= 0


@pytest.mark.asyncio
async def test_create_proration_invoice(db_session: AsyncSession) -> None:
    """Test creating a prorated invoice for plan change."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="prorateinv@example.com", name="Prorate Invoice Account")
    )

    plan_service = PlanService(db_session)
    old_plan = await plan_service.create_plan(
        PlanCreate(name="Old", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    new_plan = await plan_service.create_plan(
        PlanCreate(name="New", interval=PlanInterval.MONTH, amount=1500, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=old_plan.id, quantity=1)
    )
    await db_session.commit()

    # Create proration invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.create_proration_invoice(
        subscription=subscription,
        old_plan=old_plan,
        new_plan=new_plan,
        change_date=datetime.utcnow(),
    )
    await db_session.commit()

    assert invoice.id is not None
    assert invoice.subscription_id == subscription.id
    assert invoice.extra_metadata.get("proration") is True
    assert len(invoice.line_items) > 0


@pytest.mark.asyncio
async def test_void_invoice(db_session: AsyncSession) -> None:
    """Test voiding an unpaid invoice."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup and create invoice
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="void@example.com", name="Void Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Void Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    assert invoice.status == InvoiceStatus.OPEN

    # Void invoice
    voided = await invoice_service.void_invoice(invoice.id, "Customer cancelled before payment")
    await db_session.commit()

    assert voided.status == InvoiceStatus.VOID
    assert voided.voided_at is not None
    assert voided.extra_metadata.get("void_reason") == "Customer cancelled before payment"


@pytest.mark.asyncio
async def test_cannot_void_paid_invoice(db_session: AsyncSession) -> None:
    """Test that paid invoices cannot be voided."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup and create invoice
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="paidvoid@example.com", name="Paid Void Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="Paid Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )

    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)

    # Mark as paid
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.utcnow()
    await db_session.commit()

    # Try to void - should raise error
    with pytest.raises(ValueError, match="paid"):
        await invoice_service.void_invoice(invoice.id, "Test")


@pytest.mark.asyncio
async def test_list_invoices(db_session: AsyncSession) -> None:
    """Test listing invoices with filtering."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService

    # Setup
    account_service = AccountService(db_session)
    account1 = await account_service.create_account(
        AccountCreate(email="list1@example.com", name="List Account 1")
    )
    account2 = await account_service.create_account(
        AccountCreate(email="list2@example.com", name="List Account 2")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(name="List Plan", interval=PlanInterval.MONTH, amount=1000, currency="USD")
    )
    await db_session.commit()

    # Create subscriptions and invoices
    subscription_service = SubscriptionService(db_session)
    invoice_service = InvoiceService(db_session)

    sub1 = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account1.id, plan_id=plan.id, quantity=1)
    )
    inv1 = await invoice_service.generate_invoice_for_subscription(sub1.id)

    sub2 = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account2.id, plan_id=plan.id, quantity=1)
    )
    inv2 = await invoice_service.generate_invoice_for_subscription(sub2.id)
    await db_session.commit()

    # List all invoices
    invoices, total = await invoice_service.list_invoices()
    assert total >= 2

    # Filter by account
    invoices, total = await invoice_service.list_invoices(account_id=account1.id)
    invoice_ids = [inv.id for inv in invoices]
    assert inv1.id in invoice_ids
    assert inv2.id not in invoice_ids


# API endpoint tests


@pytest.mark.asyncio
async def test_list_invoices_via_api(async_client: AsyncClient) -> None:
    """Test listing invoices via REST API."""
    # Create account, plan, subscription, which auto-generates invoice
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "listinvapi@example.com", "name": "List Inv API"},
    )
    account_id = account_response.json()["id"]

    plan_response = await async_client.post(
        "/v1/plans",
        json={"name": "List Inv Plan", "interval": "month", "amount": 1000, "currency": "USD"},
    )
    plan_id = plan_response.json()["id"]

    # Note: In reality, invoices are generated by background workers
    # For this test, we're just checking the endpoint structure
    response = await async_client.get(f"/v1/invoices?account_id={account_id}")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_void_invoice_via_api(async_client: AsyncClient) -> None:
    """Test voiding invoice via REST API."""
    # This test assumes we have a way to create an invoice
    # In a real scenario, we'd need to create account -> plan -> subscription
    # and then manually generate an invoice or trigger the billing cycle

    # For now, we'll test the endpoint structure with a mock
    response = await async_client.post(
        "/v1/invoices/00000000-0000-0000-0000-000000000000/void",
        json={"reason": "Test void"},
    )

    # Should return 404 since invoice doesn't exist
    assert response.status_code == 404
