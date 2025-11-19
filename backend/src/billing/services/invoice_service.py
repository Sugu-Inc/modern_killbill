"""Invoice service for business logic."""
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.subscription import Subscription, SubscriptionStatus
from billing.models.plan import Plan
from billing.models.account import Account
from billing.models.credit import Credit
from billing.schemas.invoice import InvoiceCreate, InvoiceLineItem


class InvoiceService:
    """Service layer for invoice operations."""

    def __init__(self, db: AsyncSession):
        """Initialize invoice service with database session."""
        self.db = db

    async def generate_invoice_number(self) -> str:
        """
        Generate sequential invoice number.

        Format: INV-{sequential_number} (e.g., INV-0001, INV-0002)

        Returns:
            Invoice number string
        """
        # Get the count of existing invoices
        result = await self.db.execute(select(func.count()).select_from(Invoice))
        count = result.scalar() or 0

        # Generate number with padding
        return f"INV-{count + 1:06d}"

    async def generate_invoice_for_subscription(
        self,
        subscription_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> Invoice:
        """
        Generate invoice for a subscription billing cycle.

        Args:
            subscription_id: Subscription UUID
            period_start: Billing period start (defaults to current_period_start)
            period_end: Billing period end (defaults to current_period_end)

        Returns:
            Generated invoice

        Raises:
            ValueError: If subscription not found or already has invoice for period
        """
        # Load subscription with plan
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan), selectinload(Subscription.account))
            .where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Use subscription period if not provided
        if not period_start:
            period_start = subscription.current_period_start
        if not period_end:
            period_end = subscription.current_period_end

        # Check if invoice already exists for this period
        existing_invoice = await self.db.execute(
            select(Invoice).where(
                Invoice.subscription_id == subscription_id,
                Invoice.extra_metadata["period_start"].astext == period_start.isoformat(),
                Invoice.status != InvoiceStatus.VOID,
            )
        )
        if existing_invoice.scalar_one_or_none():
            raise ValueError(f"Invoice already exists for subscription {subscription_id} period {period_start}")

        # Calculate line items
        line_items = []

        # Base subscription charge
        plan = subscription.plan
        base_amount = plan.amount * subscription.quantity

        line_items.append(
            InvoiceLineItem(
                description=f"{plan.name} ({period_start.strftime('%Y-%m-%d')} - {period_end.strftime('%Y-%m-%d')})",
                amount=base_amount,
                quantity=subscription.quantity,
                type="subscription",
            ).model_dump()
        )

        # Calculate subtotal
        subtotal = sum(item["amount"] for item in line_items)

        # Calculate tax (will be enhanced with external service in T059)
        tax_amount = await self._calculate_tax(subscription.account, subtotal)

        # Calculate total
        total_amount = subtotal + tax_amount

        # Apply available credits
        credits_applied = await self._get_available_credits(subscription.account_id)
        if credits_applied:
            credit_amount = min(credits_applied, total_amount)
            if credit_amount > 0:
                line_items.append(
                    InvoiceLineItem(
                        description="Account Credit",
                        amount=-credit_amount,
                        quantity=1,
                        type="credit",
                    ).model_dump()
                )
                total_amount -= credit_amount

        # Generate invoice number
        invoice_number = await self.generate_invoice_number()

        # Create invoice
        invoice = Invoice(
            account_id=subscription.account_id,
            subscription_id=subscription_id,
            number=invoice_number,
            status=InvoiceStatus.OPEN,
            amount_due=total_amount,
            amount_paid=0,
            tax=tax_amount,
            currency=plan.currency,
            due_date=period_end,
            line_items=line_items,
            extra_metadata={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "subtotal": subtotal,
            },
        )

        self.db.add(invoice)
        await self.db.flush()
        await self.db.refresh(invoice)

        return invoice

    async def calculate_proration(
        self,
        old_amount: int,
        new_amount: int,
        period_start: datetime,
        period_end: datetime,
        change_date: datetime | None = None,
    ) -> dict[str, int]:
        """
        Calculate prorated amount for mid-cycle changes.

        Args:
            old_amount: Previous plan amount in cents
            new_amount: New plan amount in cents
            period_start: Billing period start
            period_end: Billing period end
            change_date: When the change occurs (defaults to now)

        Returns:
            Dict with 'credit' (unused time on old plan) and 'charge' (time on new plan)
        """
        if not change_date:
            change_date = datetime.utcnow()

        # Calculate total period in seconds
        total_period = (period_end - period_start).total_seconds()

        # Calculate unused time in seconds
        unused_time = (period_end - change_date).total_seconds()

        # Calculate time used on new plan
        used_on_new = unused_time

        # Proration ratio
        proration_ratio = Decimal(str(unused_time)) / Decimal(str(total_period))

        # Credit for unused time on old plan
        credit = int(Decimal(str(old_amount)) * proration_ratio)

        # Charge for time on new plan
        charge = int(Decimal(str(new_amount)) * proration_ratio)

        return {
            "credit": credit,
            "charge": charge,
            "net": charge - credit,
        }

    async def create_proration_invoice(
        self,
        subscription: Subscription,
        old_plan: Plan,
        new_plan: Plan,
        change_date: datetime,
    ) -> Invoice:
        """
        Create prorated invoice for plan change.

        Args:
            subscription: Subscription being changed
            old_plan: Previous plan
            new_plan: New plan
            change_date: When change occurred

        Returns:
            Prorated invoice
        """
        # Calculate proration amounts
        proration = await self.calculate_proration(
            old_amount=old_plan.amount * subscription.quantity,
            new_amount=new_plan.amount * subscription.quantity,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            change_date=change_date,
        )

        line_items = []

        # Credit for old plan (if applicable)
        if proration["credit"] > 0:
            line_items.append(
                InvoiceLineItem(
                    description=f"Credit for unused time on {old_plan.name}",
                    amount=-proration["credit"],
                    quantity=subscription.quantity,
                    type="proration_credit",
                ).model_dump()
            )

        # Charge for new plan
        if proration["charge"] > 0:
            line_items.append(
                InvoiceLineItem(
                    description=f"Prorated charge for {new_plan.name}",
                    amount=proration["charge"],
                    quantity=subscription.quantity,
                    type="proration_charge",
                ).model_dump()
            )

        # Calculate total
        subtotal = sum(item["amount"] for item in line_items)
        tax_amount = await self._calculate_tax(subscription.account, subtotal)
        total_amount = max(0, subtotal + tax_amount)  # Ensure non-negative

        # Generate invoice number
        invoice_number = await self.generate_invoice_number()

        # Create invoice
        invoice = Invoice(
            account_id=subscription.account_id,
            subscription_id=subscription.id,
            number=invoice_number,
            status=InvoiceStatus.OPEN if total_amount > 0 else InvoiceStatus.PAID,
            amount_due=total_amount,
            amount_paid=0 if total_amount > 0 else total_amount,
            tax=tax_amount,
            currency=new_plan.currency,
            due_date=datetime.utcnow() + timedelta(days=7),
            paid_at=datetime.utcnow() if total_amount == 0 else None,
            line_items=line_items,
            extra_metadata={
                "proration": True,
                "old_plan_id": str(old_plan.id),
                "new_plan_id": str(new_plan.id),
                "change_date": change_date.isoformat(),
            },
        )

        self.db.add(invoice)
        await self.db.flush()
        await self.db.refresh(invoice)

        return invoice

    async def void_invoice(self, invoice_id: UUID, reason: str) -> Invoice:
        """
        Void an invoice (cancel it).

        Args:
            invoice_id: Invoice UUID
            reason: Reason for voiding

        Returns:
            Voided invoice

        Raises:
            ValueError: If invoice not found, already paid, or already void
        """
        # Load invoice
        result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # Check if can be voided
        if invoice.status == InvoiceStatus.VOID:
            raise ValueError(f"Invoice {invoice_id} is already voided")
        if invoice.status == InvoiceStatus.PAID:
            raise ValueError(f"Invoice {invoice_id} is paid and cannot be voided. Issue a credit instead.")

        # Void invoice
        invoice.status = InvoiceStatus.VOID
        invoice.voided_at = datetime.utcnow()
        invoice.extra_metadata = {
            **invoice.extra_metadata,
            "void_reason": reason,
            "voided_at": datetime.utcnow().isoformat(),
        }

        await self.db.flush()
        await self.db.refresh(invoice)

        return invoice

    async def apply_credit_to_invoice(self, invoice_id: UUID, credit_id: UUID) -> Invoice:
        """
        Apply a credit to an invoice.

        Args:
            invoice_id: Invoice UUID
            credit_id: Credit UUID

        Returns:
            Updated invoice

        Raises:
            ValueError: If invoice or credit not found, or credit already applied
        """
        # Load invoice
        result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # Load credit
        credit_result = await self.db.execute(
            select(Credit).where(Credit.id == credit_id)
        )
        credit = credit_result.scalar_one_or_none()
        if not credit:
            raise ValueError(f"Credit {credit_id} not found")

        if credit.applied_to_invoice_id:
            raise ValueError(f"Credit {credit_id} has already been applied")

        # Apply credit to invoice
        credit_amount = min(credit.amount, invoice.amount_due - invoice.amount_paid)

        # Update invoice
        invoice.amount_paid += credit_amount
        if invoice.amount_paid >= invoice.amount_due:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.utcnow()

        # Update credit
        credit.applied_to_invoice_id = invoice_id

        await self.db.flush()
        await self.db.refresh(invoice)

        return invoice

    async def get_invoice(self, invoice_id: UUID) -> Invoice | None:
        """
        Get invoice by ID.

        Args:
            invoice_id: Invoice UUID

        Returns:
            Invoice or None if not found
        """
        result = await self.db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.account),
                selectinload(Invoice.subscription),
                selectinload(Invoice.payments),
            )
            .where(Invoice.id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def list_invoices(
        self,
        account_id: UUID | None = None,
        subscription_id: UUID | None = None,
        status: InvoiceStatus | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[Invoice], int]:
        """
        List invoices with pagination and filtering.

        Args:
            account_id: Filter by account ID
            subscription_id: Filter by subscription ID
            status: Filter by status
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (invoices, total_count)
        """
        # Build query
        query = select(Invoice)

        if account_id:
            query = query.where(Invoice.account_id == account_id)
        if subscription_id:
            query = query.where(Invoice.subscription_id == subscription_id)
        if status:
            query = query.where(Invoice.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(Invoice.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        invoices = result.scalars().all()

        return list(invoices), total or 0

    async def _calculate_tax(self, account: Account, amount: int) -> int:
        """
        Calculate tax for an invoice.

        This is a placeholder that will be enhanced with external tax service in T059.

        Args:
            account: Account to calculate tax for
            amount: Subtotal amount in cents

        Returns:
            Tax amount in cents
        """
        # Skip tax for tax-exempt accounts
        if account.tax_exempt:
            return 0

        # Placeholder: Apply simple 10% tax rate
        # TODO (T059): Integrate with Stripe Tax API or Avalara
        tax_rate = Decimal("0.10")
        tax_amount = int(Decimal(str(amount)) * tax_rate)

        return tax_amount

    async def _get_available_credits(self, account_id: UUID) -> int:
        """
        Get total available credits for an account.

        Args:
            account_id: Account UUID

        Returns:
            Total available credit amount in cents
        """
        result = await self.db.execute(
            select(func.sum(Credit.amount))
            .where(
                Credit.account_id == account_id,
                Credit.applied_to_invoice_id.is_(None),
            )
        )
        total_credits = result.scalar()
        return total_credits or 0
