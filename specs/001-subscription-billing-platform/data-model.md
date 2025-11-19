# Data Model: Modern Subscription Billing Platform

**Date**: 2025-11-19
**Status**: Complete
**Plan**: [plan.md](./plan.md)

## Overview

This document defines the complete database schema for the subscription billing platform. All entities are implemented as PostgreSQL tables using SQLAlchemy ORM.

---

## Entity-Relationship Diagram

```
┌─────────────┐
│  Account    │────┐
└─────────────┘    │
       │           │
       │ 1:N       │ 1:N
       ▼           ▼
┌─────────────┐  ┌──────────────────┐
│PaymentMethod│  │  Subscription    │
└─────────────┘  └──────────────────┘
                        │
                        │ 1:N
                        ▼
                 ┌──────────────────┐
                 │    Invoice       │
                 └──────────────────┘
                        │
                        │ 1:N
                        ▼
                 ┌──────────────────┐
                 │    Payment       │
                 └──────────────────┘

┌─────────────┐
│    Plan     │────────────────────┐
└─────────────┘                    │
                                   │ N:1
                                   ▼
                            ┌──────────────────┐
                            │  Subscription    │
                            └──────────────────┘
                                   │
                                   │ 1:N
                                   ▼
                            ┌──────────────────┐
                            │  UsageRecord     │
                            └──────────────────┘

┌─────────────┐
│   Credit    │───────────────────┐
└─────────────┘                   │ N:1
                                  ▼
                           ┌──────────────────┐
                           │    Account       │
                           └──────────────────┘

┌──────────────────┐
│ SubscriptionHistory │
└──────────────────┘
       │
       │ N:1
       ▼
┌──────────────────┐
│  Subscription    │
└──────────────────┘

┌─────────────┐
│  AuditLog   │  (references all entities)
└─────────────┘
```

---

## Core Entities

### 1. Account

**Purpose**: Customer with billing information

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `email` (VARCHAR(255), UNIQUE): Customer email
- `name` (VARCHAR(255)): Customer name
- `currency` (CHAR(3)): ISO currency code (USD, EUR, GBP, etc.)
- `timezone` (VARCHAR(50)): IANA timezone (e.g., "America/New_York")
- `default_payment_method_id` (UUID, FK → PaymentMethod): Default payment method
- `tax_exempt` (BOOLEAN): Tax exemption flag
- `metadata` (JSONB): Custom key-value data
- `created_at` (TIMESTAMP): Creation timestamp
- `updated_at` (TIMESTAMP): Last update timestamp

**Indexes**:
- `idx_accounts_email` on `email`
- `idx_accounts_created` on `created_at`

**SQLAlchemy Model**:
```python
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    timezone = Column(String(50))
    default_payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id"))
    tax_exempt = Column(Boolean, default=False)
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscriptions = relationship("Subscription", back_populates="account")
    payment_methods = relationship("PaymentMethod", back_populates="account")
    invoices = relationship("Invoice", back_populates="account")
    credits = relationship("Credit", back_populates="account")
```

---

### 2. Plan

**Purpose**: Pricing definition template

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `name` (VARCHAR(255)): Plan name (e.g., "Pro Plan")
- `interval` (VARCHAR(20)): Billing interval (month, year)
- `amount` (INTEGER): Price in cents
- `currency` (CHAR(3)): Currency code
- `trial_days` (INTEGER): Trial period in days (0 = no trial)
- `usage_type` (VARCHAR(20)): licensed (fixed), metered (usage-based), hybrid
- `tiers` (JSONB): Usage tier pricing (for metered plans)
- `metadata` (JSONB): Custom data
- `active` (BOOLEAN): Plan availability flag
- `version` (INTEGER): Plan version (for grandfather pricing)
- `created_at` (TIMESTAMP): Creation timestamp

**Indexes**:
- `idx_plans_active` on `active`
- `idx_plans_version` on `name, version`

**SQLAlchemy Model**:
```python
class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    interval = Column(String(20), nullable=False)  # 'month', 'year'
    amount = Column(Integer, nullable=False)  # cents
    currency = Column(String(3), nullable=False)
    trial_days = Column(Integer, default=0)
    usage_type = Column(String(20), default="licensed")  # 'licensed', 'metered', 'hybrid'
    tiers = Column(JSONB, default=list)  # [{"up_to": 1000, "unit_price": 0}, {"up_to": 10000, "unit_price": 100}, ...]
    metadata = Column(JSONB, default=dict)
    active = Column(Boolean, default=True, index=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")
```

---

### 3. Subscription

