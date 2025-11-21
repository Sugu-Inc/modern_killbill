"""
GraphQL schema definition using Strawberry.

Provides GraphQL API for complex nested queries with efficient data loading.
Implements US14: Flexible API Access with GraphQL

Types:
- Account
- Plan
- Subscription
- Invoice
- Payment
- Usage Record
- Credit

Features:
- N+1 query prevention via DataLoaders
- Cursor-based pagination
- Nested object queries
- Type-safe schema
"""

import strawberry
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal

# Scalars for custom types

@strawberry.scalar(
    serialize=lambda v: str(v),
    parse_value=lambda v: Decimal(v)
)
class DecimalScalar:
    """Decimal scalar for precise financial calculations."""
    pass


@strawberry.scalar(
    serialize=lambda v: v.isoformat(),
    parse_value=lambda v: datetime.fromisoformat(v)
)
class DateTimeScalar:
    """DateTime scalar with ISO 8601 format."""
    pass


@strawberry.scalar(
    serialize=lambda v: v.isoformat(),
    parse_value=lambda v: date.fromisoformat(v)
)
class DateScalar:
    """Date scalar with ISO 8601 format."""
    pass


# Enums

@strawberry.enum
class SubscriptionStatusEnum(str):
    """Subscription status."""
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@strawberry.enum
class InvoiceStatusEnum(str):
    """Invoice status."""
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


@strawberry.enum
class PaymentStatusEnum(str):
    """Payment status."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# Types

@strawberry.type
class PaymentMethod:
    """Payment method (card, ACH, etc.)."""
    id: strawberry.ID
    type: str
    card_last4: Optional[str]
    card_brand: Optional[str]
    is_default: bool
    created_at: DateTimeScalar


@strawberry.type
class Account:
    """Customer account."""
    id: strawberry.ID
    email: str
    name: str
    currency: str
    timezone: str
    tax_exempt: bool
    created_at: DateTimeScalar
    updated_at: DateTimeScalar

    # Relationships (resolved via DataLoaders)
    subscriptions: List["Subscription"] = strawberry.field()
    invoices: List["Invoice"] = strawberry.field()
    payment_methods: List[PaymentMethod] = strawberry.field()
    credits: List["Credit"] = strawberry.field()


@strawberry.type
class Plan:
    """Pricing plan."""
    id: strawberry.ID
    name: str
    interval: str  # month, year
    amount: int  # cents
    currency: str
    trial_days: int
    usage_type: str  # licensed, metered
    active: bool
    created_at: DateTimeScalar

    # Relationships
    subscriptions: List["Subscription"] = strawberry.field()


@strawberry.type
class Subscription:
    """Customer subscription to a plan."""
    id: strawberry.ID
    status: SubscriptionStatusEnum
    quantity: int
    current_period_start: DateTimeScalar
    current_period_end: DateTimeScalar
    cancel_at_period_end: bool
    created_at: DateTimeScalar
    updated_at: DateTimeScalar

    # Relationships (resolved via DataLoaders)
    account: Account = strawberry.field()
    plan: Plan = strawberry.field()
    invoices: List["Invoice"] = strawberry.field()
    usage_records: List["UsageRecord"] = strawberry.field()


@strawberry.type
class InvoiceLineItem:
    """Invoice line item."""
    description: str
    quantity: int
    amount: int  # cents
    total: int  # cents


@strawberry.type
class Invoice:
    """Customer invoice."""
    id: strawberry.ID
    number: str
    status: InvoiceStatusEnum
    amount_due: int  # cents
    amount_paid: int  # cents
    tax: int  # cents
    currency: str
    due_date: DateScalar
    paid_at: Optional[DateTimeScalar]
    line_items: List[InvoiceLineItem]
    created_at: DateTimeScalar

    # Relationships
    account: Account = strawberry.field()
    subscription: Optional[Subscription] = strawberry.field()
    payments: List["Payment"] = strawberry.field()


@strawberry.type
class Payment:
    """Payment transaction."""
    id: strawberry.ID
    amount: int  # cents
    currency: str
    status: PaymentStatusEnum
    failure_message: Optional[str]
    created_at: DateTimeScalar

    # Relationships
    invoice: Invoice = strawberry.field()


@strawberry.type
class UsageRecord:
    """Usage event for metered billing."""
    id: strawberry.ID
    metric: str
    quantity: int
    timestamp: DateTimeScalar
    created_at: DateTimeScalar

    # Relationships
    subscription: Subscription = strawberry.field()


@strawberry.type
class Credit:
    """Account credit."""
    id: strawberry.ID
    amount: int  # cents
    currency: str
    reason: str
    created_at: DateTimeScalar

    # Relationships
    account: Account = strawberry.field()
    applied_to_invoice: Optional[Invoice] = strawberry.field()


# Pagination

@strawberry.type
class PageInfo:
    """Pagination information."""
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]


@strawberry.type
class AccountEdge:
    """Account edge for cursor pagination."""
    cursor: str
    node: Account


@strawberry.type
class AccountConnection:
    """Paginated account results."""
    edges: List[AccountEdge]
    page_info: PageInfo
    total_count: int


@strawberry.type
class SubscriptionEdge:
    """Subscription edge for cursor pagination."""
    cursor: str
    node: Subscription


@strawberry.type
class SubscriptionConnection:
    """Paginated subscription results."""
    edges: List[SubscriptionEdge]
    page_info: PageInfo
    total_count: int


@strawberry.type
class InvoiceEdge:
    """Invoice edge for cursor pagination."""
    cursor: str
    node: Invoice


@strawberry.type
class InvoiceConnection:
    """Paginated invoice results."""
    edges: List[InvoiceEdge]
    page_info: PageInfo
    total_count: int


# Root Query

@strawberry.type
class Query:
    """Root GraphQL query."""

    # Single object queries
    account: Optional[Account] = strawberry.field()
    plan: Optional[Plan] = strawberry.field()
    subscription: Optional[Subscription] = strawberry.field()
    invoice: Optional[Invoice] = strawberry.field()

    # Paginated list queries
    accounts: AccountConnection = strawberry.field()
    subscriptions: SubscriptionConnection = strawberry.field()
    invoices: InvoiceConnection = strawberry.field()
    plans: List[Plan] = strawberry.field()


# Root Mutation (placeholder for future)

@strawberry.type
class Mutation:
    """Root GraphQL mutation."""
    # Mutations would be added here (create, update, delete operations)
    pass


# Schema

schema = strawberry.Schema(query=Query, mutation=Mutation)
