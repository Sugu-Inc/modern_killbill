"""Integration tests for usage-based billing (User Story 7)."""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import PlanInterval
from billing.models.invoice import InvoiceStatus
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate, PlanTier
from billing.schemas.subscription import SubscriptionCreate
from billing.schemas.usage_record import UsageRecordCreate


@pytest.mark.asyncio
async def test_submit_usage_event_with_idempotency(db_session: AsyncSession) -> None:
    """Test that usage events can be submitted with idempotency keys."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.usage_service import UsageService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="usage1@example.com", name="Usage Account 1")
    )

    # Create usage-based plan with tiered pricing
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="API Calls Plan",
            interval=PlanInterval.MONTH,
            amount=0,  # Base price
            currency="USD",
            usage_type="metered",
            tiers=[
                PlanTier(up_to=1000, unit_amount=10),  # $0.10 per call up to 1000
                PlanTier(up_to=10000, unit_amount=5),  # $0.05 per call from 1001-10000
                PlanTier(up_to=None, unit_amount=2),   # $0.02 per call beyond 10000
            ],
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Submit usage event
    usage_service = UsageService(db_session)
    idempotency_key = f"usage_{uuid4()}"

    usage_record = await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=500,
            timestamp=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
    )
    await db_session.commit()

    assert usage_record.id is not None
    assert usage_record.subscription_id == subscription.id
    assert usage_record.metric == "api_calls"
    assert usage_record.quantity == 500
    assert usage_record.idempotency_key == idempotency_key


@pytest.mark.asyncio
async def test_duplicate_usage_events_ignored(db_session: AsyncSession) -> None:
    """Test that duplicate usage events with same idempotency key are ignored."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.usage_service import UsageService

    # Setup
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="dedup@example.com", name="Dedup Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="API Plan",
            interval=PlanInterval.MONTH,
            amount=0,
            currency="USD",
            usage_type="metered",
        )
    )
    await db_session.commit()

    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Submit usage event
    usage_service = UsageService(db_session)
    idempotency_key = f"dedup_{uuid4()}"

    first_record = await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=100,
            timestamp=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
    )
    await db_session.commit()

    # Submit duplicate event with same idempotency key
    second_record = await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=200,  # Different quantity (should be ignored)
            timestamp=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
    )
    await db_session.commit()

    # Should return the original record
    assert second_record.id == first_record.id
    assert second_record.quantity == 100  # Original quantity, not 200


@pytest.mark.asyncio
async def test_usage_charge_calculation_with_tiers(db_session: AsyncSession) -> None:
    """Test that tiered usage charges are calculated correctly on invoices."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.usage_service import UsageService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="tiers@example.com", name="Tiers Account")
    )

    # Create tiered usage plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Tiered API Plan",
            interval=PlanInterval.MONTH,
            amount=1000,  # $10 base fee
            currency="USD",
            usage_type="metered",
            tiers=[
                PlanTier(up_to=1000, unit_amount=10),   # $0.10 per call (0-1000)
                PlanTier(up_to=5000, unit_amount=5),    # $0.05 per call (1001-5000)
                PlanTier(up_to=None, unit_amount=2),    # $0.02 per call (5001+)
            ],
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Submit usage events totaling 7500 API calls
    # Tier 1: 1000 calls @ $0.10 = $100
    # Tier 2: 4000 calls @ $0.05 = $200
    # Tier 3: 2500 calls @ $0.02 = $50
    # Total usage charge: $350
    usage_service = UsageService(db_session)

    # Submit in batches
    await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=3000,
            timestamp=subscription.current_period_start + timedelta(days=5),
            idempotency_key=f"usage_{uuid4()}",
        )
    )

    await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=4500,
            timestamp=subscription.current_period_start + timedelta(days=15),
            idempotency_key=f"usage_{uuid4()}",
        )
    )
    await db_session.commit()

    # Generate invoice for the subscription
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Verify invoice includes base charge + tiered usage charges
    # Base: $10, Usage: $350 = Total: $360 (before tax)
    assert invoice.status == InvoiceStatus.OPEN

    # Check line items
    line_items = invoice.line_items
    assert len(line_items) >= 2  # Base subscription + usage charges

    # Find usage line item
    usage_line_item = None
    for item in line_items:
        if item.get("type") == "usage":
            usage_line_item = item
            break

    assert usage_line_item is not None
    assert usage_line_item["quantity"] == 7500  # Total API calls

    # Expected usage charge: $350 (35000 cents)
    # Tier 1: 1000 * 10 = 10000
    # Tier 2: 4000 * 5 = 20000
    # Tier 3: 2500 * 2 = 5000
    expected_usage_amount = 35000
    assert usage_line_item["amount"] == expected_usage_amount


@pytest.mark.asyncio
async def test_late_usage_generates_supplemental_invoice(db_session: AsyncSession) -> None:
    """Test that usage arriving after period close generates supplemental invoice."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.usage_service import UsageService
    from billing.services.invoice_service import InvoiceService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="late@example.com", name="Late Usage Account")
    )

    # Create usage plan
    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Late Usage Plan",
            interval=PlanInterval.MONTH,
            amount=500,
            currency="USD",
            usage_type="metered",
            tiers=[PlanTier(up_to=None, unit_amount=10)],
        )
    )
    await db_session.commit()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Generate invoice for the period (closes the period)
    invoice_service = InvoiceService(db_session)
    initial_invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    initial_invoice_count = len(
        (await invoice_service.list_invoices(subscription_id=subscription.id))[0]
    )

    # Submit late usage (after period already closed)
    usage_service = UsageService(db_session)
    late_timestamp = subscription.current_period_start + timedelta(days=20)  # Within closed period

    await usage_service.record_usage(
        UsageRecordCreate(
            subscription_id=subscription.id,
            metric="api_calls",
            quantity=1000,
            timestamp=late_timestamp,
            idempotency_key=f"late_{uuid4()}",
        )
    )
    await db_session.commit()

    # Process late usage (normally done by background worker)
    supplemental_invoice = await usage_service.process_late_usage(subscription.id)
    await db_session.commit()

    # Verify supplemental invoice created
    assert supplemental_invoice is not None
    assert supplemental_invoice.extra_metadata.get("supplemental") is True
    assert supplemental_invoice.extra_metadata.get("late_usage") is True

    # Verify new invoice was created
    final_invoice_count = len(
        (await invoice_service.list_invoices(subscription_id=subscription.id))[0]
    )
    assert final_invoice_count == initial_invoice_count + 1


