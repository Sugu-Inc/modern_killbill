"""Subscription API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db, get_current_user
from billing.auth.rbac import require_roles, Role
from billing.models.subscription import SubscriptionStatus
from billing.schemas.subscription import (
    Subscription,
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionList,
    SubscriptionPlanChange,
    SubscriptionPause,
)
from billing.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.post("", response_model=Subscription, status_code=status.HTTP_201_CREATED)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def create_subscription(
    subscription_data: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Create a new subscription.

    - **account_id**: Account UUID (required)
    - **plan_id**: Plan UUID (required)
    - **quantity**: Number of seats/licenses (default: 1)
    - **trial_end**: Trial end date (optional, overrides plan trial_days)

    The subscription starts immediately. If the plan has trial_days or trial_end is provided,
    the subscription starts in TRIALING status. Otherwise, it starts ACTIVE.
    """
    service = SubscriptionService(db)

    try:
        subscription = await service.create_subscription(subscription_data)
        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{subscription_id}", response_model=Subscription)
async def get_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    """
    Get subscription by ID.

    Returns subscription details including status, current period, and plan information.
    """
    service = SubscriptionService(db)
    subscription = await service.get_subscription(subscription_id)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found",
        )

    return subscription


@router.get("", response_model=SubscriptionList)
async def list_subscriptions(
    account_id: UUID | None = Query(None, description="Filter by account ID"),
    status_filter: SubscriptionStatus | None = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionList:
    """
    List subscriptions with pagination.

    - **account_id**: Filter by account (optional)
    - **status**: Filter by status (optional)
    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (default: 100, max: 1000)
    """
    service = SubscriptionService(db)
    subscriptions, total = await service.list_subscriptions(
        account_id, status_filter, page, page_size
    )

    return SubscriptionList(
        items=subscriptions,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{subscription_id}", response_model=Subscription)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def update_subscription(
    subscription_id: UUID,
    update_data: SubscriptionUpdate | SubscriptionPlanChange,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Update subscription or change plan.

    For plan changes:
    - **new_plan_id**: New plan to switch to
    - **new_quantity**: New quantity (optional)
    - **immediate**: Apply change immediately (default: false)
    - **change_at_period_end**: Schedule for period end (default: false)

    For updates:
    - **quantity**: Update number of seats/licenses
    - **cancel_at_period_end**: Schedule cancellation at period end

    All fields are optional.
    """
    service = SubscriptionService(db)

    try:
        # Check if this is a plan change request
        if isinstance(update_data, SubscriptionPlanChange) or hasattr(update_data, "new_plan_id"):
            # Handle plan change
            subscription = await service.change_plan(subscription_id, update_data)
        else:
            # Handle regular update
            subscription = await service.update_subscription(subscription_id, update_data)

        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{subscription_id}/cancel", response_model=Subscription)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def cancel_subscription(
    subscription_id: UUID,
    immediate: bool = Query(False, description="Cancel immediately or at period end"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Cancel subscription.

    - **immediate**: If true, cancels immediately. If false, cancels at end of current period.

    Default is false (cancel at period end).
    """
    service = SubscriptionService(db)

    try:
        subscription = await service.cancel_subscription(subscription_id, immediate)
        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{subscription_id}/reactivate", response_model=Subscription)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def reactivate_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Reactivate a subscription scheduled for cancellation.

    Only works if the subscription is scheduled to cancel at period end
    but hasn't been cancelled yet.
    """
    service = SubscriptionService(db)

    try:
        subscription = await service.reactivate_subscription(subscription_id)
        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{subscription_id}/pause", response_model=Subscription)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def pause_subscription(
    subscription_id: UUID,
    pause_data: SubscriptionPause,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Pause subscription.

    - **resumes_at**: Auto-resume date (optional, None for indefinite pause)

    Paused subscriptions don't generate invoices. They can be resumed manually
    or automatically on the resumes_at date.
    """
    service = SubscriptionService(db)

    try:
        subscription = await service.pause_subscription(subscription_id, pause_data)
        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{subscription_id}/resume", response_model=Subscription)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def resume_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Resume a paused subscription.

    The subscription returns to ACTIVE status and billing resumes.
    """
    service = SubscriptionService(db)

    try:
        subscription = await service.resume_subscription(subscription_id)
        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{subscription_id}/change-plan", response_model=Subscription)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def change_subscription_plan(
    subscription_id: UUID,
    plan_change: SubscriptionPlanChange,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Subscription:
    """
    Change subscription plan.

    - **new_plan_id**: Plan UUID to switch to (required)
    - **immediate**: Apply change now or at next period (default: false)

    If immediate is false, the plan change is scheduled for the next billing period.
    If immediate is true, the change applies now and may generate a prorated invoice.
    """
    service = SubscriptionService(db)

    try:
        subscription = await service.change_plan(subscription_id, plan_change)
        await db.commit()
        return subscription
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{subscription_id}/usage")
async def get_subscription_usage(
    subscription_id: UUID,
    metric: str | None = Query(None, description="Filter by metric"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get usage data for a subscription.

    Returns aggregated usage for the current billing period.
    - **subscription_id**: Subscription UUID
    - **metric**: Optional metric filter
    """
    from billing.services.usage_service import UsageService
    from billing.models.subscription import Subscription
    from sqlalchemy import select

    # Get subscription to determine billing period
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found",
        )

    service = UsageService(db)

    # Get usage records for current period
    usage_records, total_count = await service.list_usage_records(
        subscription_id=subscription_id,
        metric=metric,
        start_time=subscription.current_period_start,
        end_time=subscription.current_period_end,
        page=1,
        page_size=1000,
    )

    # Calculate total quantity
    total_quantity = sum(record.quantity for record in usage_records)

    return {
        "subscription_id": str(subscription_id),
        "items": [
            {
                "id": str(record.id),
                "metric": record.metric,
                "quantity": record.quantity,
                "timestamp": record.timestamp.isoformat(),
                "idempotency_key": record.idempotency_key,
            }
            for record in usage_records
        ],
        "total_quantity": total_quantity,
        "total": total_count,
    }
