"""Integration tests for health check endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Test basic health check endpoint returns 200 OK."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_readiness_check_structure(client: TestClient) -> None:
    """Test readiness check endpoint structure."""
    response = client.get("/health/ready")

    # Response should have correct structure regardless of status
    data = response.json()
    assert "ready" in data
    assert "checks" in data
    assert "timestamp" in data

    # Checks should include database, redis, stripe
    checks = data["checks"]
    assert "database" in checks
    assert "redis" in checks
    assert "stripe" in checks


@pytest.mark.asyncio
async def test_health_returns_version(client: TestClient) -> None:
    """Test that health endpoint returns version information."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.1.0"
    assert data["status"] == "healthy"
