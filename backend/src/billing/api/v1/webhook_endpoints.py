"""Webhook endpoint configuration API."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from billing.database import get_db

router = APIRouter(prefix="/webhook-endpoints", tags=["Webhooks"])


# Pydantic schemas for webhook endpoint configuration
class WebhookEndpointCreate(BaseModel):
    """Schema for creating a webhook endpoint subscription."""

    url: str = Field(..., min_length=1, description="Webhook endpoint URL")
    events: list[str] = Field(default=["*"], description="Event types to subscribe to (use '*' for all)")
    description: str | None = Field(default=None, description="Endpoint description")
    active: bool = Field(default=True, description="Whether endpoint is active")


class WebhookEndpoint(BaseModel):
    """Schema for webhook endpoint configuration."""

    id: UUID
    url: str
    events: list[str]
    description: str | None
    active: bool
    created_at: str


class WebhookEndpointList(BaseModel):
    """Schema for paginated webhook endpoint list."""

    items: list[WebhookEndpoint]
    total: int
    page: int
    page_size: int


# In-memory storage for webhook endpoints (for MVP)
# In production, this should be stored in database
_webhook_endpoints: dict[UUID, WebhookEndpoint] = {}


@router.post("", response_model=WebhookEndpoint, status_code=status.HTTP_201_CREATED)
async def create_webhook_endpoint(
    endpoint_data: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpoint:
    """
    Create a new webhook endpoint subscription.

    Configure an endpoint URL to receive webhook notifications for billing events.
    You can subscribe to specific event types or use "*" to receive all events.

    Event types:
    - invoice.created, invoice.paid, invoice.voided
    - payment.succeeded, payment.failed
    - subscription.created, subscription.updated, subscription.canceled
    - credit.created, credit.applied
    """
    from datetime import datetime

    # Create webhook endpoint configuration
    endpoint_id = UUID(hex="0" * 32)  # Generate proper UUID in production
    import uuid
    endpoint_id = uuid.uuid4()

    endpoint = WebhookEndpoint(
        id=endpoint_id,
        url=endpoint_data.url,
        events=endpoint_data.events,
        description=endpoint_data.description,
        active=endpoint_data.active,
        created_at=datetime.utcnow().isoformat(),
    )

    # Store in memory (replace with database in production)
    _webhook_endpoints[endpoint_id] = endpoint

    return endpoint


@router.get("", response_model=WebhookEndpointList)
async def list_webhook_endpoints(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointList:
    """
    List all webhook endpoint subscriptions.

    Returns all configured webhook endpoints with their subscription settings.
    """
    endpoints = list(_webhook_endpoints.values())

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    paginated = endpoints[start:end]

    return WebhookEndpointList(
        items=paginated,
        total=len(endpoints),
        page=page,
        page_size=page_size,
    )


@router.get("/{endpoint_id}", response_model=WebhookEndpoint)
async def get_webhook_endpoint(
    endpoint_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpoint:
    """
    Get webhook endpoint configuration by ID.
    """
    if endpoint_id not in _webhook_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook endpoint {endpoint_id} not found",
        )

    return _webhook_endpoints[endpoint_id]


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_endpoint(
    endpoint_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete webhook endpoint subscription.

    Removes the endpoint configuration and stops sending webhooks to this URL.
    """
    if endpoint_id not in _webhook_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook endpoint {endpoint_id} not found",
        )

    del _webhook_endpoints[endpoint_id]


def get_active_endpoints() -> list[str]:
    """
    Get list of active webhook endpoint URLs.

    Returns:
        List of active endpoint URLs
    """
    return [
        endpoint.url
        for endpoint in _webhook_endpoints.values()
        if endpoint.active
    ]


def get_endpoints_for_event(event_type: str) -> list[str]:
    """
    Get webhook endpoints subscribed to a specific event type.

    Args:
        event_type: Event type (e.g., "invoice.created")

    Returns:
        List of endpoint URLs subscribed to this event
    """
    matching_endpoints = []

    for endpoint in _webhook_endpoints.values():
        if not endpoint.active:
            continue

        # Check if endpoint is subscribed to this event
        if "*" in endpoint.events or event_type in endpoint.events:
            matching_endpoints.append(endpoint.url)

        # Check for wildcard patterns (e.g., "invoice.*")
        event_category = event_type.split(".")[0]
        if f"{event_category}.*" in endpoint.events:
            matching_endpoints.append(endpoint.url)

    return matching_endpoints
