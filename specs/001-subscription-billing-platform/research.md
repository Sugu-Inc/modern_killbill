# Research: Modern Subscription Billing Platform

**Date**: 2025-11-19
**Status**: Complete
**Plan**: [plan.md](./plan.md)

## Overview

This document captures technology decisions and architectural patterns researched for the Modern Subscription Billing Platform. Each decision includes rationale, alternatives considered, and code examples.

---

## 1. Payment Gateway Integration Patterns

### Decision

**Use Adapter Pattern with Stripe SDK**

Create a thin adapter layer around Stripe SDK to enable:
- Testability (swap real Stripe with test adapter)
- Idempotency enforcement
- Webhook signature verification
- Centralized error handling

### Rationale

- **Testability**: Direct SDK usage makes tests brittle and slow. Adapter allows fast unit tests with mock adapter.
- **Flexibility**: If we need to support multiple gateways later, adapter pattern provides abstraction point.
- **Idempotency**: Centralize idempotency key generation and retry logic in one place.
- **Type Safety**: Wrap Stripe's dict-based responses in Pydantic models for type checking.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Direct Stripe SDK calls | Hard to test, couples business logic to SDK, no idempotency layer |
| Full payment abstraction (support multiple gateways) | YAGNI - only need Stripe now, adapter provides future-proofing without complexity |
| Mock Stripe responses in tests | Brittle tests, miss SDK changes, false confidence |

### Implementation Pattern

```python
# src/billing/integrations/stripe.py
from typing import Protocol
import stripe
from pydantic import BaseModel

class PaymentMethod(BaseModel):
    id: str
    type: str
    card_last4: str | None
    card_brand: str | None

class PaymentGateway(Protocol):
    """Protocol for payment gateway adapters"""
    async def create_payment_method(
        self,
        customer_token: str,
        idempotency_key: str
    ) -> PaymentMethod:
        ...

    async def charge(
        self,
        amount: int,
        currency: str,
        payment_method_id: str,
        idempotency_key: str
    ) -> str:  # Returns charge ID
        ...

class StripeAdapter:
    """Real Stripe integration"""

    def __init__(self, api_key: str):
        stripe.api_key = api_key

    async def create_payment_method(
        self,
        customer_token: str,
        idempotency_key: str
    ) -> PaymentMethod:
        try:
            pm = await stripe.PaymentMethod.create_async(
                type="card",
                card={"token": customer_token},
                idempotency_key=idempotency_key
            )
            return PaymentMethod(
                id=pm.id,
                type=pm.type,
                card_last4=pm.card.last4 if pm.card else None,
                card_brand=pm.card.brand if pm.card else None
            )
        except stripe.error.StripeError as e:
            # Centralized error handling
            raise PaymentGatewayError(f"Failed to create payment method: {e.user_message}")

    async def charge(
        self,
        amount: int,
        currency: str,
        payment_method_id: str,
        idempotency_key: str
    ) -> str:
        charge = await stripe.PaymentIntent.create_async(
            amount=amount,
            currency=currency,
            payment_method=payment_method_id,
            confirm=True,
            idempotency_key=idempotency_key
        )
        return charge.id

class TestPaymentAdapter:
    """Test adapter for fast unit tests"""

    async def create_payment_method(self, customer_token: str, idempotency_key: str) -> PaymentMethod:
        return PaymentMethod(
            id=f"pm_test_{idempotency_key[:8]}",
            type="card",
            card_last4="4242",
            card_brand="visa"
        )

    async def charge(self, amount: int, currency: str, payment_method_id: str, idempotency_key: str) -> str:
        return f"ch_test_{idempotency_key[:8]}"
```

**Webhook Verification**:
```python
from fastapi import Header, HTTPException

async def verify_stripe_webhook(
    raw_body: bytes,
    signature: str = Header(alias="stripe-signature")
):
    try:
        event = stripe.Webhook.construct_event(
            raw_body,
            signature,
            settings.STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
```

---

## 2. Database Schema Design for Billing

### Decision

**Temporal data with immutable invoices, event sourcing for state changes**

- **Immutable Invoices**: Once finalized, invoices never change (void creates new adjustment invoice)
- **Subscription History**: Track quantity/plan changes in separate history table
- **Audit Log**: Store all state transitions as events (Event Sourcing pattern)
- **Proration Logic**: Calculate on-the-fly from current period dates, not stored

### Rationale

- **Financial Integrity**: Immutable invoices ensure audit trail and prevent tampering
- **Temporal Queries**: Can answer "What was the subscription state on date X?"
- **Debugging**: Event log makes it easy to understand how system reached current state
- **Compliance**: Audit trail required for financial compliance (7-year retention)

