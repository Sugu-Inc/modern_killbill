"""Service for usage-based billing operations."""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.models.usage_record import UsageRecord
from billing.models.subscription import Subscription
from billing.models.plan import Plan
from billing.models.invoice import Invoice, InvoiceStatus
from billing.schemas.usage_record import UsageRecordCreate, UsageAggregation


class UsageService:
    """Service for recording and aggregating usage events."""

    def __init__(self, db: AsyncSession):
        """Initialize usage service with database session."""
        self.db = db

    async def record_usage(self, usage_data: UsageRecordCreate) -> UsageRecord:
        """
        Record a usage event with idempotency.

        Args:
            usage_data: Usage record creation data

        Returns:
            Created or existing usage record

        Raises:
            ValueError: If subscription not found
        """
        # Check for existing record with same idempotency key
        existing_result = await self.db.execute(
            select(UsageRecord).where(
                UsageRecord.idempotency_key == usage_data.idempotency_key
            )
        )
        existing_record = existing_result.scalar_one_or_none()

        if existing_record:
            # Idempotency: return existing record
            return existing_record

        # Verify subscription exists and is active
        subscription_result = await self.db.execute(
            select(Subscription).where(Subscription.id == usage_data.subscription_id)
        )
        subscription = subscription_result.scalar_one_or_none()

        if not subscription:
            raise ValueError(f"Subscription {usage_data.subscription_id} not found")

        # Check if subscription is paused or inactive
        from billing.models.subscription import SubscriptionStatus
        if subscription.status in [SubscriptionStatus.PAUSED, SubscriptionStatus.CANCELLED]:
            raise ValueError(f"Cannot record usage for paused or inactive subscription")

        # Create new usage record
        usage_record = UsageRecord(
            subscription_id=usage_data.subscription_id,
            metric=usage_data.metric,
            quantity=usage_data.quantity,
            timestamp=usage_data.timestamp,
            idempotency_key=usage_data.idempotency_key,
            extra_metadata=usage_data.extra_metadata,
        )

        self.db.add(usage_record)
        await self.db.flush()
        await self.db.refresh(usage_record)

        return usage_record

    async def aggregate_usage_for_period(
        self,
        subscription_id: UUID,
        metric: str,
        period_start: datetime,
        period_end: datetime,
    ) -> UsageAggregation:
        """
        Aggregate usage for a subscription and metric within a time period.

        Args:
            subscription_id: Subscription UUID
            metric: Usage metric name
            period_start: Start of aggregation period
            period_end: End of aggregation period

        Returns:
            Aggregated usage data
        """
        # Query total quantity
        result = await self.db.execute(
            select(func.sum(UsageRecord.quantity))
            .where(
                UsageRecord.subscription_id == subscription_id,
                UsageRecord.metric == metric,
                UsageRecord.timestamp >= period_start,
                UsageRecord.timestamp < period_end,
            )
        )
        total_quantity = result.scalar() or 0

        return UsageAggregation(
            subscription_id=subscription_id,
            metric=metric,
            total_quantity=total_quantity,
            period_start=period_start,
            period_end=period_end,
        )

    async def calculate_tiered_charges(
        self,
        total_quantity: int,
        tiers: list[dict],
    ) -> int:
        """
        Calculate charges based on tiered pricing.

        Args:
            total_quantity: Total units consumed
            tiers: List of pricing tiers (from Plan.tiers)

        Returns:
            Total charge in cents

        Example:
            Tiers: [{up_to: 1000, unit_amount: 10}, {up_to: None, unit_amount: 5}]
            Quantity: 1500
            Result: (1000 * 10) + (500 * 5) = 10000 + 2500 = 12500 cents
        """
        total_charge = 0
        remaining_quantity = total_quantity
        previous_threshold = 0

        # Sort tiers by up_to (None last)
        sorted_tiers = sorted(tiers, key=lambda t: t.get("up_to") or float("inf"))

        for tier in sorted_tiers:
            tier_limit = tier.get("up_to")
            unit_amount = tier.get("unit_amount", 0)

            if tier_limit is None:
                # Last tier (unlimited)
                quantity_in_tier = remaining_quantity
            else:
                # Calculate quantity in this tier
                tier_size = tier_limit - previous_threshold
                quantity_in_tier = min(remaining_quantity, tier_size)

            # Add charge for this tier
            total_charge += quantity_in_tier * unit_amount
            remaining_quantity -= quantity_in_tier

            if remaining_quantity <= 0:
                break

            previous_threshold = tier_limit if tier_limit is not None else previous_threshold

        return total_charge

    async def list_usage_records(
        self,
        subscription_id: UUID | None = None,
        metric: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[UsageRecord], int]:
        """
        List usage records with optional filters.

        Args:
            subscription_id: Filter by subscription (optional)
            metric: Filter by metric (optional)
            start_time: Filter by timestamp >= start_time (optional)
            end_time: Filter by timestamp < end_time (optional)
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (usage_records, total_count)
        """
        query = select(UsageRecord)

        # Apply filters
        if subscription_id:
            query = query.where(UsageRecord.subscription_id == subscription_id)
        if metric:
            query = query.where(UsageRecord.metric == metric)
        if start_time:
            query = query.where(UsageRecord.timestamp >= start_time)
        if end_time:
            query = query.where(UsageRecord.timestamp < end_time)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.order_by(UsageRecord.timestamp.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        records = list(result.scalars().all())

        return records, total

    async def process_late_usage(self, subscription_id: UUID) -> Invoice | None:
        """
        Process late usage events and generate supplemental invoice.

        Late usage: events that arrive after an invoice has already been
        generated for their billing period.

        Args:
            subscription_id: Subscription UUID

        Returns:
            Supplemental invoice if late usage found, None otherwise
        """
        # Load subscription with plan
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Find the most recent invoice for this subscription
        invoice_result = await self.db.execute(
            select(Invoice)
            .where(
                Invoice.subscription_id == subscription_id,
                Invoice.status != InvoiceStatus.VOID,
            )
            .order_by(Invoice.created_at.desc())
            .limit(1)
        )
        latest_invoice = invoice_result.scalar_one_or_none()

        if not latest_invoice:
            return None  # No invoice to compare against

        # Get the period from invoice metadata
        period_start_str = latest_invoice.extra_metadata.get("period_start")
        period_end_str = latest_invoice.extra_metadata.get("period_end")

        if not period_start_str or not period_end_str:
            return None  # Invoice doesn't have period metadata

        period_start = datetime.fromisoformat(period_start_str)
        period_end = datetime.fromisoformat(period_end_str)

        # Find usage events with timestamp in the invoiced period but created after the invoice
        late_usage_result = await self.db.execute(
            select(UsageRecord)
            .where(
                UsageRecord.subscription_id == subscription_id,
                UsageRecord.timestamp >= period_start,
                UsageRecord.timestamp < period_end,
                UsageRecord.created_at > latest_invoice.created_at,
            )
        )
        late_usage_records = list(late_usage_result.scalars().all())

        if not late_usage_records:
            return None

        # Aggregate late usage by metric
        usage_by_metric: dict[str, int] = {}
        for record in late_usage_records:
            usage_by_metric[record.metric] = usage_by_metric.get(record.metric, 0) + record.quantity

        # Calculate charges based on plan tiers
        from billing.services.invoice_service import InvoiceService
        invoice_service = InvoiceService(self.db)

        line_items = []
        total_charge = 0

        for metric, quantity in usage_by_metric.items():
            if subscription.plan.tiers:
                # Convert tiers to dict format
                tiers_dict = [
                    {"up_to": tier.get("up_to"), "unit_amount": tier.get("unit_amount")}
                    for tier in subscription.plan.tiers
                ]
                charge = await self.calculate_tiered_charges(quantity, tiers_dict)

                line_items.append({
                    "description": f"Late usage: {metric} ({quantity} units)",
                    "quantity": quantity,
                    "amount": charge,
                    "type": "late_usage",
                })
                total_charge += charge

        if total_charge == 0:
            return None

        # Generate supplemental invoice
        invoice_number = await invoice_service.generate_invoice_number()
        now = datetime.utcnow()

        supplemental_invoice = Invoice(
            account_id=subscription.account_id,
            subscription_id=subscription.id,
            number=invoice_number,
            status=InvoiceStatus.OPEN,
            amount_due=total_charge,
            amount_paid=0,
            tax=0,  # Simplified: no tax on supplemental
            currency=subscription.plan.currency,
            due_date=now + timedelta(days=7),
            paid_at=None,
            line_items=line_items,
            extra_metadata={
                "supplemental": True,
                "late_usage": True,
                "original_period_end": period_end.isoformat(),
            },
        )

        self.db.add(supplemental_invoice)
        await self.db.flush()
        await self.db.refresh(supplemental_invoice)

        return supplemental_invoice
