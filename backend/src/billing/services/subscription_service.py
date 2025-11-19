"""Subscription service for business logic."""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.models.subscription import Subscription, SubscriptionStatus, SubscriptionHistory
from billing.models.plan import Plan
from billing.models.account import Account
from billing.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionPlanChange,
    SubscriptionPause,
)


class SubscriptionService:
    """Service layer for subscription operations."""

    def __init__(self, db: AsyncSession):
        """Initialize subscription service with database session."""
        self.db = db

    async def create_subscription(
        self, subscription_data: SubscriptionCreate
    ) -> Subscription:
        """
        Create a new subscription.

        Args:
            subscription_data: Subscription creation data

        Returns:
            Created subscription

        Raises:
            ValueError: If account or plan not found, or plan is inactive
        """
        # Verify account exists
        account_result = await self.db.execute(
            select(Account).where(Account.id == subscription_data.account_id)
        )
        account = account_result.scalar_one_or_none()
        if not account:
            raise ValueError(f"Account {subscription_data.account_id} not found")

        # Verify plan exists and is active
        plan_result = await self.db.execute(
            select(Plan).where(Plan.id == subscription_data.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise ValueError(f"Plan {subscription_data.plan_id} not found")
        if not plan.active:
            raise ValueError(f"Plan {subscription_data.plan_id} is inactive")

        # Calculate period dates
        now = datetime.utcnow()
        if plan.interval.value == "month":
            period_end = now + timedelta(days=30)
        else:  # year
            period_end = now + timedelta(days=365)

        # Calculate trial end
        trial_end = subscription_data.trial_end
        if not trial_end and plan.trial_days > 0:
            trial_end = now + timedelta(days=plan.trial_days)

        # Determine initial status
        status = SubscriptionStatus.TRIALING if trial_end else SubscriptionStatus.ACTIVE

        # Create subscription
        subscription = Subscription(
            account_id=subscription_data.account_id,
            plan_id=subscription_data.plan_id,
            quantity=subscription_data.quantity,
            status=status,
            current_period_start=now,
            current_period_end=period_end,
            trial_end=trial_end,
        )

        self.db.add(subscription)
        await self.db.flush()

        # Create history record
        await self._create_history(
            subscription.id,
            "subscription_created",
            None,
            status.value,
        )

        await self.db.refresh(subscription)
        return subscription

    async def get_subscription(self, subscription_id: UUID) -> Subscription | None:
        """
        Get subscription by ID.

        Args:
            subscription_id: Subscription UUID

        Returns:
            Subscription or None if not found
        """
        result = await self.db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_subscription_with_plan(self, subscription_id: UUID) -> Subscription | None:
        """
        Get subscription with eager-loaded plan.

        Args:
            subscription_id: Subscription UUID

        Returns:
            Subscription with plan or None
        """
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.id == subscription_id)
            .options(selectinload(Subscription.plan))
        )
        return result.scalar_one_or_none()

    async def update_subscription(
        self, subscription_id: UUID, update_data: SubscriptionUpdate
    ) -> Subscription:
        """
        Update subscription.

        Args:
            subscription_id: Subscription UUID
            update_data: Update data

        Returns:
            Updated subscription

        Raises:
            ValueError: If subscription not found
        """
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Update quantity if provided
        if update_data.quantity is not None:
            old_quantity = subscription.quantity
            subscription.quantity = update_data.quantity
            await self._create_history(
                subscription_id,
                "quantity_changed",
                str(old_quantity),
                str(update_data.quantity),
            )

        # Update cancel_at_period_end if provided
        if update_data.cancel_at_period_end is not None:
            old_value = subscription.cancel_at_period_end
            subscription.cancel_at_period_end = update_data.cancel_at_period_end
            if update_data.cancel_at_period_end and not old_value:
                # Mark for cancellation
                subscription.cancelled_at = datetime.utcnow()
                await self._create_history(
                    subscription_id,
                    "cancellation_scheduled",
                    None,
                    str(subscription.current_period_end),
                )

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def cancel_subscription(
        self, subscription_id: UUID, immediate: bool = False
    ) -> Subscription:
        """
        Cancel subscription.

        Args:
            subscription_id: Subscription UUID
            immediate: Cancel immediately or at period end

        Returns:
            Updated subscription

        Raises:
            ValueError: If subscription not found
        """
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        if immediate:
            # Immediate cancellation
            old_status = subscription.status
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = datetime.utcnow()
            subscription.cancel_at_period_end = False

            await self._create_history(
                subscription_id,
                "status_changed",
                old_status.value,
                SubscriptionStatus.CANCELLED.value,
            )
        else:
            # Cancel at period end
            subscription.cancel_at_period_end = True
            subscription.cancelled_at = datetime.utcnow()

            await self._create_history(
                subscription_id,
                "cancellation_scheduled",
                None,
                str(subscription.current_period_end),
            )

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def reactivate_subscription(self, subscription_id: UUID) -> Subscription:
        """
        Reactivate a cancelled subscription (before period end).

        Args:
            subscription_id: Subscription UUID

        Returns:
            Updated subscription

        Raises:
            ValueError: If subscription not found or already cancelled
        """
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ValueError("Cannot reactivate a cancelled subscription")

        if not subscription.cancel_at_period_end:
            raise ValueError("Subscription is not scheduled for cancellation")

        # Unset cancellation
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None

        await self._create_history(
            subscription_id,
            "cancellation_removed",
            None,
            None,
        )

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def pause_subscription(
        self, subscription_id: UUID, pause_data: SubscriptionPause
    ) -> Subscription:
        """
        Pause subscription.

        Args:
            subscription_id: Subscription UUID
            pause_data: Pause configuration

        Returns:
            Updated subscription

        Raises:
            ValueError: If subscription not found or already paused
        """
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        if subscription.status == SubscriptionStatus.PAUSED:
            raise ValueError("Subscription is already paused")

        old_status = subscription.status
        subscription.status = SubscriptionStatus.PAUSED
        subscription.pause_resumes_at = pause_data.resumes_at

        await self._create_history(
            subscription_id,
            "status_changed",
            old_status.value,
            SubscriptionStatus.PAUSED.value,
        )

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def resume_subscription(self, subscription_id: UUID) -> Subscription:
        """
        Resume a paused subscription.

        Args:
            subscription_id: Subscription UUID

        Returns:
            Updated subscription

        Raises:
            ValueError: If subscription not found or not paused
        """
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        if subscription.status != SubscriptionStatus.PAUSED:
            raise ValueError("Subscription is not paused")

        old_status = subscription.status
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.pause_resumes_at = None

        await self._create_history(
            subscription_id,
            "status_changed",
            old_status.value,
            SubscriptionStatus.ACTIVE.value,
        )

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def change_plan(
        self, subscription_id: UUID, plan_change: SubscriptionPlanChange
    ) -> Subscription:
        """
        Change subscription plan with optional proration and quantity changes.

        Args:
            subscription_id: Subscription UUID
            plan_change: Plan change configuration

        Returns:
            Updated subscription

        Raises:
            ValueError: If subscription/plan not found or plan inactive
        """
        # Load subscription with relationships
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan), selectinload(Subscription.account))
            .where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Verify new plan exists and is active
        plan_result = await self.db.execute(
            select(Plan).where(Plan.id == plan_change.new_plan_id)
        )
        new_plan = plan_result.scalar_one_or_none()
        if not new_plan:
            raise ValueError(f"Plan {plan_change.new_plan_id} not found")
        if not new_plan.active:
            raise ValueError(f"Plan {plan_change.new_plan_id} is inactive")

        old_plan = subscription.plan
        old_quantity = subscription.quantity
        new_quantity = plan_change.new_quantity if plan_change.new_quantity is not None else subscription.quantity

        # Determine if change should be immediate or scheduled
        is_immediate = plan_change.immediate or not plan_change.change_at_period_end

        if is_immediate:
            # Immediate plan change with proration
            old_plan_id = subscription.plan_id
            subscription.plan_id = plan_change.new_plan_id
            subscription.pending_plan_id = None
            subscription.quantity = new_quantity

            # Generate prorated invoice if plan or quantity changed
            if old_plan_id != plan_change.new_plan_id or old_quantity != new_quantity:
                from billing.services.invoice_service import InvoiceService
                invoice_service = InvoiceService(self.db)

                await invoice_service.create_proration_invoice(
                    subscription=subscription,
                    old_plan=old_plan,
                    new_plan=new_plan,
                    change_date=datetime.utcnow(),
                )

            await self._create_history(
                subscription_id,
                "plan_changed",
                str(old_plan_id),
                str(plan_change.new_plan_id),
            )

            if old_quantity != new_quantity:
                await self._create_history(
                    subscription_id,
                    "quantity_changed",
                    str(old_quantity),
                    str(new_quantity),
                )
        else:
            # Schedule plan change for next period
            subscription.pending_plan_id = plan_change.new_plan_id

            await self._create_history(
                subscription_id,
                "plan_change_scheduled",
                str(subscription.plan_id),
                str(plan_change.new_plan_id),
            )

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def list_subscriptions(
        self,
        account_id: UUID | None = None,
        status: SubscriptionStatus | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[Subscription], int]:
        """
        List subscriptions with pagination.

        Args:
            account_id: Filter by account (optional)
            status: Filter by status (optional)
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (subscriptions, total_count)
        """
        # Build query
        query = select(Subscription)

        if account_id:
            query = query.where(Subscription.account_id == account_id)
        if status:
            query = query.where(Subscription.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(Subscription.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total or 0

    async def _create_history(
        self,
        subscription_id: UUID,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
    ) -> None:
        """Create subscription history record."""
        history = SubscriptionHistory(
            subscription_id=subscription_id,
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
        )
        self.db.add(history)
        await self.db.flush()