**Purpose**: Customer enrollment in a plan

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `account_id` (UUID, FK → Account): Owner account
- `plan_id` (UUID, FK → Plan): Subscribed plan
- `status` (VARCHAR(20)): TRIAL, ACTIVE, PAUSED, CANCELLED, EXPIRED
- `quantity` (INTEGER): Number of seats/licenses (default: 1)
- `current_period_start` (TIMESTAMP): Current billing period start
- `current_period_end` (TIMESTAMP): Current billing period end
- `trial_end` (TIMESTAMP): Trial end date
- `cancelled_at` (TIMESTAMP): Cancellation timestamp
- `cancel_at_period_end` (BOOLEAN): Cancel at end of current period flag
- `pause_resumes_at` (TIMESTAMP): Auto-resume date for paused subscription
- `external_key` (VARCHAR(255)): Customer reference ID
- `metadata` (JSONB): Custom data
- `created_at` (TIMESTAMP): Creation timestamp
- `updated_at` (TIMESTAMP): Last update timestamp

**Indexes**:
- `idx_subscriptions_account` on `account_id`
- `idx_subscriptions_status` on `status`
- `idx_subscriptions_next_billing` on `current_period_end` WHERE `status = 'ACTIVE'`

**State Transitions**:
```
TRIAL → ACTIVE (trial ends, payment succeeds)
TRIAL → CANCELLED (trial cancelled)
ACTIVE → PAUSED (customer pauses)
ACTIVE → CANCELLED (customer cancels)
PAUSED → ACTIVE (auto-resume or manual resume)
PAUSED → CANCELLED (pause >90 days or manual cancel)
ACTIVE/PAUSED → EXPIRED (failed to renew after retries)
```

**SQLAlchemy Model**:
```python
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    status = Column(String(20), nullable=False, index=True)  # TRIAL, ACTIVE, PAUSED, CANCELLED, EXPIRED
    quantity = Column(Integer, nullable=False, default=1)
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False, index=True)
    trial_end = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    pause_resumes_at = Column(DateTime)
    external_key = Column(String(255))
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    invoices = relationship("Invoice", back_populates="subscription")
    usage_records = relationship("UsageRecord", back_populates="subscription")
    history = relationship("SubscriptionHistory", back_populates="subscription")
```

---

### 4. Invoice

**Purpose**: Immutable billing statement

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `account_id` (UUID, FK → Account): Billed account
- `subscription_id` (UUID, FK → Subscription): Related subscription (NULL for one-off invoices)
- `number` (VARCHAR(50), UNIQUE): Invoice number (e.g., "INV-2025-001")
- `status` (VARCHAR(20)): DRAFT, OPEN, PAID, VOID
- `amount_due` (INTEGER): Total amount due in cents
- `amount_paid` (INTEGER): Amount paid in cents
- `tax` (INTEGER): Tax amount in cents
- `currency` (CHAR(3)): Currency code
- `due_date` (TIMESTAMP): Payment due date
- `paid_at` (TIMESTAMP): Payment completion timestamp
- `voided_at` (TIMESTAMP): Void timestamp
- `void_reason` (TEXT): Reason for voiding
- `line_items` (JSONB): Array of `{description, quantity, unit_amount, amount}`
- `metadata` (JSONB): Custom data
- `created_at` (TIMESTAMP): Creation timestamp

**Constraints**:
- Immutable: Once `status != 'DRAFT'`, no updates allowed (enforced in application layer)
- `amount_due = sum(line_items.amount) + tax`

**Indexes**:
- `idx_invoices_account` on `account_id`
- `idx_invoices_subscription` on `subscription_id`
- `idx_invoices_status` on `status`
- `idx_invoices_due_date` on `due_date` WHERE `status = 'OPEN'`
- `idx_invoices_number` UNIQUE on `number`

**State Transitions**:
```
DRAFT → OPEN (finalize invoice)
OPEN → PAID (payment succeeds)
OPEN → VOID (manual void)
DRAFT → VOID (cancel before sending)
```

**SQLAlchemy Model**:
```python
class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), index=True)
    number = Column(String(50), nullable=False, unique=True)
    status = Column(String(20), nullable=False, index=True)  # DRAFT, OPEN, PAID, VOID
    amount_due = Column(Integer, nullable=False)  # cents
    amount_paid = Column(Integer, nullable=False, default=0)
    tax = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False)
    due_date = Column(DateTime, nullable=False)
    paid_at = Column(DateTime)
    voided_at = Column(DateTime)
    void_reason = Column(Text)
    line_items = Column(JSONB, nullable=False, default=list)
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="invoices")
    subscription = relationship("Subscription", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")
```

---

### 5. Payment

