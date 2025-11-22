"""Service for managing webhook events and delivery."""
from datetime import datetime, timedelta
from uuid import UUID
from typing import Any

import httpx
import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.webhook_event import WebhookEvent, WebhookStatus
from billing.schemas.webhook_event import WebhookEventCreate

logger = structlog.get_logger(__name__)


class WebhookService:
    """Service for webhook event management and delivery."""

    # Retry schedule in minutes: [3, 6, 12, 24, 48]
    RETRY_SCHEDULE_MINUTES = [3, 6, 12, 24, 48]
    MAX_RETRIES = 5
    DELIVERY_TIMEOUT_SECONDS = 30

    def __init__(self, db: AsyncSession):
        """Initialize webhook service with database session."""
        self.db = db

    async def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        endpoint_url: str,
    ) -> WebhookEvent:
        """
        Create a new webhook event for delivery.

        Args:
            event_type: Event type (e.g., "invoice.created", "payment.succeeded")
            payload: Event payload data
            endpoint_url: Webhook endpoint URL to deliver to

        Returns:
            Created webhook event
        """
        event = WebhookEvent(
            event_type=event_type,
            payload=payload,
            endpoint_url=endpoint_url,
            status=WebhookStatus.PENDING,
            retry_count=0,
        )

        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)

        logger.info(
            "webhook_event_created",
            event_id=str(event.id),
            event_type=event_type,
            endpoint=endpoint_url,
        )

        return event

    async def deliver_event(self, event_id: UUID) -> bool:
        """
        Attempt to deliver a webhook event to its endpoint.

        Args:
            event_id: Webhook event ID

        Returns:
            True if delivery succeeded, False otherwise
        """
        # Load event
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event:
            logger.warning("webhook_event_not_found", event_id=str(event_id))
            return False

        if event.status == WebhookStatus.DELIVERED:
            logger.info("webhook_already_delivered", event_id=str(event_id))
            return True

        try:
            async with httpx.AsyncClient(timeout=self.DELIVERY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    event.endpoint_url,
                    json={
                        "id": str(event.id),
                        "type": event.event_type,
                        "created": event.created_at.isoformat() if event.created_at else datetime.utcnow().isoformat(),
                        "data": event.payload,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "BillingPlatform-Webhooks/1.0",
                    },
                )

                if response.status_code in [200, 201, 202, 204]:
                    # Successful delivery
                    await self.mark_delivery_success(event_id)
                    logger.info(
                        "webhook_delivered",
                        event_id=str(event_id),
                        event_type=event.event_type,
                        status_code=response.status_code,
                    )
                    return True
                else:
                    # Failed delivery - schedule retry
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    await self.mark_delivery_failed(event_id, error=error_msg)
                    logger.warning(
                        "webhook_delivery_failed",
                        event_id=str(event_id),
                        status_code=response.status_code,
                        error=error_msg,
                    )
                    return False

        except httpx.TimeoutException:
            error_msg = f"Request timeout after {self.DELIVERY_TIMEOUT_SECONDS}s"
            await self.mark_delivery_failed(event_id, error=error_msg)
            logger.warning("webhook_timeout", event_id=str(event_id))
            return False

        except httpx.HTTPError as e:
            error_msg = f"HTTP error: {str(e)}"
            await self.mark_delivery_failed(event_id, error=error_msg)
            logger.error("webhook_http_error", event_id=str(event_id), error=str(e))
            return False

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            await self.mark_delivery_failed(event_id, error=error_msg)
            logger.error("webhook_unexpected_error", event_id=str(event_id), error=str(e), exc_info=True)
            return False

    async def mark_delivery_success(self, event_id: UUID) -> None:
        """
        Mark webhook event as successfully delivered.

        Args:
            event_id: Webhook event ID
        """
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        event = result.scalar_one_or_none()

        if event:
            event.status = WebhookStatus.DELIVERED
            event.delivered_at = datetime.utcnow()
            event.last_error = None
            event.next_retry_at = None
            await self.db.flush()

    async def mark_delivery_failed(self, event_id: UUID, error: str) -> None:
        """
        Mark webhook event delivery as failed and schedule retry.

        Args:
            event_id: Webhook event ID
            error: Error message
        """
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event:
            return

        event.retry_count += 1
        event.last_error = error[:500]  # Limit error message length

        if event.retry_count >= self.MAX_RETRIES:
            # Max retries exceeded - mark as permanently failed
            event.status = WebhookStatus.FAILED
            event.next_retry_at = None
            logger.error(
                "webhook_permanently_failed",
                event_id=str(event_id),
                retries=event.retry_count,
                last_error=error,
            )
        else:
            # Schedule next retry with exponential backoff
            event.status = WebhookStatus.PENDING
            retry_delay_minutes = self.RETRY_SCHEDULE_MINUTES[min(event.retry_count - 1, len(self.RETRY_SCHEDULE_MINUTES) - 1)]
            event.next_retry_at = datetime.utcnow() + timedelta(minutes=retry_delay_minutes)

            logger.info(
                "webhook_retry_scheduled",
                event_id=str(event_id),
                retry=event.retry_count,
                next_retry_in_minutes=retry_delay_minutes,
            )

        await self.db.flush()

    async def get_pending_events_for_retry(self) -> list[WebhookEvent]:
        """
        Get webhook events that are ready for retry.

        Returns:
            List of webhook events ready for retry
        """
        now = datetime.utcnow()

        query = select(WebhookEvent).where(
            and_(
                WebhookEvent.status == WebhookStatus.PENDING,
                WebhookEvent.retry_count > 0,  # Has been attempted before
                WebhookEvent.next_retry_at.isnot(None),
                WebhookEvent.next_retry_at <= now,
            )
        ).order_by(WebhookEvent.next_retry_at)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pending_events_for_initial_delivery(self, limit: int = 100) -> list[WebhookEvent]:
        """
        Get webhook events that need initial delivery attempt.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of webhook events pending initial delivery
        """
        query = select(WebhookEvent).where(
            and_(
                WebhookEvent.status == WebhookStatus.PENDING,
                WebhookEvent.retry_count == 0,
            )
        ).order_by(WebhookEvent.created_at).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def retry_failed_events(self) -> int:
        """
        Retry all webhook events that are ready for retry.

        Returns:
            Number of events retried
        """
        events = await self.get_pending_events_for_retry()

        retry_count = 0
        for event in events:
            success = await self.deliver_event(event.id)
            if success or event.retry_count >= self.MAX_RETRIES:
                retry_count += 1

        return retry_count

    async def filter_events_by_category(self, category: str) -> list[WebhookEvent]:
        """
        Filter webhook events by category (e.g., "invoice", "payment", "subscription").

        Args:
            category: Event category to filter by

        Returns:
            List of webhook events matching the category
        """
        query = select(WebhookEvent).where(
            WebhookEvent.event_type.like(f"{category}.%")
        ).order_by(WebhookEvent.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_events_by_resource(
        self, resource_type: str, resource_id: UUID
    ) -> list[WebhookEvent]:
        """
        Get webhook events for a specific resource.

        Args:
            resource_type: Resource type (e.g., "invoice", "payment", "subscription")
            resource_id: Resource UUID

        Returns:
            List of webhook events for the resource
        """
        # Search for resource_id in payload
        resource_id_str = str(resource_id)

        query = select(WebhookEvent).where(
            and_(
                WebhookEvent.event_type.like(f"{resource_type}.%"),
                WebhookEvent.payload.op("@>")({f"{resource_type}_id": resource_id_str})
            )
        ).order_by(WebhookEvent.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_event(self, event_id: UUID) -> WebhookEvent | None:
        """
        Get webhook event by ID.

        Args:
            event_id: Webhook event UUID

        Returns:
            Webhook event or None if not found
        """
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def list_events(
        self,
        status: WebhookStatus | None = None,
        event_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WebhookEvent], int]:
        """
        List webhook events with filtering and pagination.

        Args:
            status: Filter by status (optional)
            event_type: Filter by event type (optional)
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (events list, total count)
        """
        conditions = []

        if status:
            conditions.append(WebhookEvent.status == status)

        if event_type:
            conditions.append(WebhookEvent.event_type == event_type)

        # Count total
        count_query = select(WebhookEvent)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        count_result = await self.db.execute(count_query)
        total = len(list(count_result.scalars().all()))

        # Get paginated results
        query = select(WebhookEvent)
        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(WebhookEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total

    async def list_events_for_account(
        self,
        account_id: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[WebhookEvent], int]:
        """
        List all webhook events for an account.

        Searches for events where the payload contains the account_id.

        Args:
            account_id: Account UUID
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (events list, total count)
        """
        account_id_str = str(account_id)

        # Search for events where payload contains account_id
        query = select(WebhookEvent).where(
            WebhookEvent.payload.op("@>")({f"account_id": account_id_str})
        )

        # Count total
        count_result = await self.db.execute(query)
        total = len(list(count_result.scalars().all()))

        # Get paginated results
        query = select(WebhookEvent).where(
            WebhookEvent.payload.op("@>")({f"account_id": account_id_str})
        ).order_by(WebhookEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total