# API endpoint tests


@pytest.mark.asyncio
async def test_submit_usage_via_api(async_client: AsyncClient) -> None:
    """Test submitting usage events via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "apiusage@example.com", "name": "API Usage"},
    )
    account_id = account_response.json()["id"]

    # Create usage-based plan
    plan_response = await async_client.post(
        "/v1/plans",
        json={
            "name": "API Usage Plan",
            "interval": "month",
            "amount": 0,
            "currency": "USD",
            "usage_type": "metered",
            "tiers": [{"up_to": None, "unit_amount": 10}],
        },
    )
    plan_id = plan_response.json()["id"]

    # Create subscription
    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Submit usage event
    idempotency_key = f"api_usage_{uuid4()}"
    usage_response = await async_client.post(
        "/v1/usage",
        json={
            "subscription_id": subscription_id,
            "metric": "api_calls",
            "quantity": 500,
            "timestamp": datetime.utcnow().isoformat(),
            "idempotency_key": idempotency_key,
        },
    )

    assert usage_response.status_code == 201
    data = usage_response.json()
    assert data["subscription_id"] == subscription_id
    assert data["quantity"] == 500
    assert data["idempotency_key"] == idempotency_key


@pytest.mark.asyncio
async def test_query_usage_for_period_via_api(async_client: AsyncClient) -> None:
    """Test querying usage for a billing period via REST API."""
    # Create account
    account_response = await async_client.post(
        "/v1/accounts",
        json={"email": "queryusage@example.com", "name": "Query Usage"},
    )
    account_id = account_response.json()["id"]

    # Create plan
    plan_response = await async_client.post(
        "/v1/plans",
        json={
            "name": "Query Plan",
            "interval": "month",
            "amount": 0,
            "currency": "USD",
            "usage_type": "metered",
        },
    )
    plan_id = plan_response.json()["id"]

    # Create subscription
    sub_response = await async_client.post(
        "/v1/subscriptions",
        json={"account_id": account_id, "plan_id": plan_id, "quantity": 1},
    )
    subscription_id = sub_response.json()["id"]

    # Submit multiple usage events
    for i in range(3):
        await async_client.post(
            "/v1/usage",
            json={
                "subscription_id": subscription_id,
                "metric": "api_calls",
                "quantity": 100 * (i + 1),
                "timestamp": datetime.utcnow().isoformat(),
                "idempotency_key": f"query_{uuid4()}",
            },
        )

    # Query usage
    usage_query_response = await async_client.get(
        f"/v1/subscriptions/{subscription_id}/usage",
    )

    assert usage_query_response.status_code == 200
    data = usage_query_response.json()
    assert "items" in data
    assert "total_quantity" in data
    assert len(data["items"]) == 3
    assert data["total_quantity"] == 600  # 100 + 200 + 300
