"""Account API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db, get_current_user
from billing.auth.rbac import require_roles, Role
from billing.adapters.stripe_adapter import StripeAdapter
from billing.models.account import AccountStatus
from billing.schemas.account import Account, AccountCreate, AccountUpdate, AccountList
from billing.schemas.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
    PaymentMethodList,
    PaymentMethodUpdate,
)
from billing.schemas.credit import Credit, CreditList, CreditBalance
from billing.services.account_service import AccountService
from billing.services.payment_method_service import PaymentMethodService
from billing.services.credit_service import CreditService
from billing.cache import cache, cache_key

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("", response_model=Account, status_code=status.HTTP_201_CREATED)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
        account = await service.create_account(account_data, current_user=current_user)
        await db.commit()

        # Invalidate account list cache
        await cache.invalidate_pattern("account_list:*")

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
    # Check cache first
    cache_key_str = cache_key("account", str(account_id))
    cached = await cache.get(cache_key_str)
    if cached:
        return Account.model_validate(cached)

    service = AccountService(db)
    account = await service.get_account(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    # Cache for 5 minutes
    await cache.set(cache_key_str, account.model_dump(), ttl=300)

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

    # Check cache first
    cache_key_str = cache_key("account_list", f"page{page}_size{page_size}_status{status_filter}")
    cached = await cache.get(cache_key_str)
    if cached:
        return AccountList.model_validate(cached)

    service = AccountService(db)
    accounts, total = await service.list_accounts(page, page_size, status_filter)

    result = AccountList(
        items=accounts,
        total=total,
        page=page,
        page_size=page_size,
    )

    # Cache for 1 minute (lists change more frequently)
    await cache.set(cache_key_str, result.model_dump(), ttl=60)

    return result


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
        account = await service.update_account(account_id, update_data, current_user=current_user)
        await db.commit()

        # Invalidate cache for this account and account lists
        await cache.invalidate_pattern(f"account:{account_id}*")
        await cache.invalidate_pattern("account_list:*")

        return account
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_roles(Role.SUPER_ADMIN)
async def delete_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    """
    Delete account (soft delete).

    This will mark the account as deleted and block it from further use.
    """
    service = AccountService(db)

    try:
        await service.delete_account(account_id, current_user=current_user)
        await db.commit()

        # Invalidate cache for this account and account lists
        await cache.invalidate_pattern(f"account:{account_id}*")
        await cache.invalidate_pattern("account_list:*")
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# Payment Method endpoints for accounts


@router.post("/{account_id}/payment-methods", response_model=PaymentMethod, status_code=status.HTTP_201_CREATED)
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def create_payment_method(
    account_id: UUID,
    payment_data: PaymentMethodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def update_payment_method(
    account_id: UUID,
    payment_method_id: UUID,
    update_data: PaymentMethodUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
@require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP)
async def delete_payment_method(
    account_id: UUID,
    payment_method_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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


# Credit endpoints for accounts


@router.get("/{account_id}/credits", response_model=CreditList)
async def list_account_credits(
    account_id: UUID,
    page: int = 1,
    page_size: int = 50,
    include_applied: bool = True,
    include_expired: bool = True,
    db: AsyncSession = Depends(get_db),
) -> CreditList:
    """
    List credits for an account.

    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (default: 50)
    - **include_applied**: Include already-applied credits (default: True)
    - **include_expired**: Include expired credits (default: True)
    """
    # Verify account exists
    account_service = AccountService(db)
    account = await account_service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    credit_service = CreditService(db)
    credits, total = await credit_service.list_credits_for_account(
        account_id=account_id,
        page=page,
        page_size=page_size,
        include_applied=include_applied,
        include_expired=include_expired,
    )

    return CreditList(
        items=credits,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{account_id}/credits/balance", response_model=CreditBalance)
async def get_account_credit_balance(
    account_id: UUID,
    currency: str = "USD",
    db: AsyncSession = Depends(get_db),
) -> CreditBalance:
    """
    Get credit balance summary for an account.

    Returns total credits, available credits, expired credits, and applied credits.
    """
    # Verify account exists
    account_service = AccountService(db)
    account = await account_service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    credit_service = CreditService(db)
    balance = await credit_service.get_account_credit_balance(
        account_id=account_id,
        currency=currency,
    )

    return balance
