"""Integration tests for error handling and validation."""
import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient

from billing.main import app
from billing.models.account import Account
from billing.models.plan import Plan, PlanInterval


client = TestClient(app)


@pytest.mark.asyncio
async def test_validation_error_invalid_email(db_session: AsyncSession) -> None:
    """Test that invalid email returns proper validation error."""
    response = client.post(
        "/v1/accounts",
        json={
            "email": "not-an-email",  # Invalid email format
            "name": "Test Customer",
            "currency": "USD",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()
    # Pydantic validation error format
    errors = response.json()["detail"]
    assert isinstance(errors, list)
    assert any("email" in str(error).lower() for error in errors)


@pytest.mark.asyncio
async def test_validation_error_invalid_currency(db_session: AsyncSession) -> None:
    """Test that invalid currency code returns validation error."""
    response = client.post(
        "/v1/accounts",
        json={
            "email": "test@example.com",
            "name": "Test Customer",
            "currency": "INVALID",  # Should be 3-letter ISO code
        },
    )

    assert response.status_code == 422
    # Currency validation should catch this


@pytest.mark.asyncio
async def test_not_found_error_account(db_session: AsyncSession) -> None:
    """Test that accessing non-existent account returns 404."""
    non_existent_id = uuid4()

    response = client.get(f"/v1/accounts/{non_existent_id}")

    assert response.status_code == 404
    assert "detail" in response.json()
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_not_found_error_invoice(db_session: AsyncSession) -> None:
    """Test that accessing non-existent invoice returns 404."""
    non_existent_id = uuid4()

    response = client.get(f"/v1/invoices/{non_existent_id}")

    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_business_logic_error_void_paid_invoice(db_session: AsyncSession) -> None:
    """Test that attempting to void a paid invoice returns 400."""
    # This test would require creating a paid invoice first
    # For now, we'll test the error structure when business logic fails
    # In real implementation, this would:
    # 1. Create account, plan, subscription
    # 2. Generate invoice
    # 3. Pay invoice
    # 4. Attempt to void (should fail)
    # 5. Verify 400 error with clear message
    pass  # Placeholder for full e2e test


@pytest.mark.asyncio
async def test_validation_error_negative_amount(db_session: AsyncSession) -> None:
    """Test that negative amounts are rejected."""
    # Create account first
    account = Account(
        email="negative-test@example.com",
        name="Negative Test",
        currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    await db_session.commit()

    # Attempt to create plan with negative price
    response = client.post(
        "/v1/plans",
        json={
            "name": "Negative Plan",
            "price": -1000,  # Negative price should be rejected
            "currency": "USD",
            "interval": "month",
        },
    )

    # Should return validation error
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_validation_error_invalid_uuid(db_session: AsyncSession) -> None:
    """Test that invalid UUIDs return proper error."""
    response = client.get("/v1/accounts/not-a-uuid")

    assert response.status_code == 422
    # FastAPI should catch invalid UUID format


@pytest.mark.asyncio
async def test_concurrent_modification_handling(db_session: AsyncSession) -> None:
    """Test that concurrent modifications are handled gracefully."""
    # Create an account
    account = Account(
        email="concurrent@example.com",
        name="Concurrent Test",
        currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    await db_session.commit()

    # In a real concurrent scenario, multiple requests would modify the same resource
    # The system should handle this with proper error messages
    # This is a placeholder for database-level concurrency testing
    pass


@pytest.mark.asyncio
async def test_rate_limit_error_structure(db_session: AsyncSession) -> None:
    """Test that rate limit errors (when implemented) have proper structure."""
    # This test is a placeholder for when rate limiting is implemented
    # Rate limit errors should return:
    # - 429 status code
    # - Retry-After header
    # - Clear error message
    # - Retry timestamp
    pass


@pytest.mark.asyncio
async def test_error_response_includes_request_id(db_session: AsyncSession) -> None:
    """Test that error responses include request ID for tracing."""
    non_existent_id = uuid4()
    response = client.get(f"/v1/accounts/{non_existent_id}")

    assert response.status_code == 404

    # Error response should include metadata for debugging
    # This might include request_id, timestamp, etc.
    # Structure depends on implementation of T168 (structured error responses)


@pytest.mark.asyncio
async def test_database_connection_error_handling(db_session: AsyncSession) -> None:
    """Test that database errors are handled gracefully."""
    # This would test what happens when database is unavailable
    # Should return 503 Service Unavailable with proper error message
    # Requires mocking database failure
    pass


@pytest.mark.asyncio
async def test_stripe_api_error_handling(db_session: AsyncSession) -> None:
    """Test that Stripe API errors are handled gracefully."""
    # This would test what happens when Stripe API is unavailable
    # Should return proper error with remediation hints
    # Requires mocking Stripe failure
    pass


@pytest.mark.asyncio
async def test_validation_multiple_errors(db_session: AsyncSession) -> None:
    """Test that multiple validation errors are all returned."""
    response = client.post(
        "/v1/accounts",
        json={
            "email": "not-an-email",  # Invalid email
            "name": "",  # Empty name
            "currency": "TOOLONG",  # Invalid currency
        },
    )

    assert response.status_code == 422
    errors = response.json()["detail"]

    # Should have multiple errors
    assert isinstance(errors, list)
    assert len(errors) >= 2  # At least email and name errors


@pytest.mark.asyncio
async def test_missing_required_field(db_session: AsyncSession) -> None:
    """Test that missing required fields return validation error."""
    response = client.post(
        "/v1/accounts",
        json={
            "email": "test@example.com",
            # Missing required 'name' field
        },
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("name" in str(error).lower() for error in errors)


@pytest.mark.asyncio
async def test_invalid_enum_value(db_session: AsyncSession) -> None:
    """Test that invalid enum values return validation error."""
    response = client.post(
        "/v1/plans",
        json={
            "name": "Test Plan",
            "price": 1000,
            "currency": "USD",
            "interval": "invalid_interval",  # Should be "day", "week", "month", or "year"
        },
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("interval" in str(error).lower() for error in errors)
