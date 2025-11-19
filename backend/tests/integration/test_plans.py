"""Integration tests for pricing plan endpoints."""
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import Plan, PlanInterval, UsageType
from billing.schemas.plan import PlanCreate, UsageTier


@pytest.mark.asyncio
async def test_create_monthly_plan(db_session: AsyncSession) -> None:
    """Test creating a simple monthly plan."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)
    plan_data = PlanCreate(
        name="Basic Monthly",
        interval=PlanInterval.MONTH,
        amount=2900,  # $29.00
        currency="USD",
    )

    plan = await service.create_plan(plan_data)
    await db_session.commit()

    assert plan.id is not None
    assert isinstance(plan.id, UUID)
    assert plan.name == "Basic Monthly"
    assert plan.interval == PlanInterval.MONTH
    assert plan.amount == 2900
    assert plan.currency == "USD"
    assert plan.trial_days == 0
    assert plan.active is True
    assert plan.version == 1


@pytest.mark.asyncio
async def test_create_annual_plan(db_session: AsyncSession) -> None:
    """Test creating an annual plan."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)
    plan_data = PlanCreate(
        name="Pro Annual",
        interval=PlanInterval.YEAR,
        amount=29000,  # $290.00
        currency="USD",
    )

    plan = await service.create_plan(plan_data)
    await db_session.commit()

    assert plan.interval == PlanInterval.YEAR
    assert plan.amount == 29000


@pytest.mark.asyncio
async def test_create_plan_with_trial(db_session: AsyncSession) -> None:
    """Test creating a plan with trial period."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)
    plan_data = PlanCreate(
        name="Trial Plan",
        interval=PlanInterval.MONTH,
        amount=4900,
        currency="USD",
        trial_days=14,
    )

    plan = await service.create_plan(plan_data)
    await db_session.commit()

    assert plan.trial_days == 14


@pytest.mark.asyncio
async def test_create_usage_based_plan_with_tiers(db_session: AsyncSession) -> None:
    """Test creating a usage-based plan with tiered pricing."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)

    tiers = [
        {"up_to": 100, "unit_amount": 10},  # $0.10 per unit up to 100
        {"up_to": 500, "unit_amount": 8},   # $0.08 per unit from 101-500
        {"up_to": None, "unit_amount": 5},  # $0.05 per unit above 500
    ]

    plan_data = PlanCreate(
        name="Usage Tiered",
        interval=PlanInterval.MONTH,
        amount=0,  # No base fee
        currency="USD",
        usage_type=UsageType.TIERED,
        tiers=tiers,
    )

    plan = await service.create_plan(plan_data)
    await db_session.commit()

    assert plan.usage_type == UsageType.TIERED
    assert plan.tiers is not None
    assert len(plan.tiers) == 3
    assert plan.tiers[0]["up_to"] == 100
    assert plan.tiers[0]["unit_amount"] == 10