### Schema Patterns

**Core Entities**:
```sql
-- Account: Customer with billing info
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    timezone VARCHAR(50),
    default_payment_method_id UUID,
    tax_exempt BOOLEAN DEFAULT FALSE,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accounts_email ON accounts(email);

-- Subscription: Customer enrollment in plan
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id),
    plan_id UUID NOT NULL REFERENCES plans(id),
    status VARCHAR(20) NOT NULL CHECK (status IN ('TRIAL', 'ACTIVE', 'PAUSED', 'CANCELLED', 'EXPIRED')),
    quantity INTEGER NOT NULL DEFAULT 1,
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    trial_end TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    pause_resumes_at TIMESTAMP,
    external_key VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscriptions_account ON subscriptions(account_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_next_billing ON subscriptions(current_period_end) WHERE status = 'ACTIVE';

-- Subscription History: Track changes over time
CREATE TABLE subscription_history (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES subscriptions(id),
    event_type VARCHAR(50) NOT NULL,  -- 'created', 'plan_changed', 'quantity_changed', 'cancelled'
    previous_state JSONB,
    new_state JSONB,
    effective_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscription_history_subscription ON subscription_history(subscription_id, created_at);

-- Invoice: Immutable billing statement
CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id),
    subscription_id UUID REFERENCES subscriptions(id),
    number VARCHAR(50) NOT NULL UNIQUE,  -- INV-2025-001
    status VARCHAR(20) NOT NULL CHECK (status IN ('DRAFT', 'OPEN', 'PAID', 'VOID')),
    amount_due INTEGER NOT NULL,  -- cents
    amount_paid INTEGER NOT NULL DEFAULT 0,
    tax INTEGER NOT NULL DEFAULT 0,
    currency CHAR(3) NOT NULL,
    due_date TIMESTAMP NOT NULL,
    paid_at TIMESTAMP,
    voided_at TIMESTAMP,
    void_reason TEXT,
    line_items JSONB NOT NULL,  -- Array of {description, quantity, amount}
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_invoices_account ON invoices(account_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_date ON invoices(due_date) WHERE status = 'OPEN';
CREATE UNIQUE INDEX idx_invoices_number ON invoices(number);

-- Payment: Money received
CREATE TABLE payments (
    id UUID PRIMARY KEY,
    invoice_id UUID NOT NULL REFERENCES invoices(id),
    amount INTEGER NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED')),
    payment_method_id UUID REFERENCES payment_methods(id),
    gateway_transaction_id VARCHAR(255),
    failure_message TEXT,
    idempotency_key VARCHAR(255) UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payments_invoice ON payments(invoice_id);
CREATE INDEX idx_payments_status ON payments(status);

-- Audit Log: All mutations
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    user_id UUID,  -- NULL for system actions
    changes JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id, created_at);
CREATE INDEX idx_audit_log_created ON audit_log(created_at);  -- For retention cleanup
```

**Proration Calculation** (computed, not stored):
```python
from datetime import datetime
from decimal import Decimal

def calculate_proration(
    old_amount: int,  # cents
    new_amount: int,  # cents
    period_start: datetime,
    period_end: datetime,
    change_date: datetime
) -> tuple[int, int]:  # (credit, charge)
    """
    Calculate prorated credit for old plan and charge for new plan.
    Returns (credit_amount, charge_amount) in cents.
    """
    total_days = (period_end - period_start).days
    days_used = (change_date - period_start).days
    days_remaining = (period_end - change_date).days

    # Credit for unused portion of old plan
    credit = int((old_amount * days_remaining) / total_days)

    # Charge for new plan for remaining days
    charge = int((new_amount * days_remaining) / total_days)

    return (credit, charge)
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Mutable invoices | Financial integrity risk, no audit trail |
| Store proration amounts | Redundant, can be calculated, increases complexity |
| Single subscriptions table with history columns | Hard to query historical state, schema changes difficult |
| NoSQL (MongoDB) | Need ACID transactions for financial data, complex queries |

---

## 3. Background Job Processing

### Decision

**Use ARQ (Async Redis Queue) for background jobs**

- Lightweight, async-first task queue built on Redis
- Perfect for FastAPI async ecosystem
- Simpler than Celery, no message broker overhead
- Built-in cron scheduling, retries, job result storage

### Rationale

- **Async-Native**: ARQ uses async/await, matches FastAPI perfectly. Celery requires separate worker processes.
- **Simplicity**: ARQ is 1/10th the code of Celery. No broker config (just Redis).
- **Performance**: For our scale (100K subscriptions), ARQ handles 10K+ jobs/sec easily.
- **Observability**: Built-in job result storage, easy to monitor job status.

### Job Definitions

```python
# src/billing/workers/billing_cycle.py
from arq import cron
from arq.connections import RedisSettings
from datetime import datetime
from billing.services.subscription_service import SubscriptionService
from billing.database import get_db

