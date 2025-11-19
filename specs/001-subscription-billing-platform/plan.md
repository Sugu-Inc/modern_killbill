# Implementation Plan: Modern Subscription Billing Platform

**Branch**: `001-subscription-billing-platform` | **Date**: 2025-11-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-subscription-billing-platform/spec.md`

## Summary

Build a simplified, modern subscription billing platform that delivers 80% of business value with 50% of the code complexity. Cloud-native Python FastAPI backend providing REST and GraphQL APIs for subscription management, invoicing, payment processing, usage billing, and analytics. Integrates with external payment gateway (Stripe) and tax calculation services. Supports multi-currency, per-seat pricing, automated dunning, and real-time webhooks. Target: 100K active subscriptions, 100 invoices/sec, 99.9% uptime.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Stripe SDK, httpx
**Storage**: PostgreSQL 15+ (managed cloud: AWS RDS/Aurora or equivalent)
**Caching**: Redis 7+ (ElastiCache or equivalent)
**Observability**: structlog (JSON logging), Prometheus (metrics), OpenTelemetry (tracing), Alertmanager (alerting)
**Testing**: pytest, pytest-asyncio, Faker, httpx for API tests
**Target Platform**: Linux server (Docker containers on Kubernetes)
**Project Type**: Web backend (API-first, no frontend in this repository)
**Performance Goals**:
- 95% of API requests < 200ms
- 100 invoices/second generation rate
- 10,000 usage events/minute ingestion
**Constraints**:
- 99.9% uptime (43 minutes downtime/month)
- RTO: 4 hours, RPO: 15 minutes
- <200ms p95 API latency
- <50ms p99 database reads
**Scale/Scope**:
- 100,000 active subscriptions
- 16 user stories (P1-P3 prioritized)
- 156 functional requirements
- 4 admin roles (RBAC)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Code Quality Principles

✅ **No Code is Best Code**: Using managed services (Stripe for payments, external tax service) instead of building from scratch. Leveraging SQLAlchemy ORM instead of custom query builders. No unnecessary abstractions.

✅ **Write Succinct and Precise Code**: FastAPI with Pydantic models provides concise endpoint definitions. Python's expressiveness reduces boilerplate. Type hints throughout for clarity.

✅ **No Error Swallowing**: All exceptions logged with context (structlog), propagated to FastAPI exception handlers, returned as structured error responses with remediation hints.

✅ **No Unnecessary Branching**: Early returns in validation logic. State machines for subscription/invoice states instead of nested conditionals. Lookup tables for pricing calculations.

✅ **Organize Code in Appropriate Folders**: Feature-based organization (accounts/, subscriptions/, invoices/, payments/, usage/, analytics/) not technical layers.

### Testing Standards

✅ **No Fluff Tests**: Integration tests with real PostgreSQL test database. No mocked repositories - test actual database interactions.

✅ **Prefer Integration Tests**: API endpoint tests hitting real database. Stripe integration tested with Stripe test mode (real API, test keys).

⚠️ **Use Record/Replay Tests with Real Data**: Will implement for production traffic validation during rollout phase (deferred to Phase 3 - not blocking).

✅ **Test What Matters**: Focus on business logic (proration calculations, subscription state transitions, invoice generation). Skip testing FastAPI framework features.

### User Experience Consistency

⚠️ **UX Principles (10-14)**: This is a backend API - no direct user interface. However, principles apply to:
- API design consistency (REST + GraphQL patterns)
- Error message quality (structured, actionable)
- Webhook payload consistency

### GATE RESULT: ✅ PASS

No blocking violations. Record/replay testing deferred to post-launch validation.

## Project Structure

### Documentation (this feature)

```text
specs/001-subscription-billing-platform/
├── plan.md              # This file
├── research.md          # Phase 0: Technology decisions and patterns
├── data-model.md        # Phase 1: Database schema and entities
├── quickstart.md        # Phase 1: Local development setup
├── contracts/           # Phase 1: API contracts (OpenAPI, GraphQL schema)
└── tasks.md             # Phase 2: Implementation tasks (via /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/                    # Database migrations
│   ├── versions/
│   └── env.py
├── src/
│   └── billing/                # Main package
│       ├── __init__.py
│       ├── main.py             # FastAPI application entry
│       ├── config.py           # Settings (pydantic-settings)
│       ├── database.py         # SQLAlchemy session management
│       ├── models/             # SQLAlchemy ORM models
│       │   ├── __init__.py
│       │   ├── account.py
│       │   ├── plan.py
│       │   ├── subscription.py
│       │   ├── invoice.py
│       │   ├── payment.py
│       │   └── usage.py
│       ├── schemas/            # Pydantic request/response models
│       │   ├── __init__.py
│       │   ├── account.py
│       │   ├── plan.py
│       │   └── ...
│       ├── api/                # REST endpoints
│       │   ├── __init__.py
│       │   ├── deps.py         # Dependencies (auth, db session)
│       │   ├── v1/
│       │   │   ├── __init__.py
│       │   │   ├── accounts.py
│       │   │   ├── plans.py
│       │   │   ├── subscriptions.py
│       │   │   ├── invoices.py
│       │   │   └── ...
│       │   └── graphql.py      # GraphQL endpoint (Strawberry)
│       ├── services/           # Business logic
│       │   ├── __init__.py
│       │   ├── account_service.py
│       │   ├── subscription_service.py
│       │   ├── invoice_service.py
│       │   ├── payment_service.py
│       │   └── usage_service.py
│       ├── integrations/       # External service clients
│       │   ├── __init__.py
│       │   ├── stripe.py
│       │   └── tax_service.py  # Stripe Tax or TaxJar
│       ├── workers/            # Background job processors
│       │   ├── __init__.py
│       │   ├── billing_cycle.py
│       │   ├── payment_retry.py
│       │   └── overdue_check.py
│       └── utils/              # Shared utilities (minimal)
│           ├── __init__.py
│           ├── proration.py
│           └── formatting.py
├── tests/
│   ├── conftest.py             # Pytest fixtures (test DB, clients)
│   ├── integration/            # API endpoint tests
│   │   ├── test_accounts.py
│   │   ├── test_subscriptions.py
│   │   └── ...
│   ├── services/               # Business logic tests
│   │   ├── test_subscription_service.py
│   │   └── ...
│   └── utils/
│       └── test_proration.py
├── Dockerfile
├── docker-compose.yml          # Local dev environment
├── pyproject.toml              # Poetry dependencies
└── README.md

