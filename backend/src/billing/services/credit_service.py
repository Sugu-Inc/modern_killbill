"""Service for managing account credits and refunds."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.credit import Credit
from billing.models.account import Account
from billing.models.invoice import Invoice, InvoiceStatus
from billing.schemas.credit import CreditCreate, CreditBalance
from billing.utils.audit import audit_create


class CreditService:
    """Service for managing account credits and automatic application to invoices."""

    def __init__(self, db: AsyncSession):
        """Initialize credit service with database session."""
        self.db = db

    @audit_create("credit")
    async def create_credit(self, credit_data: CreditCreate, current_user: Optional[dict] = None) -> Credit:
        """
        Create a new credit for an account.

        Credits can be created for:
        - Refunds from voided invoices
        - Goodwill credits for customer satisfaction
        - Promotional credits
        - Discounts

        Args:
            credit_data: Credit creation data

        Returns:
            Created credit

        Raises:
            ValueError: If account doesn't exist
        """
        # Verify account exists
        account_result = await self.db.execute(
            select(Account).where(Account.id == credit_data.account_id)
        )
        account = account_result.scalar_one_or_none()

        if not account:
            raise ValueError(f"Account {credit_data.account_id} not found")

        # Create credit
        credit = Credit(
            account_id=credit_data.account_id,
            amount=credit_data.amount,
            currency=credit_data.currency,
            reason=credit_data.reason,
            expires_at=credit_data.expires_at if hasattr(credit_data, 'expires_at') else None,
        )

        self.db.add(credit)
        await self.db.flush()
        await self.db.refresh(credit)

        return credit

    async def get_available_credits_for_account(
        self, account_id: UUID, currency: str = "USD"
    ) -> list[Credit]:
        """
        Get all available (unapplied, non-expired) credits for an account.

        Args:
            account_id: Account UUID
            currency: Currency filter (default: USD)

        Returns:
            List of available credits, ordered by creation date (oldest first)
        """
        now = datetime.utcnow()

        query = select(Credit).where(
            and_(
                Credit.account_id == account_id,
                Credit.currency == currency,
                Credit.applied_to_invoice_id.is_(None),  # Not yet applied
                # Include credits with no expiration or not yet expired
                (Credit.expires_at.is_(None)) | (Credit.expires_at > now),
            )
        ).order_by(Credit.created_at)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def apply_credits_to_invoice(
        self, invoice_id: UUID, max_amount: int | None = None
    ) -> int:
        """
        Apply available credits to an invoice.

        Credits are applied in FIFO order (oldest first) until:
        - Invoice is fully covered (amount_due = 0), or
        - All available credits are exhausted, or
        - max_amount is reached (if specified)

        Args:
            invoice_id: Invoice UUID to apply credits to
            max_amount: Optional maximum amount of credits to apply (in cents)

        Returns:
            Total amount of credits applied (in cents)

        Raises:
            ValueError: If invoice doesn't exist or is not in OPEN status
        """
        # Load invoice
        invoice_result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        if invoice.status != InvoiceStatus.OPEN:
            raise ValueError(f"Cannot apply credits to invoice with status {invoice.status}")

        # Get available credits for this account
        available_credits = await self.get_available_credits_for_account(
            account_id=invoice.account_id,
            currency=invoice.currency,
        )

        if not available_credits:
            return 0

        total_applied = 0
        remaining_invoice_amount = invoice.amount_due

        for credit in available_credits:
            if remaining_invoice_amount <= 0:
                break

            if max_amount and total_applied >= max_amount:
                break

            # Determine how much of this credit to apply
            applicable_amount = min(credit.amount, remaining_invoice_amount)

            if max_amount:
                applicable_amount = min(applicable_amount, max_amount - total_applied)

            # Apply credit to invoice
            if applicable_amount >= credit.amount:
                # Use entire credit
                credit.applied_to_invoice_id = invoice.id
                credit.applied_at = datetime.utcnow()
                total_applied += credit.amount
                remaining_invoice_amount -= credit.amount
            else:
                # Partial credit application - split the credit
                # Apply part of the credit
                credit.applied_to_invoice_id = invoice.id
                credit.applied_at = datetime.utcnow()
                original_amount = credit.amount
                credit.amount = applicable_amount  # Update to applied amount

                # Create new credit for remaining balance
                remaining_credit = Credit(
                    account_id=credit.account_id,
                    amount=original_amount - applicable_amount,
                    currency=credit.currency,
                    reason=f"Remaining balance from credit (original: {original_amount} cents)",
                    expires_at=credit.expires_at,
                )
                self.db.add(remaining_credit)

                total_applied += applicable_amount
                remaining_invoice_amount -= applicable_amount

        # Update invoice amount_due
        invoice.amount_due = remaining_invoice_amount

        await self.db.flush()
        return total_applied

    async def get_account_credit_balance(self, account_id: UUID, currency: str = "USD") -> CreditBalance:
        """
        Get complete credit balance summary for an account.

        Args:
            account_id: Account UUID
            currency: Currency filter

        Returns:
            CreditBalance with totals for available, expired, and applied credits
        """
        now = datetime.utcnow()

        # Get all credits for account
        all_credits_result = await self.db.execute(
            select(Credit).where(
                and_(
                    Credit.account_id == account_id,
                    Credit.currency == currency,
                )
            )
        )
        all_credits = list(all_credits_result.scalars().all())

        total_credits = sum(c.amount for c in all_credits)

        # Available credits (unapplied, non-expired)
        available_credits = sum(
            c.amount
            for c in all_credits
            if c.applied_to_invoice_id is None
            and (c.expires_at is None or c.expires_at > now)
        )

        # Expired credits (unapplied but expired)
        expired_credits = sum(
            c.amount
            for c in all_credits
            if c.applied_to_invoice_id is None
            and c.expires_at is not None
            and c.expires_at <= now
        )

        # Applied credits
        applied_credits = sum(c.amount for c in all_credits if c.applied_to_invoice_id is not None)

        return CreditBalance(
            account_id=account_id,
            total_credits=total_credits,
            currency=currency,
            available_credits=available_credits,
            expired_credits=expired_credits,
            applied_credits=applied_credits,
        )

    async def create_refund_credit(
        self, invoice_id: UUID, amount: int | None = None, reason: str | None = None
    ) -> Credit:
        """
        Create a credit from a voided/refunded invoice.

        Args:
            invoice_id: Invoice UUID that was voided
            amount: Refund amount (defaults to full invoice amount)
            reason: Reason for refund

        Returns:
            Created credit

        Raises:
            ValueError: If invoice doesn't exist
        """
        # Load invoice
        invoice_result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        refund_amount = amount if amount is not None else invoice.total
        refund_reason = reason if reason else f"Refund from voided invoice #{invoice.number}"

        # Create credit
        credit = await self.create_credit(
            CreditCreate(
                account_id=invoice.account_id,
                amount=refund_amount,
                currency=invoice.currency,
                reason=refund_reason,
            )
        )

        return credit

    async def list_credits_for_account(
        self,
        account_id: UUID,
        page: int = 1,
        page_size: int = 50,
        include_applied: bool = True,
        include_expired: bool = True,
    ) -> tuple[list[Credit], int]:
        """
        List all credits for an account with pagination.

        Args:
            account_id: Account UUID
            page: Page number (1-indexed)
            page_size: Items per page
            include_applied: Include already-applied credits
            include_expired: Include expired credits

        Returns:
            Tuple of (credits list, total count)
        """
        conditions = [Credit.account_id == account_id]

        if not include_applied:
            conditions.append(Credit.applied_to_invoice_id.is_(None))

        if not include_expired:
            now = datetime.utcnow()
            conditions.append(
                (Credit.expires_at.is_(None)) | (Credit.expires_at > now)
            )

        # Count total
        count_query = select(Credit).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = len(list(count_result.scalars().all()))

        # Get paginated results
        query = (
            select(Credit)
            .where(and_(*conditions))
            .order_by(Credit.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(query)
        credits = list(result.scalars().all())

        return credits, total