async def process_billing_cycles(ctx):
    """
    Run daily at 00:00 UTC.
    Generate invoices for subscriptions ending today.
    """
    async with get_db() as db:
        service = SubscriptionService(db)

        # Find subscriptions ending today
        due_subscriptions = await service.get_subscriptions_due_for_billing(datetime.utcnow())

        for sub in due_subscriptions:
            # Enqueue invoice generation (one job per subscription)
            await ctx['redis'].enqueue_job(
                'generate_invoice',
                sub.id,
                _job_id=f'invoice_{sub.id}_{datetime.utcnow().date()}'  # Idempotent
            )

        return {'processed': len(due_subscriptions)}

async def generate_invoice(ctx, subscription_id: str):
    """Generate invoice for a subscription."""
    async with get_db() as db:
        service = SubscriptionService(db)
        invoice = await service.generate_invoice(subscription_id)

        # Enqueue payment attempt
        await ctx['redis'].enqueue_job('attempt_payment', invoice.id)

        return {'invoice_id': invoice.id}

async def attempt_payment(ctx, invoice_id: str):
    """Attempt payment for an invoice."""
    async with get_db() as db:
        from billing.services.payment_service import PaymentService
        service = PaymentService(db)
        result = await service.attempt_payment(invoice_id)
        return {'payment_id': result.id, 'status': result.status}

# ARQ Worker Configuration
class WorkerSettings:
    redis_settings = RedisSettings(host='redis', port=6379, database=0)

    functions = [
        generate_invoice,
        attempt_payment,
    ]

    cron_jobs = [
        cron(process_billing_cycles, hour=0, minute=0),  # Daily at midnight UTC
    ]

    max_jobs = 50  # Concurrent job limit
    job_timeout = 300  # 5 minutes per job
    keep_result = 3600  # Store results for 1 hour
```

**Payment Retry Worker**:
```python
# src/billing/workers/payment_retry.py
async def schedule_payment_retry(ctx, payment_id: str, attempt: int = 1):
    """Schedule payment retry with exponential backoff."""
    retry_schedule = {
        1: 3 * 24 * 3600,   # Day 3
        2: 5 * 24 * 3600,   # Day 5
        3: 7 * 24 * 3600,   # Day 7
        4: 10 * 24 * 3600,  # Day 10
    }

    if attempt > 4:
        # Max retries reached, mark as overdue
        await ctx['redis'].enqueue_job('mark_account_overdue', payment_id)
        return {'status': 'exhausted'}

    delay = retry_schedule[attempt]
    await ctx['redis'].enqueue_job(
        'retry_payment',
        payment_id,
        attempt,
        _defer_by=delay
    )
    return {'next_retry_in': delay, 'attempt': attempt}

async def retry_payment(ctx, payment_id: str, attempt: int):
    """Retry failed payment."""
    async with get_db() as db:
        from billing.services.payment_service import PaymentService
        service = PaymentService(db)
        result = await service.retry_payment(payment_id)

        if result.status == 'FAILED':
            # Schedule next retry
            await schedule_payment_retry(ctx, payment_id, attempt + 1)

        return {'payment_id': payment_id, 'status': result.status, 'attempt': attempt}
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Celery | Heavyweight, requires RabbitMQ/Redis broker, not async-first, complex setup |
| APScheduler | No distributed job queue, not designed for high-volume tasks |
| Custom async workers | Reinventing the wheel, no job persistence, retry logic |
| FastAPI BackgroundTasks | Not persistent, jobs lost on restart, no retry logic |

---

## 4. Multi-tenancy & Data Isolation

### Decision

**Single-Tenant Deployment (No Multi-Tenancy)**

Each billing platform instance serves one customer (the SaaS company using our platform). No tenant isolation needed.

### Rationale

- **Simplification**: Multi-tenancy adds significant complexity (tenant context, row-level security, query filters).
- **Deployment Model**: Platform is deployed as standalone instance per customer, not SaaS.
- **Data Isolation**: Physical isolation (separate databases) is simpler and more secure than logical isolation.
- **Performance**: No tenant filtering overhead in queries.

### Implications

- Database schema has no `tenant_id` column
- No tenant context middleware
- Simpler queries, no accidental cross-tenant data leaks
- Each customer gets dedicated resources (better performance isolation)

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Multi-tenant with shared database | Complexity, risk of data leaks, tenant context in every query |
| Separate database per tenant | Still need tenant routing logic, deployment complexity |