scripts/
└── seed_test_data.py          # Generate realistic test data
```

**Structure Decision**: Backend-only web application (Option 2 variant - no frontend). Feature-based organization within `src/billing/` following constitution principle #5. Models/schemas separated by responsibility (ORM vs API contracts). Services contain business logic, API layer is thin routing.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations requiring justification.*

---

## Phase 0: Outline & Research

**Status**: ✅ COMPLETE

**Objective**: Resolve all "NEEDS CLARIFICATION" items from Technical Context and research best practices for key technical decisions.

### Research Tasks

1. **Payment Gateway Integration Patterns**
   - Decision: How to structure Stripe SDK integration for testability
   - Research: Adapter pattern vs direct SDK usage, webhook signature verification, idempotency

2. **Database Schema Design for Billing**
   - Decision: How to model subscriptions with quantity, proration, credits
   - Research: Temporal data patterns, immutable invoices, audit logging

3. **Background Job Processing**
   - Decision: Which task queue for billing cycles, payment retries, dunning
   - Research: Celery vs ARQ vs custom async workers, job persistence, retry strategies

4. **Multi-tenancy & Data Isolation** (if applicable)
   - Decision: Single-tenant deployment or multi-tenant schema
   - Research: Row-level security, tenant context, query performance

5. **API Rate Limiting & Authentication**
   - Decision: How to implement 1000 req/hour rate limits and JWT auth
   - Research: FastAPI middleware, Redis-based rate limiting, JWT libraries

6. **GraphQL Schema Design**
   - Decision: How to structure GraphQL API alongside REST
   - Research: Strawberry vs Graphene, N+1 query prevention, pagination

7. **Observability & Monitoring**
   - Decision: Logging, metrics, tracing stack
   - Research: structlog configuration, Prometheus metrics, OpenTelemetry
   - **Addresses**: FR-145 to FR-156 (health checks, logging, metrics, tracing, alerting)

**Outputs**: `research.md` with decisions, rationale, and code examples

---

## Phase 1: Design & Contracts

**Status**: ✅ COMPLETE

**Objective**: Design database schema, API contracts, and developer quickstart.

### Artifacts

1. **data-model.md**
   - Entity-Relationship diagrams
   - SQLAlchemy model definitions (Python code snippets)
   - Indexes, constraints, foreign keys
   - State transition diagrams (Subscription, Invoice, Payment states)

2. **contracts/**
   - `openapi.yaml`: Full OpenAPI 3.0 specification for REST API
     - Includes health/monitoring endpoints: `/health` (liveness), `/health/ready` (readiness), `/metrics` (Prometheus)
     - Covers all business endpoints: accounts, plans, subscriptions, invoices, payments, usage, credits, analytics
   - `schema.graphql`: GraphQL schema with queries, mutations, types
   - `webhooks.yaml`: Webhook event payload specifications

3. **quickstart.md**
   - Docker Compose setup for local development
   - Database migration commands
   - Seed data generation
   - Example API requests (curl/httpie)
   - Running tests locally

**Deliverables**:
- Complete database schema ready for Alembic migration
- API contracts ready for code generation
- Developers can start local environment in <5 minutes

---

## Phase 2: Task Breakdown

**Status**: ⏸️ PENDING (generated by `/speckit.tasks` command)

**Note**: This phase is NOT executed by `/speckit.plan`. Run `/speckit.tasks` after completing Phase 1.

**Expected Output**: `tasks.md` with dependency-ordered implementation tasks

---

## Next Steps

1. ✅ Complete this plan document
2. ✅ Execute Phase 0 research (generating `research.md`)
3. ✅ Execute Phase 1 design (generating `data-model.md`, `contracts/*`, `quickstart.md`)
4. ✅ Update agent context with technology choices
5. ⏸️ Run `/speckit.tasks` to generate implementation tasks

**Ready for**: Phase 2 Task Generation (`/speckit.tasks`)