**Purpose**: Payment transaction record

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `invoice_id` (UUID, FK → Invoice): Related invoice
- `amount` (INTEGER): Payment amount in cents
- `currency` (CHAR(3)): Currency code
- `status` (VARCHAR(20)): PENDING, SUCCEEDED, FAILED
- `payment_method_id` (UUID, FK → PaymentMethod): Payment method used
- `gateway_transaction_id` (VARCHAR(255)): Stripe charge/payment intent ID
- `failure_message` (TEXT): Error message if failed
- `idempotency_key` (VARCHAR(255), UNIQUE): Prevents duplicate charges
- `created_at` (TIMESTAMP): Creation timestamp

**Indexes**:
- `idx_payments_invoice` on `invoice_id`
- `idx_payments_status` on `status`
- `idx_payments_idempotency_key` UNIQUE on `idempotency_key`

**SQLAlchemy Model**:
```python
class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String(20), nullable=False, index=True)  # PENDING, SUCCEEDED, FAILED
    payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id"))
    gateway_transaction_id = Column(String(255))
    failure_message = Column(Text)
    idempotency_key = Column(String(255), unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    payment_method = relationship("PaymentMethod")
```

---

### 6. PaymentMethod

**Purpose**: Stored payment instrument

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `account_id` (UUID, FK → Account): Owner account
- `gateway_payment_method_id` (VARCHAR(255)): Stripe payment method ID
- `type` (VARCHAR(20)): card, ach_debit
- `card_last4` (VARCHAR(4)): Last 4 digits of card
- `card_brand` (VARCHAR(20)): visa, mastercard, amex
- `card_exp_month` (INTEGER): Expiration month
- `card_exp_year` (INTEGER): Expiration year
- `is_default` (BOOLEAN): Default payment method flag
- `created_at` (TIMESTAMP): Creation timestamp

**Indexes**:
- `idx_payment_methods_account` on `account_id`

**SQLAlchemy Model**:
```python
class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    gateway_payment_method_id = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)  # 'card', 'ach_debit'
    card_last4 = Column(String(4))
    card_brand = Column(String(20))
    card_exp_month = Column(Integer)
    card_exp_year = Column(Integer)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="payment_methods")
```

---

## Supporting Entities

### 7. UsageRecord

**Purpose**: Metered consumption tracking

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `subscription_id` (UUID, FK → Subscription): Related subscription
- `metric` (VARCHAR(50)): Metric name (e.g., "api_calls", "storage_gb")
- `quantity` (DECIMAL): Usage quantity
- `timestamp` (TIMESTAMP): Usage timestamp
- `idempotency_key` (VARCHAR(255), UNIQUE): Deduplication key
- `metadata` (JSONB): Custom data
- `created_at` (TIMESTAMP): Record creation timestamp

**Indexes**:
- `idx_usage_records_subscription` on `subscription_id`
- `idx_usage_records_timestamp` on `timestamp`
- `idx_usage_records_idempotency` UNIQUE on `idempotency_key`

**SQLAlchemy Model**:
```python
from sqlalchemy import Numeric

class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False, index=True)
    metric = Column(String(50), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    subscription = relationship("Subscription", back_populates="usage_records")
```

---

### 8. Credit

**Purpose**: Account credit balance

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `account_id` (UUID, FK → Account): Related account
- `amount` (INTEGER): Credit amount in cents
- `currency` (CHAR(3)): Currency code
- `reason` (TEXT): Credit reason/description
- `applied_to_invoice_id` (UUID, FK → Invoice): Invoice where credit was applied (NULL if unused)
- `created_at` (TIMESTAMP): Creation timestamp

**Indexes**:
- `idx_credits_account` on `account_id`
- `idx_credits_unapplied` on `account_id` WHERE `applied_to_invoice_id IS NULL`

**SQLAlchemy Model**:
```python
class Credit(Base):
    __tablename__ = "credits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    reason = Column(Text)
    applied_to_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="credits")
```

---

### 9. SubscriptionHistory

**Purpose**: Subscription change audit trail

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `subscription_id` (UUID, FK → Subscription): Related subscription
- `event_type` (VARCHAR(50)): created, plan_changed, quantity_changed, status_changed, cancelled
- `previous_state` (JSONB): Snapshot before change
- `new_state` (JSONB): Snapshot after change
- `effective_date` (TIMESTAMP): Change effective date
- `created_at` (TIMESTAMP): Record creation timestamp

**Indexes**:
- `idx_subscription_history_subscription` on `subscription_id, created_at`

