"""Account API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db
from billing.adapters.stripe_adapter import StripeAdapter
from billing.models.account import AccountStatus
from billing.schemas.account import Account, AccountCreate, AccountUpdate, AccountList
from billing.schemas.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
    PaymentMethodList,
    PaymentMethodUpdate,
)
from billing.services.account_service import AccountService
from billing.services.payment_method_service import PaymentMethodService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("", response_model=Account, status_code=status.HTTP_201_CREATED)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """
    Create a new account.

    - **email**: Customer email address (required, unique)
    - **name**: Customer or company name (required)
    - **currency**: ISO 4217 currency code (default: USD)
    - **timezone**: IANA timezone identifier (default: UTC)
    """
    service = AccountService(db)

    try:
        account = await service.create_account(account_data)
        await db.commit()
        return account
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{account_id}", response_model=Account)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """
    Get account by ID.

    Returns account details including status, currency, and metadata.
    """
    service = AccountService(db)
    account = await service.get_account(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    return account


@router.get("", response_model=AccountList)
async def list_accounts(
    page: int = 1,
    page_size: int = 100,
    status_filter: AccountStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> AccountList:
    """
    List accounts with pagination.

    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (default: 100, max: 1000)
    - **status**: Filter by account status (optional)
    """
    if page < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page must be >= 1")

    if page_size < 1 or page_size > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Page size must be between 1 and 1000"
        )

    service = AccountService(db)
    accounts, total = await service.list_accounts(page, page_size, status_filter)

    return AccountList(
        items=accounts,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{account_id}", response_model=Account)
async def update_account(
    account_id: UUID,
    update_data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """
    Update account.

    Only provided fields will be updated. All fields are optional.
    """
    service = AccountService(db)

    try:
        account = await service.update_account(account_id, update_data)
        await db.commit()
        return account
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete account (soft delete).

    This will mark the account as deleted and block it from further use.
    """
    service = AccountService(db)

    try:
        await service.delete_account(account_id)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# Payment Method endpoints for accounts


@router.post("/{account_id}/payment-methods", response_model=PaymentMethod, status_code=status.HTTP_201_CREATED)
async def create_payment_method(
    account_id: UUID,
    payment_data: PaymentMethodCreate,
    db: AsyncSession = Depends(get_db),
) -> PaymentMethod:
    """
    Add payment method to account.

    - **stripe_payment_method_id**: Stripe payment method ID (from client-side Stripe.js)
    - **is_default**: Set as default payment method (optional)

    This endpoint attaches the Stripe payment method to the customer and stores the reference.
    """
    # Verify account exists
    account_service = AccountService(db)
    account = await account_service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    # Create Stripe customer if needed (stored in metadata)
    stripe_customer_id = account.extra_metadata.get("stripe_customer_id")
    if not stripe_customer_id:
        stripe = StripeAdapter()
        stripe_customer_id = await stripe.create_customer(
            email=account.email,
            name=account.name,
            metadata={"account_id": str(account_id)},
        )
        account.extra_metadata["stripe_customer_id"] = stripe_customer_id
        await db.flush()

    # Create payment method
    stripe = StripeAdapter()
    pm_service = PaymentMethodService(db, stripe)

    try:
        payment_method = await pm_service.create_payment_method(
            account_id=account_id,
            stripe_customer_id=stripe_customer_id,
            payment_data=payment_data,
        )
        await db.commit()
        return payment_method
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create payment method: {str(e)}",
        ) from e


@router.get("/{account_id}/payment-methods", response_model=PaymentMethodList)
async def list_payment_methods(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PaymentMethodList:
    """
    List payment methods for account.

    Returns all payment methods ordered by default status and creation date.
    """
    # Verify account exists
    account_service = AccountService(db)
    account = await account_service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    stripe = StripeAdapter()
    pm_service = PaymentMethodService(db, stripe)
    payment_methods = await pm_service.list_payment_methods(account_id)

    return PaymentMethodList(
        items=payment_methods,
        total=len(payment_methods),
        page=1,
        page_size=len(payment_methods),
    )


@router.patch("/{account_id}/payment-methods/{payment_method_id}", response_model=PaymentMethod)
async def update_payment_method(
    account_id: UUID,
    payment_method_id: UUID,
    update_data: PaymentMethodUpdate,
    db: AsyncSession = Depends(get_db),
) -> PaymentMethod:
    """
    Update payment method (set as default).

    Currently only supports updating the is_default flag.
    """
    stripe = StripeAdapter()
    pm_service = PaymentMethodService(db, stripe)

    try:
        if update_data.is_default:
            payment_method = await pm_service.set_default_payment_method(account_id, payment_method_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot unset default payment method. Set another as default instead.",
            )

        await db.commit()
        return payment_method
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{account_id}/payment-methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    account_id: UUID,
    payment_method_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete payment method.

    Cannot delete the default payment method. Set another as default first.
    """
    stripe = StripeAdapter()
    pm_service = PaymentMethodService(db, stripe)

    try:
        await pm_service.delete_payment_method(payment_method_id)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
