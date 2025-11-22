"""Plan API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db, get_current_user
from billing.auth.rbac import require_roles, Role
from billing.schemas.plan import Plan, PlanCreate, PlanUpdate, PlanList
from billing.services.plan_service import PlanService
from billing.cache import cache, cache_key

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.post("", response_model=Plan, status_code=status.HTTP_201_CREATED)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN)
async def create_plan(
    plan_data: PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Plan:
    """
    Create a new pricing plan.

    - **name**: Plan name (required)
    - **interval**: Billing interval (month or year)
    - **amount**: Price in cents (required)
    - **currency**: ISO 4217 currency code (default: USD)
    - **trial_days**: Number of trial days (default: 0)
    - **usage_type**: Usage billing type for metered plans (optional)
    - **tiers**: Usage tier configuration for metered plans (optional)

    For usage-based plans, provide usage_type and tiers.
    For flat-rate plans, omit both fields.
    """
    service = PlanService(db)

    try:
        plan = await service.create_plan(plan_data)
        await db.commit()

        # Invalidate plan list cache
        await cache.invalidate_pattern("plan_list:*")

        return plan
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{plan_id}", response_model=Plan)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Plan:
    """
    Get plan by ID.

    Returns plan details including pricing, interval, and usage configuration.
    """
    # Check cache first
    cache_key_str = cache_key("plan", str(plan_id))
    cached = await cache.get(cache_key_str)
    if cached:
        return Plan.model_validate(cached)

    service = PlanService(db)
    plan = await service.get_plan(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    # Convert SQLAlchemy model to Pydantic schema
    plan_schema = Plan.model_validate(plan)

    # Cache for 5 minutes
    await cache.set(cache_key_str, plan_schema.model_dump(), ttl=300)

    return plan_schema


@router.get("", response_model=PlanList)
async def list_plans(
    page: int = 1,
    page_size: int = 100,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
) -> PlanList:
    """
    List pricing plans with pagination.

    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (default: 100, max: 1000)
    - **active_only**: Filter to active plans only (default: true)

    Active plans are available for new subscriptions.
    """
    if page < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page must be >= 1")

    if page_size < 1 or page_size > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Page size must be between 1 and 1000"
        )

    # Check cache first
    cache_key_str = cache_key("plan_list", f"page{page}_size{page_size}_active{active_only}")
    cached = await cache.get(cache_key_str)
    if cached:
        return PlanList.model_validate(cached)

    service = PlanService(db)
    plans, total = await service.list_plans(page, page_size, active_only)

    result = PlanList(
        items=plans,
        total=total,
        page=page,
        page_size=page_size,
    )

    # Cache for 1 minute (lists change more frequently)
    await cache.set(cache_key_str, result.model_dump(), ttl=60)

    return result


@router.patch("/{plan_id}", response_model=Plan)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN)
async def update_plan(
    plan_id: UUID,
    update_data: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Plan:
    """
    Update plan.

    Only name, active status, and metadata can be updated.
    For price changes, create a new plan version instead.

    All fields are optional.
    """
    service = PlanService(db)

    try:
        plan = await service.update_plan(plan_id, update_data)
        await db.commit()

        # Invalidate cache for this plan and plan lists
        await cache.invalidate_pattern(f"plan:{plan_id}*")
        await cache.invalidate_pattern("plan_list:*")

        return plan
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN)
async def deactivate_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    """
    Deactivate plan.

    This prevents new subscriptions but doesn't affect existing subscriptions.
    The plan is soft-deleted (marked as inactive).
    """
    service = PlanService(db)

    try:
        await service.deactivate_plan(plan_id)
        await db.commit()

        # Invalidate cache for this plan and plan lists
        await cache.invalidate_pattern(f"plan:{plan_id}*")
        await cache.invalidate_pattern("plan_list:*")
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{plan_id}/versions", response_model=Plan, status_code=status.HTTP_201_CREATED)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN)
async def create_plan_version(
    plan_id: UUID,
    plan_data: PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Plan:
    """
    Create new version of a plan.

    Use this for price changes. The original plan will be deactivated and a new
    plan will be created with an incremented version number.

    Existing subscriptions remain on the old plan. New subscriptions use the new version.
    """
    service = PlanService(db)

    try:
        new_plan = await service.create_plan_version(plan_id, plan_data)
        await db.commit()

        # Invalidate cache for old plan, new plan, and plan lists
        await cache.invalidate_pattern(f"plan:{plan_id}*")
        await cache.invalidate_pattern(f"plan:{new_plan.id}*")
        await cache.invalidate_pattern("plan_list:*")

        return new_plan
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/{plan_id}/subscription-count", response_model=dict[str, int])
async def get_plan_subscription_count(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """
    Get count of active subscriptions on this plan.

    Useful before deactivating a plan to understand impact.
    """
    service = PlanService(db)
    count = await service.get_plan_subscription_count(plan_id)

    return {"active_subscriptions": count}
