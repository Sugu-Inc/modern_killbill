"""
GraphQL resolvers with DataLoader support.

Implements efficient data loading with N+1 prevention using Strawberry DataLoaders.
Covers T132, T133, T134: Resolvers + DataLoaders + Pagination
"""

from typing import List, Optional
import strawberry
from strawberry.dataloader import DataLoader
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import json

from billing.models.account import Account as AccountModel
from billing.models.plan import Plan as PlanModel
from billing.models.subscription import Subscription as SubscriptionModel
from billing.models.invoice import Invoice as InvoiceModel
from billing.models.payment import Payment as PaymentModel
from billing.models.usage_record import UsageRecord as UsageRecordModel
from billing.models.credit import Credit as CreditModel
from billing.models.payment_method import PaymentMethod as PaymentMethodModel

from billing.graphql.schema import (
    Account, Plan, Subscription, Invoice, Payment, UsageRecord, Credit,
    PaymentMethod, AccountConnection, SubscriptionConnection, InvoiceConnection,
    AccountEdge, SubscriptionEdge, InvoiceEdge, PageInfo
)


# DataLoaders for N+1 prevention

async def load_accounts(keys: List[str], db: AsyncSession) -> List[Optional[AccountModel]]:
    """Batch load accounts by ID."""
    stmt = select(AccountModel).where(AccountModel.id.in_(keys))
    result = await db.execute(stmt)
    accounts = {str(acc.id): acc for acc in result.scalars()}
    return [accounts.get(key) for key in keys]


async def load_plans(keys: List[str], db: AsyncSession) -> List[Optional[PlanModel]]:
    """Batch load plans by ID."""
    stmt = select(PlanModel).where(PlanModel.id.in_(keys))
    result = await db.execute(stmt)
    plans = {str(plan.id): plan for plan in result.scalars()}
    return [plans.get(key) for key in keys]


async def load_subscriptions(keys: List[str], db: AsyncSession) -> List[Optional[SubscriptionModel]]:
    """Batch load subscriptions by ID."""
    stmt = select(SubscriptionModel).where(SubscriptionModel.id.in_(keys))
    result = await db.execute(stmt)
    subscriptions = {str(sub.id): sub for sub in result.scalars()}
    return [subscriptions.get(key) for key in keys]


async def load_invoices(keys: List[str], db: AsyncSession) -> List[Optional[InvoiceModel]]:
    """Batch load invoices by ID."""
    stmt = select(InvoiceModel).where(InvoiceModel.id.in_(keys))
    result = await db.execute(stmt)
    invoices = {str(inv.id): inv for inv in result.scalars()}
    return [invoices.get(key) for key in keys]


# Cursor-based pagination helpers

def encode_cursor(value: str) -> str:
    """Encode cursor for pagination."""
    return base64.b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    """Decode cursor for pagination."""
    try:
        return base64.b64decode(cursor.encode()).decode()
    except:
        return ""


async def paginate_query(
    query,
    db: AsyncSession,
    first: Optional[int] = None,
    after: Optional[str] = None,
    model_class=None
):
    """
    Apply cursor-based pagination to a query.

    Args:
        query: SQLAlchemy query
        db: Database session
        first: Number of items to return
        after: Cursor to start after
        model_class: Model class for cursor generation

    Returns:
        Tuple of (items, has_next_page, start_cursor, end_cursor)
    """
    limit = min(first or 50, 100)  # Max 100 items per page

    # Apply cursor filter
    if after:
        cursor_id = decode_cursor(after)
        if cursor_id:
            query = query.where(model_class.id > cursor_id)

    # Fetch limit + 1 to check if there are more results
    query = query.limit(limit + 1)
    result = await db.execute(query)
    items = result.scalars().all()

    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    start_cursor = encode_cursor(str(items[0].id)) if items else None
    end_cursor = encode_cursor(str(items[-1].id)) if items else None

    return items, has_next, start_cursor, end_cursor


# Resolver functions

