"""Integration tests for account management endpoints."""
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.account import Account, AccountStatus
from billing.schemas.account import AccountCreate


@pytest.mark.asyncio
async def test_create_account_minimal(db_session: AsyncSession) -> None:
    """Test creating an account with minimal required fields."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)
    account_data = AccountCreate(
        email="test@example.com",
        name="Test Account",
    )

    account = await service.create_account(account_data)
    await db_session.commit()

    assert account.id is not None
    assert isinstance(account.id, UUID)
    assert account.email == "test@example.com"
    assert account.name == "Test Account"
    assert account.currency == "USD"  # Default
    assert account.timezone == "UTC"  # Default
    assert account.status == AccountStatus.ACTIVE
    assert account.tax_exempt is False
    assert account.created_at is not None


@pytest.mark.asyncio
async def test_create_account_with_custom_fields(db_session: AsyncSession) -> None:
    """Test creating an account with custom currency and timezone."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)
    account_data = AccountCreate(
        email="eu@example.com",
        name="EU Account",
        currency="EUR",
        timezone="Europe/Paris",
        tax_exempt=True,
        extra_metadata={"region": "EU", "segment": "enterprise"},
    )

    account = await service.create_account(account_data)
    await db_session.commit()

    assert account.email == "eu@example.com"
    assert account.currency == "EUR"
    assert account.timezone == "Europe/Paris"
    assert account.tax_exempt is True
    assert account.extra_metadata["region"] == "EU"
    assert account.extra_metadata["segment"] == "enterprise"


@pytest.mark.asyncio
async def test_duplicate_email_rejected(db_session: AsyncSession) -> None:
    """Test that duplicate emails are rejected (email uniqueness is enforced)."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)
    account_data = AccountCreate(
        email="duplicate@example.com",
        name="Account 1",
    )

    # Create first account
    account1 = await service.create_account(account_data)
    await db_session.commit()

    # Try to create second account with same email - should fail
    account_data2 = AccountCreate(
        email="duplicate@example.com",
        name="Account 2",
    )

    with pytest.raises(ValueError, match="already exists"):
        await service.create_account(account_data2)


@pytest.mark.asyncio
async def test_get_account(db_session: AsyncSession) -> None:
    """Test retrieving an account by ID."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)

    # Create account
    account_data = AccountCreate(email="get@example.com", name="Get Account")
    created = await service.create_account(account_data)
    await db_session.commit()

    # Retrieve account
    retrieved = await service.get_account(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.email == created.email
    assert retrieved.name == created.name


@pytest.mark.asyncio
async def test_get_nonexistent_account(db_session: AsyncSession) -> None:
    """Test retrieving a non-existent account returns None."""
    from billing.services.account_service import AccountService
    from uuid import uuid4

    service = AccountService(db_session)
    account = await service.get_account(uuid4())

    assert account is None


@pytest.mark.asyncio
async def test_list_accounts(db_session: AsyncSession) -> None:
    """Test listing accounts with pagination."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)

    # Create multiple accounts
    for i in range(5):
        account_data = AccountCreate(
            email=f"list{i}@example.com",
            name=f"Account {i}",
        )
        await service.create_account(account_data)
    await db_session.commit()

    # List accounts
    accounts, total = await service.list_accounts(page=1, page_size=10)

    assert len(accounts) >= 5
    assert total >= 5


@pytest.mark.asyncio
async def test_update_account_status(db_session: AsyncSession) -> None:
    """Test updating account status for dunning."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)

    # Create account
    account_data = AccountCreate(email="status@example.com", name="Status Account")
    account = await service.create_account(account_data)
    await db_session.commit()

    assert account.status == AccountStatus.ACTIVE

    # Update to WARNING
    updated = await service.update_account_status(account.id, AccountStatus.WARNING)
    await db_session.commit()

    assert updated.status == AccountStatus.WARNING

    # Update to BLOCKED
    updated = await service.update_account_status(account.id, AccountStatus.BLOCKED)
    await db_session.commit()

    assert updated.status == AccountStatus.BLOCKED


@pytest.mark.asyncio
async def test_soft_delete_account(db_session: AsyncSession) -> None:
    """Test soft deleting an account."""
    from billing.services.account_service import AccountService

    service = AccountService(db_session)

    # Create account
    account_data = AccountCreate(email="delete@example.com", name="Delete Account")
    account = await service.create_account(account_data)
    await db_session.commit()

    # Soft delete
    deleted = await service.delete_account(account.id)
    await db_session.commit()

    assert deleted.deleted_at is not None

    # Verify account no longer appears in list
    accounts, total = await service.list_accounts()
    account_ids = [a.id for a in accounts]
    assert account.id not in account_ids


# API endpoint tests using TestClient


def test_create_account_via_api(client: TestClient) -> None:
    """Test creating account via REST API."""
    response = client.post(
        "/v1/accounts",
        json={
            "email": "api@example.com",
            "name": "API Account",
            "currency": "USD",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "api@example.com"
    assert data["name"] == "API Account"
    assert "id" in data


def test_get_account_via_api(client: TestClient) -> None:
    """Test retrieving account via REST API."""
    # Create account
    create_response = client.post(
        "/v1/accounts",
        json={"email": "getapi@example.com", "name": "Get API Account"},
    )
    account_id = create_response.json()["id"]

    # Get account
    response = client.get(f"/v1/accounts/{account_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == account_id
    assert data["email"] == "getapi@example.com"


def test_list_accounts_via_api(client: TestClient) -> None:
    """Test listing accounts via REST API with pagination."""
    # Create a few accounts
    for i in range(3):
        client.post(
            "/v1/accounts",
            json={"email": f"listapi{i}@example.com", "name": f"List API {i}"},
        )

    # List accounts
    response = client.get("/v1/accounts?page=1&page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 3
