"""Integration tests for webhook notifications (User Story 11)."""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import PlanInterval
from billing.schemas.account import AccountCreate
from billing.schemas.plan import PlanCreate
from billing.schemas.subscription import SubscriptionCreate


@pytest.mark.asyncio
async def test_invoice_created_event_sent(db_session: AsyncSession) -> None:
    """Test that webhook event is sent when invoice is created."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.webhook_service import WebhookService
    from billing.models.webhook_event import WebhookEventStatus

    # Create account and plan
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="webhook1@example.com", name="Webhook Account 1")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Webhook Plan",
            interval=PlanInterval.MONTH,
            amount=5000,
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

    # Generate invoice (should trigger webhook event)
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Verify webhook event was created
    webhook_service = WebhookService(db_session)
    events = await webhook_service.get_events_by_resource(
        resource_type="invoice",
        resource_id=invoice.id
    )

    assert len(events) >= 1
    invoice_event = next((e for e in events if e.event_type == "invoice.created"), None)
    assert invoice_event is not None
    assert invoice_event.payload["invoice_id"] == str(invoice.id)
    assert invoice_event.status in [WebhookEventStatus.PENDING, WebhookEventStatus.DELIVERED]


@pytest.mark.asyncio
async def test_payment_succeeded_event_sent(db_session: AsyncSession) -> None:
    """Test that webhook event is sent when payment succeeds."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.invoice_service import InvoiceService
    from billing.services.payment_service import PaymentService
    from billing.services.webhook_service import WebhookService

    # Create account and plan
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="webhook2@example.com", name="Webhook Account 2")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Payment Webhook Plan",
            interval=PlanInterval.MONTH,
            amount=10000,
            currency="USD",
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

    # Process payment (should trigger webhook event)
    payment_service = PaymentService(db_session)
    payment = await payment_service.attempt_payment(
        invoice_id=invoice.id,
        payment_method_id=None,  # Mock payment
    )
    await db_session.commit()

    # Verify payment succeeded webhook event
    webhook_service = WebhookService(db_session)
    events = await webhook_service.get_events_by_resource(
        resource_type="payment",
        resource_id=payment.id
    )

    assert len(events) >= 1
    payment_event = next((e for e in events if "payment.succeeded" in e.event_type), None)
    assert payment_event is not None
    assert payment_event.payload["payment_id"] == str(payment.id)


@pytest.mark.asyncio
async def test_webhook_retry_on_failure(db_session: AsyncSession) -> None:
    """Test that webhooks retry on delivery failure with exponential backoff."""
    from billing.services.webhook_service import WebhookService
    from billing.models.webhook_event import WebhookEventStatus

    webhook_service = WebhookService(db_session)

    # Create a webhook event
    event = await webhook_service.create_event(
        event_type="test.event",
        payload={"test": "data"},
        endpoint_url="https://example.com/webhook-endpoint",
    )
    await db_session.commit()

    # Simulate delivery failure
    await webhook_service.mark_delivery_failed(event.id, error="Connection timeout")
    await db_session.commit()

    await db_session.refresh(event)

    # Verify retry count increased and status is PENDING for retry
    assert event.retry_count == 1
    assert event.status == WebhookEventStatus.PENDING

    # Simulate multiple failures
    for i in range(4):
        await webhook_service.mark_delivery_failed(event.id, error=f"Retry {i+2} failed")
        await db_session.commit()
        await db_session.refresh(event)

    # After 5 retries, should be marked as FAILED
    assert event.retry_count == 5
    assert event.status == WebhookEventStatus.FAILED


@pytest.mark.asyncio
async def test_webhook_delivery_success(db_session: AsyncSession) -> None:
    """Test successful webhook delivery."""
    from billing.services.webhook_service import WebhookService
    from billing.models.webhook_event import WebhookEventStatus

    webhook_service = WebhookService(db_session)

    # Create a webhook event
    event = await webhook_service.create_event(
        event_type="subscription.created",
        payload={"subscription_id": str(uuid4())},
        endpoint_url="https://example.com/webhooks",
    )
    await db_session.commit()

    # Mark as successfully delivered
    await webhook_service.mark_delivery_success(event.id)
    await db_session.commit()

    await db_session.refresh(event)

    assert event.status == WebhookEventStatus.DELIVERED
    assert event.delivered_at is not None
    assert event.retry_count == 0


