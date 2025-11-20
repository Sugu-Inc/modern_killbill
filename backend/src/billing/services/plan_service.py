"""Plan service for business logic."""
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.plan import Plan
from billing.schemas.plan import PlanCreate, PlanUpdate


class PlanService:
    """Service layer for plan operations."""

    def __init__(self, db: AsyncSession):
        """Initialize plan service with database session."""
        self.db = db

    async def create_plan(self, plan_data: PlanCreate) -> Plan:
        """
        Create a new pricing plan.

        Args:
            plan_data: Plan creation data

        Returns:
            Created plan

        Raises:
            ValueError: If currency is not supported
        """
        # Validate currency
        from billing.utils.currency import validate_currency

        if not validate_currency(plan_data.currency):
            raise ValueError(
                f"Currency {plan_data.currency} is not supported. "
                f"Please use one of the supported currencies."
            )

        # Convert usage tiers to dict format for JSONB
        tiers_dict = None
        if plan_data.tiers:
            tiers_dict = [tier.model_dump() for tier in plan_data.tiers]

        # Create new plan
        plan = Plan(
            name=plan_data.name,
            interval=plan_data.interval,
            amount=plan_data.amount,
            currency=plan_data.currency,
            trial_days=plan_data.trial_days,
            usage_type=plan_data.usage_type,
            tiers=tiers_dict,
            active=plan_data.active,
            extra_metadata=plan_data.extra_metadata,
            version=1,
        )

        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)

        return plan

    async def get_plan(self, plan_id: UUID) -> Plan | None:
        """
        Get plan by ID.

        Args:
            plan_id: Plan UUID

        Returns:
            Plan or None if not found
        """
        result = await self.db.execute(select(Plan).where(Plan.id == plan_id))
        return result.scalar_one_or_none()

    async def update_plan(self, plan_id: UUID, update_data: PlanUpdate) -> Plan:
        """
        Update plan.

        Note: Only name, active status, and metadata can be updated.
        Price changes require creating a new plan version.

        Args:
            plan_id: Plan UUID
            update_data: Update data

        Returns:
            Updated plan

        Raises:
            ValueError: If plan not found
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(plan, field, value)

        await self.db.flush()
        await self.db.refresh(plan)

        return plan

    async def deactivate_plan(self, plan_id: UUID) -> Plan:
        """
        Deactivate plan (prevent new subscriptions).

        Args:
            plan_id: Plan UUID

        Returns:
            Updated plan

        Raises:
            ValueError: If plan not found
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        plan.active = False
        await self.db.flush()
        await self.db.refresh(plan)

        return plan

    async def list_plans(
        self,
        page: int = 1,
        page_size: int = 100,
        active_only: bool = True,
    ) -> tuple[list[Plan], int]:
        """
        List plans with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            active_only: Filter to active plans only

        Returns:
            Tuple of (plans, total_count)
        """
        # Build query
        query = select(Plan)

        if active_only:
            query = query.where(Plan.active == True)  # noqa: E712

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(Plan.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        plans = result.scalars().all()

        return list(plans), total or 0

    async def get_active_plans(self) -> list[Plan]:
        """
        Get all active plans (for subscription creation).

        Returns:
            List of active plans
        """
        result = await self.db.execute(
            select(Plan).where(Plan.active == True).order_by(Plan.name)  # noqa: E712
        )
        return list(result.scalars().all())

    async def create_plan_version(self, plan_id: UUID, plan_data: PlanCreate) -> Plan:
        """
        Create new version of a plan (for price changes).

        The old plan is deactivated and a new plan is created with incremented version.

        Args:
            plan_id: Original plan UUID
            plan_data: New plan data

        Returns:
            New plan version

        Raises:
            ValueError: If original plan not found
        """
        original_plan = await self.get_plan(plan_id)
        if not original_plan:
            raise ValueError(f"Plan {plan_id} not found")

        # Deactivate original plan
        original_plan.active = False

        # Convert usage tiers to dict format for JSONB
        tiers_dict = None
        if plan_data.tiers:
            tiers_dict = [tier.model_dump() for tier in plan_data.tiers]

        # Create new version
        new_plan = Plan(
            name=plan_data.name,
            interval=plan_data.interval,
            amount=plan_data.amount,
            currency=plan_data.currency,
            trial_days=plan_data.trial_days,
            usage_type=plan_data.usage_type,
            tiers=tiers_dict,
            active=plan_data.active,
            extra_metadata={
                **plan_data.extra_metadata,
                "previous_version_id": str(plan_id),
            },
            version=original_plan.version + 1,
        )

        self.db.add(new_plan)
        await self.db.flush()
        await self.db.refresh(new_plan)

        return new_plan

    async def get_plan_subscription_count(self, plan_id: UUID) -> int:
        """
        Get count of active subscriptions on this plan.

        Args:
            plan_id: Plan UUID

        Returns:
            Number of active subscriptions
        """
        from billing.models.subscription import Subscription, SubscriptionStatus

        result = await self.db.execute(
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.plan_id == plan_id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
        )
        return result.scalar() or 0