---

## 5. API Rate Limiting & Authentication

### Decision

**JWT Authentication + Redis-based Rate Limiting**

- **Auth**: JWT tokens with RS256 signing, short-lived access tokens (15min), refresh tokens (7 days)
- **Rate Limiting**: Redis sliding window counter, 1000 requests/hour per API key
- **RBAC**: Role claims in JWT, enforced via FastAPI dependencies

### Implementation

**JWT Configuration**:
```python
# src/billing/api/deps.py
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """Validate JWT and extract user claims."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_PUBLIC_KEY,
            algorithms=["RS256"]
        )

        # Check expiration
        if datetime.fromtimestamp(payload['exp']) < datetime.utcnow():
            raise HTTPException(401, "Token expired")

        return {
            'user_id': payload['sub'],
            'email': payload['email'],
            'roles': payload.get('roles', []),
        }
    except JWTError:
        raise HTTPException(401, "Invalid token")

def require_role(required_role: str):
    """Dependency to enforce role-based access."""
    async def role_checker(user: dict = Depends(get_current_user)):
        if required_role not in user['roles']:
            raise HTTPException(403, f"Role '{required_role}' required")
        return user
    return role_checker

# Usage in endpoint
@router.post("/plans", dependencies=[Depends(require_role("billing_admin"))])
async def create_plan(plan: PlanCreate, db: Session = Depends(get_db)):
    ...
```

**Rate Limiting Middleware**:
```python
# src/billing/api/rate_limit.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis
from time import time

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client: redis.Redis):
        super().__init__(app)
        self.redis = redis_client

    async def dispatch(self, request: Request, call_next):
        # Extract API key from Authorization header
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return await call_next(request)

        api_key = auth.split(" ")[1][:20]  # Use first 20 chars as rate limit key

        # Sliding window rate limit (1000 requests/hour)
        now = int(time())
        window_key = f"rate_limit:{api_key}:{now // 3600}"  # Hour-based window

        count = await self.redis.incr(window_key)
        if count == 1:
            await self.redis.expire(window_key, 3600)

        if count > 1000:
            raise HTTPException(
                429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": 1000,
                    "window": "1 hour",
                    "retry_after": 3600 - (now % 3600)
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = "1000"
        response.headers["X-RateLimit-Remaining"] = str(1000 - count)
        return response
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| API key-only auth (no JWT) | Can't encode user roles, every request needs database lookup |
| Session-based auth | Not stateless, doesn't work well for API-only services |
| OAuth2 password flow | More complex than needed for admin API, JWT simpler |
| In-memory rate limiting | Not distributed, loses state on restart |

---

## 6. GraphQL Schema Design

### Decision

**Use Strawberry GraphQL alongside REST API**

- **Framework**: Strawberry (modern, type-hint based, async-first)
- **Pattern**: GraphQL for complex queries (nested data), REST for mutations
- **N+1 Prevention**: DataLoader pattern for batching database queries
- **Pagination**: Relay-style cursor pagination

### Rationale

- **Developer Experience**: Strawberry uses Python type hints (no separate SDL file), integrates perfectly with Pydantic
- **Performance**: DataLoader prevents N+1 queries, crucial for billing (account → subscriptions → invoices)
- **Flexibility**: Clients can query exact fields needed, reduces over-fetching
- **Complementary**: REST for mutations (create invoice), GraphQL for reads (get account with nested subscriptions)

### Schema Pattern

```python
# src/billing/api/graphql.py
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.dataloader import DataLoader
from typing import List
from billing.models import Account as AccountModel, Subscription as SubscriptionModel

@strawberry.type
class Account:
    id: strawberry.ID
    email: str
    name: str
    currency: str

    @strawberry.field
    async def subscriptions(self, info) -> List["Subscription"]:
        # Use DataLoader to batch subscription queries
        loader = info.context["subscription_loader"]
        return await loader.load(self.id)

@strawberry.type
class Subscription:
    id: strawberry.ID
    status: str
    quantity: int
    plan: "Plan"

    @strawberry.field
    async def invoices(self, info) -> List["Invoice"]:
        loader = info.context["invoice_loader"]
        return await loader.load(self.id)

@strawberry.type
class Query:
    @strawberry.field
    async def account(self, id: strawberry.ID, info) -> Account:
        db = info.context["db"]
        account = await db.get(AccountModel, id)
        return Account(
            id=account.id,
            email=account.email,
            name=account.name,
            currency=account.currency
        )

