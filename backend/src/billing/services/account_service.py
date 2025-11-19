"""Account service for business logic."""
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.account import Account, AccountStatus
from billing.schemas.account import AccountCreate, AccountUpdate


class AccountService:
    """Service layer for account operations."""

    def __init__(self, db: AsyncSession):
        """Initialize account service with database session."""
        self.db = db

    async def create_account(self, account_data: AccountCreate) -> Account:
        """
        Create a new account.

        Args:
            account_data: Account creation data

        Returns:
            Created account

        Raises:
            ValueError: If email already exists
        """
        # Check if email already exists
        existing = await self.get_account_by_email(account_data.email)
        if existing:
            raise ValueError(f"Account with email {account_data.email} already exists")

        # Create new account
        account = Account(
            email=account_data.email,
            name=account_data.name,
            currency=account_data.currency,
            timezone=account_data.timezone,
            tax_exempt=account_data.tax_exempt,
            tax_id=account_data.tax_id,
            vat_id=account_data.vat_id,
            extra_metadata=account_data.extra_metadata,
            status=AccountStatus.ACTIVE,
        )

        self.db.add(account)
        await self.db.flush()
        await self.db.refresh(account)

        return account

    async def get_account(self, account_id: UUID) -> Account | None:
        """
        Get account by ID.

        Args:
            account_id: Account UUID

        Returns:
            Account or None if not found
        """
        result = await self.db.execute(
            select(Account).where(Account.id == account_id, Account.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_account_by_email(self, email: str) -> Account | None:
        """
        Get account by email.

        Args:
            email: Account email

        Returns:
            Account or None if not found
        """
        result = await self.db.execute(
            select(Account).where(Account.email == email, Account.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def update_account(self, account_id: UUID, update_data: AccountUpdate) -> Account:
        """
        Update account.

        Args:
            account_id: Account UUID
            update_data: Update data

        Returns:
            Updated account

        Raises:
            ValueError: If account not found
        """
        account = await self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(account, field, value)

        await self.db.flush()
        await self.db.refresh(account)

        return account

    async def delete_account(self, account_id: UUID) -> Account:
        """
        Soft delete account.

        Args:
            account_id: Account UUID

        Returns:
            Account: The soft-deleted account

        Raises:
            ValueError: If account not found
        """
        from datetime import datetime

        account = await self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Soft delete
        account.deleted_at = datetime.utcnow().isoformat()
        account.status = AccountStatus.BLOCKED

        await self.db.flush()
        return account

    async def list_accounts(
        self,
        page: int = 1,
        page_size: int = 100,
        status: AccountStatus | None = None,
    ) -> tuple[list[Account], int]:
        """
        List accounts with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            status: Filter by status (optional)

        Returns:
            Tuple of (accounts, total_count)
        """
        # Build query
        query = select(Account).where(Account.deleted_at.is_(None))

        if status:
            query = query.where(Account.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(Account.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        accounts = result.scalars().all()

        return list(accounts), total or 0

    async def update_account_status(self, account_id: UUID, status: AccountStatus) -> Account:
        """
        Update account status (for dunning process).

        Args:
            account_id: Account UUID
            status: New status

        Returns:
            Updated account

        Raises:
            ValueError: If account not found
        """
        account = await self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        account.status = status
        await self.db.flush()
        await self.db.refresh(account)

        return account

    async def get_account_with_payment_methods(self, account_id: UUID) -> Account | None:
        """
        Get account with eager-loaded payment methods.

        Args:
            account_id: Account UUID

        Returns:
            Account with payment methods or None
        """
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Account)
            .where(Account.id == account_id, Account.deleted_at.is_(None))
            .options(selectinload(Account.payment_methods))
        )
        return result.scalar_one_or_none()
