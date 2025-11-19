"""Service for dunning process and overdue account management."""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.models.account import Account, AccountStatus
from billing.models.invoice import Invoice, InvoiceStatus


class DunningService:
    """Service for managing overdue invoices and account dunning process."""

    # Dunning schedule: days overdue -> action
    REMINDER_DAY = 3
    WARNING_DAY = 7
    BLOCK_DAY = 14

    def __init__(self, db: AsyncSession):
        """Initialize dunning service with database session."""
        self.db = db

    async def check_overdue_invoices(self) -> list[dict]:
        """
        Check all overdue invoices and send appropriate notifications.

        Progressive dunning process:
        - Day 3: Send friendly reminder, keep account ACTIVE
        - Day 7: Send warning, change account to WARNING
        - Day 14: Block account, change to BLOCKED

        Returns:
            List of notification dictionaries sent
        """
        notifications = []

        # Find all open invoices past their due date
        query = select(Invoice).where(
            and_(
                Invoice.status == InvoiceStatus.OPEN,
                Invoice.due_date < datetime.utcnow(),
            )
        ).options(selectinload(Invoice.account))

        result = await self.db.execute(query)
        overdue_invoices = list(result.scalars().all())

        for invoice in overdue_invoices:
            days_overdue = (datetime.utcnow() - invoice.due_date).days

            # Determine action based on days overdue
            if days_overdue >= self.BLOCK_DAY:
                # Block service after 14 days
                notification = await self._block_account(invoice, days_overdue)
                if notification:
                    notifications.append(notification)
            elif days_overdue >= self.WARNING_DAY:
                # Send warning at 7 days
                notification = await self._send_warning(invoice, days_overdue)
                if notification:
                    notifications.append(notification)
            elif days_overdue >= self.REMINDER_DAY:
                # Send reminder at 3 days
                notification = await self._send_reminder(invoice, days_overdue)
                if notification:
                    notifications.append(notification)

        await self.db.flush()
        return notifications

    async def _send_reminder(self, invoice: Invoice, days_overdue: int) -> dict | None:
        """
        Send friendly payment reminder.

        Args:
            invoice: Overdue invoice
            days_overdue: Number of days past due date

        Returns:
            Notification dictionary if sent, None otherwise
        """
        # Only send reminder once (exactly at day 3, or within day 3-6 range)
        if days_overdue < self.REMINDER_DAY or days_overdue >= self.WARNING_DAY:
            return None

        account = invoice.account

        # Send notification via notification service
        notification = {
            "type": "reminder",
            "invoice_id": invoice.id,
            "account_id": account.id,
            "days_overdue": days_overdue,
            "amount_due": invoice.amount_due,
            "message": f"Friendly reminder: Your invoice #{invoice.number} of ${invoice.amount_due/100:.2f} is {days_overdue} days overdue. Please submit payment to avoid service disruption.",
            "sent_at": datetime.utcnow().isoformat(),
        }

        # Log notification (in production, send via NotificationService)
        await self._log_notification(notification)

        return notification

    async def _send_warning(self, invoice: Invoice, days_overdue: int) -> dict | None:
        """
        Send warning and change account status to WARNING.

        Args:
            invoice: Overdue invoice
            days_overdue: Number of days past due date

        Returns:
            Notification dictionary if sent, None otherwise
        """
        # Only send warning once (exactly at day 7, or within day 7-13 range)
        if days_overdue < self.WARNING_DAY or days_overdue >= self.BLOCK_DAY:
            return None

        account = invoice.account

        # Update account status to WARNING
        if account.status != AccountStatus.WARNING:
            account.status = AccountStatus.WARNING

        # Send notification
        notification = {
            "type": "warning",
            "invoice_id": invoice.id,
            "account_id": account.id,
            "days_overdue": days_overdue,
            "amount_due": invoice.amount_due,
            "message": f"Warning: Your invoice #{invoice.number} is now {days_overdue} days overdue. Your account has been marked for review. Please pay ${invoice.amount_due/100:.2f} immediately to avoid service interruption.",
            "sent_at": datetime.utcnow().isoformat(),
        }

        # Log notification
        await self._log_notification(notification)

        return notification

    async def _block_account(self, invoice: Invoice, days_overdue: int) -> dict | None:
        """
        Block account after 14 days of non-payment.

        Args:
            invoice: Overdue invoice
            days_overdue: Number of days past due date

        Returns:
            Notification dictionary if sent, None otherwise
        """
        if days_overdue < self.BLOCK_DAY:
            return None

        account = invoice.account

        # Block account
        if account.status != AccountStatus.BLOCKED:
            account.status = AccountStatus.BLOCKED

        # Send blocking notification
        notification = {
            "type": "service_blocked",
            "invoice_id": invoice.id,
            "account_id": account.id,
            "days_overdue": days_overdue,
            "amount_due": invoice.amount_due,
            "message": f"Your account has been suspended due to non-payment. Invoice #{invoice.number} is {days_overdue} days overdue. Pay ${invoice.amount_due/100:.2f} immediately to restore service.",
            "sent_at": datetime.utcnow().isoformat(),
        }

        # Log notification
        await self._log_notification(notification)

        return notification

    async def unblock_on_payment(self, account_id: UUID) -> None:
        """
        Unblock account when payment is received.

        Checks if all overdue invoices are paid, and if so, restores
        account to ACTIVE status.

        Args:
            account_id: Account UUID to potentially unblock
        """
        # Load account
        result = await self.db.execute(
            select(Account).where(Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Only unblock if currently blocked or warned
        if account.status not in [AccountStatus.BLOCKED, AccountStatus.WARNING]:
            return

        # Check for any remaining overdue invoices
        overdue_query = select(Invoice).where(
            and_(
                Invoice.account_id == account_id,
                Invoice.status == InvoiceStatus.OPEN,
                Invoice.due_date < datetime.utcnow(),
            )
        )

        overdue_result = await self.db.execute(overdue_query)
        overdue_invoices = list(overdue_result.scalars().all())

        # If no overdue invoices, restore account to ACTIVE
        if not overdue_invoices:
            account.status = AccountStatus.ACTIVE
            await self.db.flush()

    async def _log_notification(self, notification: dict) -> None:
        """
        Log notification for audit trail.

        In production, this would:
        1. Store notification in notifications table
        2. Send via NotificationService (email/SMS)
        3. Track delivery status

        Args:
            notification: Notification dictionary to log
        """
        # Placeholder: In production, persist to database and send via external service
        # For now, just validate structure
        required_fields = ["type", "invoice_id", "account_id", "message"]
        for field in required_fields:
            if field not in notification:
                raise ValueError(f"Notification missing required field: {field}")

    async def get_account_dunning_status(self, account_id: UUID) -> dict:
        """
        Get current dunning status for an account.

        Args:
            account_id: Account UUID

        Returns:
            Dictionary with dunning status information
        """
        # Load account
        result = await self.db.execute(
            select(Account).where(Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Find overdue invoices
        overdue_query = select(Invoice).where(
            and_(
                Invoice.account_id == account_id,
                Invoice.status == InvoiceStatus.OPEN,
                Invoice.due_date < datetime.utcnow(),
            )
        ).order_by(Invoice.due_date)

        overdue_result = await self.db.execute(overdue_query)
        overdue_invoices = list(overdue_result.scalars().all())

        # Calculate total overdue amount
        total_overdue = sum(inv.amount_due for inv in overdue_invoices)

        # Find most overdue invoice
        most_overdue_days = 0
        if overdue_invoices:
            oldest_invoice = overdue_invoices[0]
            most_overdue_days = (datetime.utcnow() - oldest_invoice.due_date).days

        return {
            "account_id": str(account_id),
            "status": account.status.value,
            "overdue_invoice_count": len(overdue_invoices),
            "total_overdue_amount": total_overdue,
            "most_overdue_days": most_overdue_days,
            "is_blocked": account.status == AccountStatus.BLOCKED,
            "next_action": self._determine_next_action(most_overdue_days, account.status),
        }

    def _determine_next_action(self, days_overdue: int, current_status: AccountStatus) -> str:
        """
        Determine next dunning action based on days overdue.

        Args:
            days_overdue: Number of days the oldest invoice is overdue
            current_status: Current account status

        Returns:
            Description of next action
        """
        if current_status == AccountStatus.BLOCKED:
            return "Account blocked - payment required to restore service"

        if days_overdue >= self.BLOCK_DAY:
            return f"Account will be blocked (overdue {days_overdue} days)"
        elif days_overdue >= self.WARNING_DAY:
            return f"Warning issued (day {days_overdue}), blocking in {self.BLOCK_DAY - days_overdue} days"
        elif days_overdue >= self.REMINDER_DAY:
            return f"Reminder sent (day {days_overdue}), warning in {self.WARNING_DAY - days_overdue} days"
        elif days_overdue > 0:
            return f"Grace period ({days_overdue} days overdue), reminder in {self.REMINDER_DAY - days_overdue} days"
        else:
            return "No action required"
