"""Invoice service for business logic."""
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from billing.models.invoice import Invoice, InvoiceStatus
from billing.models.subscription import Subscription, SubscriptionStatus
from billing.models.plan import Plan
from billing.models.account import Account
from billing.models.credit import Credit
from billing.models.payment_method import PaymentMethod
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

        # Add usage charges if plan is usage-based
        if plan.usage_type and plan.tiers:
            usage_charges = await self._calculate_usage_charges(
                subscription_id, period_start, period_end, plan
            )
            line_items.extend(usage_charges)

        # Calculate subtotal
        subtotal = sum(item["amount"] for item in line_items)

        # Calculate tax (will be enhanced with external service in T059)
        tax_amount = await self._calculate_tax(subscription.account, subtotal)

        # Calculate total
        total_amount = subtotal + tax_amount

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

        # Auto-apply available credits to invoice (T104)
        await self._auto_apply_credits(invoice)

        # Auto-attempt payment for the invoice (T076)
        await self._auto_attempt_payment(invoice)

        # Emit webhook event for invoice.created (T120)
        await self._emit_webhook_event("invoice.created", invoice)

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

    async def _calculate_usage_charges(
        self,
        subscription_id: UUID,
        period_start: datetime,
        period_end: datetime,
        plan: Plan,
    ) -> list[dict]:
        """
        Calculate usage charges for a billing period.

        Args:
            subscription_id: Subscription UUID
            period_start: Start of billing period
            period_end: End of billing period
            plan: Subscription plan with tier configuration

        Returns:
            List of usage line items
        """
        from billing.services.usage_service import UsageService

        usage_service = UsageService(self.db)
        line_items = []

        # Aggregate usage for all metrics in the period
        # For simplicity, we'll use a default metric or iterate if multiple exist
        # In a real system, metrics would be defined per plan
        metric = "api_calls"  # Default metric, could be plan.usage_metric

        # Get aggregated usage
        aggregation = await usage_service.aggregate_usage_for_period(
            subscription_id=subscription_id,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
        )

        if aggregation.total_quantity > 0:
            # Convert plan tiers to dict format for calculation
            tiers_dict = []
            if plan.tiers:
                for tier in plan.tiers:
                    if isinstance(tier, dict):
                        tiers_dict.append(tier)
                    else:
                        # Convert SQLAlchemy model to dict
                        tiers_dict.append({
                            "up_to": tier.get("up_to"),
                            "unit_amount": tier.get("unit_amount"),
                        })

            # Calculate tiered charges
            usage_charge = await usage_service.calculate_tiered_charges(
                total_quantity=aggregation.total_quantity,
                tiers=tiers_dict,
            )

            if usage_charge > 0:
                line_items.append({
                    "description": f"Usage: {metric} ({aggregation.total_quantity} units)",
                    "amount": usage_charge,
                    "quantity": aggregation.total_quantity,
                    "type": "usage",
                })

        return line_items

    async def _calculate_tax(self, account: Account, amount: int) -> int:
        """
        Calculate tax for an invoice using TaxService.

        Integrates with Stripe Tax API for accurate tax calculation based on
        customer location, with support for tax exemptions and EU VAT reverse charge.

        Args:
            account: Account to calculate tax for
            amount: Subtotal amount in cents

        Returns:
            Tax amount in cents
        """
        from billing.integrations.tax_service import TaxService

        # Initialize tax service
        tax_service = TaxService()

        # Calculate tax using TaxService (handles exemptions, VAT, etc.)
        tax_result = await tax_service.calculate_tax_for_invoice(
            account=account,
            amount=amount,
            currency=account.currency,
        )

        # Extract tax amount from result
        tax_amount = tax_result.get("amount", 0)

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

    async def _auto_attempt_payment(self, invoice: Invoice) -> None:
        """
        Automatically attempt payment for an invoice (T076).

        Args:
            invoice: Invoice to process payment for
        """
        from billing.services.payment_service import PaymentService

        # Only attempt payment for OPEN invoices
        if invoice.status != InvoiceStatus.OPEN:
            return

        # Get payment method for account
        payment_method_result = await self.db.execute(
            select(PaymentMethod)
            .where(
                PaymentMethod.account_id == invoice.account_id,
                PaymentMethod.is_default == True,  # noqa: E712
            )
            .limit(1)
        )
        payment_method = payment_method_result.scalar_one_or_none()

        # Only attempt payment if a payment method exists
        # If no payment method, invoice stays OPEN for manual payment
        if not payment_method:
            return

        # Create payment service and attempt payment
        payment_service = PaymentService(self.db)

        try:
            await payment_service.attempt_payment(
                invoice_id=invoice.id,
                payment_method_id=payment_method.id,
            )
        except Exception:
            # Payment attempt failed, but invoice is still created
            # Retry logic will handle this via background workers
            pass

    async def _auto_apply_credits(self, invoice: Invoice) -> None:
        """
        Automatically apply available credits to an invoice (T104).

        Credits are applied in FIFO order to reduce the invoice amount_due.
        This is called during invoice generation to automatically use
        account credits.

        Args:
            invoice: Invoice to apply credits to
        """
        if invoice.status != InvoiceStatus.OPEN:
            return

        # Import here to avoid circular dependency
        from billing.services.credit_service import CreditService

        credit_service = CreditService(self.db)

        try:
            # Apply all available credits to this invoice
            credits_applied = await credit_service.apply_credits_to_invoice(
                invoice_id=invoice.id
            )

            if credits_applied > 0:
                # Refresh invoice to get updated amount_due
                await self.db.refresh(invoice)

        except Exception:
            # If credit application fails, continue with invoice generation
            # Credits can be applied manually later
            pass

    async def void_invoice(self, invoice_id: UUID, reason: str = "Voided") -> Invoice:
        """
        Void an invoice and create a refund credit if it was already paid.

        Voiding an invoice:
        - Changes status to VOID
        - If invoice was PAID, creates a credit for the paid amount
        - Cannot void DRAFT invoices (delete instead)

        Args:
            invoice_id: Invoice UUID to void
            reason: Reason for voiding

        Returns:
            Voided invoice

        Raises:
            ValueError: If invoice doesn't exist or cannot be voided
        """
        # Load invoice
        result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        if invoice.status == InvoiceStatus.VOID:
            raise ValueError(f"Invoice {invoice_id} is already voided")

        original_status = invoice.status
        was_paid = invoice.status == InvoiceStatus.PAID

        # If invoice was paid, create a refund credit for the paid amount
        if was_paid:
            from billing.services.credit_service import CreditService
            from billing.schemas.credit import CreditCreate

            credit_service = CreditService(self.db)
            await credit_service.create_credit(
                CreditCreate(
                    account_id=invoice.account_id,
                    amount=invoice.amount_paid or invoice.total,
                    currency=invoice.currency,
                    reason=f"Refund from voided invoice {invoice.number}: {reason}",
                )
            )

        # Void the invoice
        invoice.status = InvoiceStatus.VOID
        invoice.voided_at = datetime.utcnow()
        invoice.extra_metadata["void_reason"] = reason
        invoice.extra_metadata["original_status"] = original_status.value
        flag_modified(invoice, "extra_metadata")

        await self.db.flush()
        await self.db.refresh(invoice)

        return invoice

    async def _emit_webhook_event(self, event_type: str, invoice: Invoice) -> None:
        """
        Emit webhook event for invoice state changes.

        Args:
            event_type: Event type (e.g., "invoice.created", "invoice.paid")
            invoice: Invoice object
        """
        try:
            from billing.services.webhook_service import WebhookService
            from billing.api.v1.webhook_endpoints import get_endpoints_for_event

            webhook_service = WebhookService(self.db)

            # Create webhook payload
            payload = {
                "invoice_id": str(invoice.id),
                "account_id": str(invoice.account_id),
                "subscription_id": str(invoice.subscription_id) if invoice.subscription_id else None,
                "number": invoice.number,
                "status": invoice.status.value,
                "amount_due": invoice.amount_due,
                "amount_paid": invoice.amount_paid,
                "tax": invoice.tax,
                "currency": invoice.currency,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            }

            # Get webhook endpoints subscribed to this event
            endpoints = get_endpoints_for_event(event_type)

            # Create webhook event for each subscribed endpoint, or one with "system" endpoint if none
            if not endpoints:
                # Create event with system endpoint for audit trail
                await webhook_service.create_event(
                    event_type=event_type,
                    payload=payload,
                    endpoint_url="system",
                )
            else:
                # Create webhook event for each subscribed endpoint
                for endpoint_url in endpoints:
                    await webhook_service.create_event(
                        event_type=event_type,
                        payload=payload,
                        endpoint_url=endpoint_url,
                    )

        except Exception:
            # Don't let webhook failures break invoice operations
            pass