@pytest.mark.asyncio
async def test_filter_events_by_category(db_session: AsyncSession) -> None:
    """Test filtering webhook events by category."""
    from billing.services.webhook_service import WebhookService

    webhook_service = WebhookService(db_session)

    # Create multiple webhook events
    await webhook_service.create_event(
        event_type="invoice.created",
        payload={"invoice_id": str(uuid4())},
        endpoint_url="https://example.com/webhooks",
    )

    await webhook_service.create_event(
        event_type="invoice.paid",
        payload={"invoice_id": str(uuid4())},
        endpoint_url="https://example.com/webhooks",
    )

    await webhook_service.create_event(
        event_type="payment.succeeded",
        payload={"payment_id": str(uuid4())},
        endpoint_url="https://example.com/webhooks",
    )

    await webhook_service.create_event(
        event_type="subscription.created",
        payload={"subscription_id": str(uuid4())},
        endpoint_url="https://example.com/webhooks",
    )

    await db_session.commit()

    # Filter by category (invoice)
    invoice_events = await webhook_service.filter_events_by_category("invoice")
    assert len(invoice_events) == 2
    assert all("invoice" in e.event_type for e in invoice_events)

    # Filter by category (payment)
    payment_events = await webhook_service.filter_events_by_category("payment")
    assert len(payment_events) == 1
    assert payment_events[0].event_type == "payment.succeeded"

    # Filter by category (subscription)
    subscription_events = await webhook_service.filter_events_by_category("subscription")
    assert len(subscription_events) == 1
    assert subscription_events[0].event_type == "subscription.created"


@pytest.mark.asyncio
async def test_subscription_created_webhook(db_session: AsyncSession) -> None:
    """Test that webhook is sent when subscription is created."""
    from billing.services.account_service import AccountService
    from billing.services.plan_service import PlanService
    from billing.services.subscription_service import SubscriptionService
    from billing.services.webhook_service import WebhookService

    # Create account and plan
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="sub_webhook@example.com", name="Subscription Webhook Account")
    )

    plan_service = PlanService(db_session)
    plan = await plan_service.create_plan(
        PlanCreate(
            name="Webhook Sub Plan",
            interval=PlanInterval.MONTH,
            amount=5000,
            currency="USD",
        )
    )
    await db_session.commit()

    # Create subscription (should trigger webhook)
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Verify webhook event created
    webhook_service = WebhookService(db_session)
    events = await webhook_service.get_events_by_resource(
        resource_type="subscription",
        resource_id=subscription.id
    )

    assert len(events) >= 1
    sub_event = next((e for e in events if e.event_type == "subscription.created"), None)
    assert sub_event is not None
    assert sub_event.payload["subscription_id"] == str(subscription.id)


# API endpoint tests


@pytest.mark.asyncio
async def test_create_webhook_endpoint_via_api(async_client: AsyncClient) -> None:
    """Test creating webhook endpoint configuration via API."""
    response = await async_client.post(
        "/v1/webhook-endpoints",
        json={
            "url": "https://example.com/billing-webhooks",
            "events": ["invoice.created", "invoice.paid", "payment.succeeded"],
            "description": "Main billing webhook endpoint",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/billing-webhooks"
    assert "invoice.created" in data["events"]
    assert data["active"] is True


@pytest.mark.asyncio
async def test_list_webhook_endpoints_via_api(async_client: AsyncClient) -> None:
    """Test listing webhook endpoints via API."""
    # Create a webhook endpoint
    await async_client.post(
        "/v1/webhook-endpoints",
        json={
            "url": "https://example.com/webhooks",
            "events": ["*"],  # All events
        },
    )

    # List endpoints
    response = await async_client.get("/v1/webhook-endpoints")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_webhook_event_timeline(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Test webhook events timeline for an account."""
    from billing.services.account_service import AccountService

    # Create account
    account_service = AccountService(db_session)
    account = await account_service.create_account(
        AccountCreate(email="timeline@example.com", name="Timeline Account")
    )
    await db_session.commit()

    # Get webhook events for account
    response = await async_client.get(f"/v1/accounts/{account.id}/webhook-events")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # Initially might be empty or have account.created event