# DataLoader for batching
async def load_subscriptions(account_ids: List[str], db) -> List[List[SubscriptionModel]]:
    """Batch load subscriptions for multiple accounts."""
    subs = await db.execute(
        select(SubscriptionModel)
        .where(SubscriptionModel.account_id.in_(account_ids))
    )
    # Group by account_id
    grouped = {}
    for sub in subs.scalars():
        grouped.setdefault(sub.account_id, []).append(sub)
    return [grouped.get(aid, []) for aid in account_ids]

# FastAPI integration
schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(
    schema,
    context_getter=lambda request: {
        "db": request.state.db,
        "subscription_loader": DataLoader(load_fn=lambda ids: load_subscriptions(ids, request.state.db))
    }
)
```

**Example Query**:
```graphql
query GetAccountDetails {
  account(id: "123") {
    email
    name
    subscriptions {
      id
      status
      plan {
        name
        amount
      }
      invoices {
        number
        amountDue
        status
      }
    }
  }
}
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Graphene | Older, not async-first, requires separate schema definition |
| REST-only | Clients over-fetch data, many round trips for nested data |
| GraphQL-only | Mutations more complex in GraphQL, REST simpler for writes |

---

## 7. Observability & Monitoring

### Decision

**Structured Logging (structlog) + Prometheus Metrics + OpenTelemetry Tracing**

- **Logging**: structlog for JSON-structured logs, context propagation
- **Metrics**: Prometheus client for business metrics (MRR, invoices/sec, payment success rate)
- **Tracing**: OpenTelemetry for distributed tracing (API → DB → Stripe)
- **Alerting**: Prometheus Alertmanager for critical errors

### Implementation

**Structured Logging**:
```python
# src/billing/main.py
import structlog
from fastapi import Request
import time

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Add request context to all logs in this request
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request.headers.get("X-Request-ID"),
        path=request.url.path,
        method=request.method,
    )

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(
        "request_completed",
        status_code=response.status_code,
        duration_ms=int(duration * 1000)
    )

    return response

# Usage in service
async def create_subscription(account_id: str, plan_id: str):
    logger.info("creating_subscription", account_id=account_id, plan_id=plan_id)
    try:
        subscription = await _create_subscription_logic(account_id, plan_id)
        logger.info("subscription_created", subscription_id=subscription.id)
        return subscription
    except Exception as e:
        logger.error("subscription_creation_failed", error=str(e), exc_info=True)
        raise
```

**Prometheus Metrics**:
```python
# src/billing/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Business metrics
invoices_generated = Counter('invoices_generated_total', 'Total invoices generated')
payments_attempted = Counter('payments_attempted_total', 'Total payment attempts', ['status'])
mrr_gauge = Gauge('mrr_dollars', 'Monthly Recurring Revenue in dollars')

# Performance metrics
api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint']
)

# Usage
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    api_request_duration.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response

# In service
async def generate_invoice(subscription_id: str):
    invoice = await _generate_invoice_logic(subscription_id)
    invoices_generated.inc()
    return invoice
```

**OpenTelemetry Tracing**:
```python
# src/billing/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Setup tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317"))
)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Instrument SQLAlchemy
SQLAlchemyInstrumentor().instrument(engine=engine)

# Manual span creation
tracer = trace.get_tracer(__name__)

async def attempt_payment(invoice_id: str):
    with tracer.start_as_current_span("attempt_payment") as span:
        span.set_attribute("invoice_id", invoice_id)

        invoice = await get_invoice(invoice_id)  # Auto-traced SQL query

        with tracer.start_as_current_span("stripe_charge") as stripe_span:
            result = await stripe_adapter.charge(...)  # Traced external call
            stripe_span.set_attribute("charge_id", result)

        return result
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Plain text logs | Hard to parse, query, aggregate. No structure. |
| ELK stack for metrics | Overkill, Prometheus simpler and more performant for time-series |
| No tracing | Hard to debug distributed systems, latency issues |
| AWS CloudWatch only | Vendor lock-in, harder to run locally |

---

## Summary

All research tasks completed. Key decisions:

1. ✅ **Payment Gateway**: Stripe adapter pattern for testability
2. ✅ **Database**: PostgreSQL with immutable invoices, event sourcing for audit
3. ✅ **Background Jobs**: ARQ (async Redis queue) for simplicity
4. ✅ **Multi-Tenancy**: Single-tenant deployment (no complexity)
5. ✅ **Rate Limiting**: Redis sliding window + JWT auth
6. ✅ **GraphQL**: Strawberry with DataLoader for complex queries
7. ✅ **Observability**: structlog + Prometheus + OpenTelemetry

**Next Phase**: Data Model & Contracts (Phase 1)