**SQLAlchemy Model**:
```python
class SubscriptionHistory(Base):
    __tablename__ = "subscription_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    previous_state = Column(JSONB)
    new_state = Column(JSONB, nullable=False)
    effective_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    subscription = relationship("Subscription", back_populates="history")

    __table_args__ = (
        Index('idx_subscription_history_subscription', 'subscription_id', 'created_at'),
    )
```

---

### 10. AuditLog

**Purpose**: Global mutation audit trail

**Attributes**:
- `id` (UUID, PK): Unique identifier
- `entity_type` (VARCHAR(50)): Table name (accounts, subscriptions, invoices, etc.)
- `entity_id` (UUID): Entity primary key
- `action` (VARCHAR(50)): created, updated, deleted
- `user_id` (UUID): User who performed action (NULL for system actions)
- `changes` (JSONB): Changed fields with before/after values
- `created_at` (TIMESTAMP): Action timestamp

**Indexes**:
- `idx_audit_log_entity` on `entity_type, entity_id, created_at`
- `idx_audit_log_created` on `created_at` (for retention cleanup)

**SQLAlchemy Model**:
```python
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)
    user_id = Column(UUID(as_uuid=True))
    changes = Column(JSONB, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_audit_log_entity', 'entity_type', 'entity_id', 'created_at'),
    )
```

---

## Database Constraints

### Foreign Key Constraints

- All foreign keys have `ON DELETE RESTRICT` to prevent accidental data loss
- Exception: `SubscriptionHistory`, `AuditLog` have `ON DELETE CASCADE` (delete history with parent)

### Check Constraints

```sql
-- Subscription status
ALTER TABLE subscriptions ADD CONSTRAINT check_subscription_status
    CHECK (status IN ('TRIAL', 'ACTIVE', 'PAUSED', 'CANCELLED', 'EXPIRED'));

-- Invoice status
ALTER TABLE invoices ADD CONSTRAINT check_invoice_status
    CHECK (status IN ('DRAFT', 'OPEN', 'PAID', 'VOID'));

-- Payment status
ALTER TABLE payments ADD CONSTRAINT check_payment_status
    CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED'));

-- Positive amounts
ALTER TABLE invoices ADD CONSTRAINT check_invoice_amount_positive
    CHECK (amount_due >= 0 AND amount_paid >= 0 AND tax >= 0);

ALTER TABLE payments ADD CONSTRAINT check_payment_amount_positive
    CHECK (amount >= 0);

ALTER TABLE credits ADD CONSTRAINT check_credit_amount_positive
    CHECK (amount > 0);

-- Subscription quantity
ALTER TABLE subscriptions ADD CONSTRAINT check_subscription_quantity_positive
    CHECK (quantity > 0);
```

---

## Data Retention & Archival

Per FR-142 to FR-144 from specification:

| Table | Retention Period | Archival Strategy |
|-------|------------------|-------------------|
| `invoices`, `payments` | 7 years | Archive to S3 after 2 years, keep in DB for 7 years |
| `audit_log` | 3 years | Archive to S3 after 1 year, keep in DB for 3 years |
| `accounts` (soft-deleted) | 30 days | Hard delete after 30 days |
| `subscriptions` | Indefinite (tied to invoice retention) | Archive with invoices |
| `usage_records` | 2 years | Archive to S3 after 1 year |

**Implementation**:
- Soft delete: Add `deleted_at TIMESTAMP` column to `accounts`, `subscriptions`
- Archival job: Monthly background job moves old records to S3 (Parquet format)
- Hard delete job: Daily job removes `accounts` where `deleted_at < NOW() - 30 days`

---

## Migration Strategy

**Alembic Migrations**:

1. **Initial Schema**: Create all tables, indexes, constraints
2. **Seed Data**: Default plans, admin users
3. **Foreign Key Constraints**: Add FK constraints after tables exist
4. **Indexes**: Create performance indexes last

**Sample Migration**:
```python
# alembic/versions/001_initial_schema.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('timezone', sa.String(50)),
        sa.Column('default_payment_method_id', postgresql.UUID(as_uuid=True)),
        sa.Column('tax_exempt', sa.Boolean, server_default='false'),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_accounts_email', 'accounts', ['email'])
    # ... continue for other tables

def downgrade():
    op.drop_table('accounts')
    # ... drop other tables
```

---

## Summary

**Total Tables**: 10 core entities + supporting tables
**Total Indexes**: 25+ for query performance
**Constraints**: FK, CHECK, UNIQUE enforced at database level
**Data Integrity**: Immutable invoices, audit logging, idempotency
**Scalability**: Partitioning ready for `audit_log`, `usage_records` (if needed)

**Next**: Generate API contracts in `contracts/` directory
