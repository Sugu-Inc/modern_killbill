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


@pytest.fixture(scope="function")
def client() -> TestClient:
    """
    Create a FastAPI test client.

    Returns:
        TestClient: Synchronous test client for FastAPI
    """
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async HTTP client for testing.

    Yields:
        AsyncClient: Async HTTP client for API testing
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


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