@strawberry.field
async def resolve_account(id: strawberry.ID, info) -> Optional[Account]:
    """Resolve single account by ID."""
    db: AsyncSession = info.context["db"]

    stmt = select(AccountModel).where(AccountModel.id == id)
    result = await db.execute(stmt)
    account_model = result.scalars().first()

    if not account_model:
        return None

    return Account(
        id=strawberry.ID(str(account_model.id)),
        email=account_model.email,
        name=account_model.name,
        currency=account_model.currency,
        timezone=account_model.timezone,
        tax_exempt=account_model.tax_exempt,
        created_at=account_model.created_at,
        updated_at=account_model.updated_at
    )


@strawberry.field
async def resolve_accounts(
    first: Optional[int] = 50,
    after: Optional[str] = None,
    info=None
) -> AccountConnection:
    """Resolve paginated list of accounts."""
    db: AsyncSession = info.context["db"]

    # Base query
    query = select(AccountModel).order_by(AccountModel.id)

    # Apply pagination
    items, has_next, start_cursor, end_cursor = await paginate_query(
        query, db, first, after, AccountModel
    )

    # Get total count
    count_stmt = select(func.count()).select_from(AccountModel)
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar()

    # Convert to GraphQL types
    edges = [
        AccountEdge(
            cursor=encode_cursor(str(item.id)),
            node=Account(
                id=strawberry.ID(str(item.id)),
                email=item.email,
                name=item.name,
                currency=item.currency,
                timezone=item.timezone,
                tax_exempt=item.tax_exempt,
                created_at=item.created_at,
                updated_at=item.updated_at
            )
        )
        for item in items
    ]

    page_info = PageInfo(
        has_next_page=has_next,
        has_previous_page=bool(after),
        start_cursor=start_cursor,
        end_cursor=end_cursor
    )

    return AccountConnection(
        edges=edges,
        page_info=page_info,
        total_count=total_count
    )


@strawberry.field
async def resolve_subscription(id: strawberry.ID, info) -> Optional[Subscription]:
    """Resolve single subscription by ID."""
    db: AsyncSession = info.context["db"]

    stmt = select(SubscriptionModel).where(SubscriptionModel.id == id)
    result = await db.execute(stmt)
    sub_model = result.scalars().first()

    if not sub_model:
        return None

    return Subscription(
        id=strawberry.ID(str(sub_model.id)),
        status=sub_model.status,
        quantity=sub_model.quantity,
        current_period_start=sub_model.current_period_start,
        current_period_end=sub_model.current_period_end,
        cancel_at_period_end=sub_model.cancel_at_period_end,
        created_at=sub_model.created_at,
        updated_at=sub_model.updated_at
    )


@strawberry.field
async def resolve_subscriptions(
    first: Optional[int] = 50,
    after: Optional[str] = None,
    account_id: Optional[strawberry.ID] = None,
    info=None
) -> SubscriptionConnection:
    """Resolve paginated list of subscriptions."""
    db: AsyncSession = info.context["db"]

    # Base query
    query = select(SubscriptionModel).order_by(SubscriptionModel.id)

    # Filter by account if provided
    if account_id:
        query = query.where(SubscriptionModel.account_id == account_id)

    # Apply pagination
    items, has_next, start_cursor, end_cursor = await paginate_query(
        query, db, first, after, SubscriptionModel
    )

    # Get total count
    count_query = select(func.count()).select_from(SubscriptionModel)
    if account_id:
        count_query = count_query.where(SubscriptionModel.account_id == account_id)
    count_result = await db.execute(count_query)
    total_count = count_result.scalar()

    # Convert to GraphQL types
    edges = [
        SubscriptionEdge(
            cursor=encode_cursor(str(item.id)),
            node=Subscription(
                id=strawberry.ID(str(item.id)),
                status=item.status,
                quantity=item.quantity,
                current_period_start=item.current_period_start,
                current_period_end=item.current_period_end,
                cancel_at_period_end=item.cancel_at_period_end,
                created_at=item.created_at,
                updated_at=item.updated_at
            )
        )
        for item in items
    ]

    page_info = PageInfo(
        has_next_page=has_next,
        has_previous_page=bool(after),
        start_cursor=start_cursor,
        end_cursor=end_cursor
    )

    return SubscriptionConnection(
        edges=edges,
        page_info=page_info,
        total_count=total_count
    )


# Attach resolvers to Query type
# These will be integrated when mounting the GraphQL app
