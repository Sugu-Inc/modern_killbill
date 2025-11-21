"""Usage tracking API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db, get_current_user
from billing.auth.rbac import require_roles, Role
from billing.schemas.usage_record import UsageRecord, UsageRecordCreate
from billing.services.usage_service import UsageService

router = APIRouter(prefix="/usage", tags=["Usage"])


@router.post("", response_model=UsageRecord, status_code=status.HTTP_201_CREATED)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def submit_usage_event(
    usage_data: UsageRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UsageRecord:
    """
    Submit a usage event.

    - **subscription_id**: UUID of the subscription
    - **metric**: Usage metric name (e.g., "api_calls", "storage_gb")
    - **quantity**: Number of units consumed
    - **timestamp**: When the usage occurred
    - **idempotency_key**: Unique key to prevent duplicate charges

    Idempotency: Submitting the same event with the same idempotency_key multiple times
    will return the original usage record without creating duplicates.
    """
    service = UsageService(db)

    try:
        usage_record = await service.record_usage(usage_data)
        await db.commit()
        return usage_record
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
