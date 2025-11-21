"""Pytest configuration and fixtures for async testing."""
import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from billing.database import Base
from billing.main import app

# Test database URL (use a separate test database)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/billing_test"

# Create async test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# Create async session factory for tests
TestAsyncSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create an event loop for the test session.

    Yields:
        Event loop for async tests
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database session for each test.

    Yields:
        AsyncSession: Database session for testing
    """
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with TestAsyncSessionLocal() as session:
        yield session
        await session.rollback()

    # Drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _setup_test_db() -> None:
    """Create database tables for testing."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _teardown_test_db() -> None:
    """Drop database tables after testing."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _mock_current_user() -> dict:
    """
    Mock current user for testing.

    Returns a Super Admin user to bypass all RBAC checks in tests.
    """
    return {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "role": "Super Admin",  # Super Admin has all permissions
        "permissions": ["*"],  # All permissions
    }


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client with test database.

    Returns:
        TestClient: Synchronous test client for FastAPI with test database
    """
    from billing.api.deps import get_db, get_current_user

    # Setup database tables
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_setup_test_db())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Override database dependency to use test database."""
        async with TestAsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _mock_current_user

    with TestClient(app) as test_client:
        yield test_client

    # Clean up
    app.dependency_overrides.clear()
    loop.run_until_complete(_teardown_test_db())


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async HTTP client for testing with database dependency override.

    Args:
        db_session: Test database session fixture

    Yields:
        AsyncClient: Async HTTP client for API testing
    """
    from billing.api.deps import get_db, get_current_user

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Override database dependency to use test database."""
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _mock_current_user

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def sample_account_data() -> dict[str, str]:
    """
    Sample account data for testing.

    Returns:
        dict: Account creation data
    """
    return {
        "email": "test@example.com",
        "name": "Test Account",
        "currency": "USD",
        "timezone": "UTC",
    }


@pytest.fixture(scope="function")
def sample_plan_data() -> dict:
    """
    Sample plan data for testing.

    Returns:
        dict: Plan creation data
    """
    return {
        "name": "Pro Plan",
        "interval": "month",
        "amount": 2900,  # $29.00 in cents
        "currency": "USD",
        "trial_days": 14,
    }


@pytest.fixture(scope="function")
def sample_subscription_data(sample_account_data: dict, sample_plan_data: dict) -> dict:
    """
    Sample subscription data for testing.

    Returns:
        dict: Subscription creation data
    """
    return {
        "account_id": "placeholder-account-id",
        "plan_id": "placeholder-plan-id",
        "quantity": 1,
    }