@pytest.mark.asyncio
async def test_plan_versioning(db_session: AsyncSession) -> None:
    """Test plan versioning when updating prices."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)

    # Create original plan
    plan_data = PlanCreate(
        name="Versioned Plan",
        interval=PlanInterval.MONTH,
        amount=1000,
        currency="USD",
    )
    plan_v1 = await service.create_plan(plan_data)
    await db_session.commit()

    assert plan_v1.version == 1
    assert plan_v1.active is True

    # Create new version (price change)
    plan_data_v2 = PlanCreate(
        name="Versioned Plan",
        interval=PlanInterval.MONTH,
        amount=1500,  # Price increase
        currency="USD",
    )
    plan_v2 = await service.create_plan_version(plan_v1.id, plan_data_v2)
    await db_session.commit()

    assert plan_v2.version == 2
    assert plan_v2.active is True
    assert plan_v2.amount == 1500

    # Verify old version is now inactive
    await db_session.refresh(plan_v1)
    assert plan_v1.active is False
    assert plan_v1.amount == 1000  # Original price unchanged


@pytest.mark.asyncio
async def test_get_plan(db_session: AsyncSession) -> None:
    """Test retrieving a plan by ID."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)

    # Create plan
    plan_data = PlanCreate(
        name="Get Plan",
        interval=PlanInterval.MONTH,
        amount=999,
        currency="USD",
    )
    created = await service.create_plan(plan_data)
    await db_session.commit()

    # Retrieve plan
    retrieved = await service.get_plan(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == created.name


@pytest.mark.asyncio
async def test_list_active_plans(db_session: AsyncSession) -> None:
    """Test listing only active plans."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)

    # Create active plan
    active_plan_data = PlanCreate(
        name="Active Plan",
        interval=PlanInterval.MONTH,
        amount=1000,
        currency="USD",
    )
    active_plan = await service.create_plan(active_plan_data)
    await db_session.commit()

    # Create and deactivate a plan
    inactive_plan_data = PlanCreate(
        name="Inactive Plan",
        interval=PlanInterval.MONTH,
        amount=2000,
        currency="USD",
    )
    inactive_plan = await service.create_plan(inactive_plan_data)
    await db_session.commit()

    await service.deactivate_plan(inactive_plan.id)
    await db_session.commit()

    # List active plans only
    plans, total = await service.list_plans(active_only=True)

    plan_ids = [p.id for p in plans]
    assert active_plan.id in plan_ids
    assert inactive_plan.id not in plan_ids


@pytest.mark.asyncio
async def test_deactivate_plan(db_session: AsyncSession) -> None:
    """Test deactivating a plan."""
    from billing.services.plan_service import PlanService

    service = PlanService(db_session)

    # Create plan
    plan_data = PlanCreate(
        name="Deactivate Plan",
        interval=PlanInterval.MONTH,
        amount=1000,
        currency="USD",
    )
    plan = await service.create_plan(plan_data)
    await db_session.commit()

    assert plan.active is True

    # Deactivate
    deactivated = await service.deactivate_plan(plan.id)
    await db_session.commit()

    assert deactivated.active is False


# API endpoint tests


def test_create_plan_via_api(client: TestClient) -> None:
    """Test creating plan via REST API."""
    response = client.post(
        "/v1/plans",
        json={
            "name": "API Plan",
            "interval": "month",
            "amount": 3900,
            "currency": "USD",
            "trial_days": 7,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "API Plan"
    assert data["amount"] == 3900
    assert data["trial_days"] == 7
    assert "id" in data


def test_get_plan_via_api(client: TestClient) -> None:
    """Test retrieving plan via REST API."""
    # Create plan
    create_response = client.post(
        "/v1/plans",
        json={
            "name": "Get API Plan",
            "interval": "month",
            "amount": 1999,
            "currency": "USD",
        },
    )
    plan_id = create_response.json()["id"]

    # Get plan
    response = client.get(f"/v1/plans/{plan_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == plan_id
    assert data["name"] == "Get API Plan"


def test_list_plans_via_api(client: TestClient) -> None:
    """Test listing plans via REST API."""
    # Create a few plans
    for i in range(3):
        client.post(
            "/v1/plans",
            json={
                "name": f"List API Plan {i}",
                "interval": "month",
                "amount": 1000 + (i * 100),
                "currency": "USD",
            },
        )

    # List plans
    response = client.get("/v1/plans?page=1&page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 3


def test_list_active_plans_filter_via_api(client: TestClient) -> None:
    """Test filtering active plans via REST API."""
    # Create plan
    create_response = client.post(
        "/v1/plans",
        json={
            "name": "Filter Plan",
            "interval": "month",
            "amount": 2500,
            "currency": "USD",
        },
    )
    plan_id = create_response.json()["id"]

    # Deactivate it
    client.delete(f"/v1/plans/{plan_id}")

    # List active plans only
    response = client.get("/v1/plans?active=true")

    assert response.status_code == 200
    data = response.json()
    plan_ids = [p["id"] for p in data["items"]]
    assert plan_id not in plan_ids
