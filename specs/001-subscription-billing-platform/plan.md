# Implementation Plan: Modern Subscription Billing Platform

**Branch**: `001-subscription-billing-platform` | **Date**: 2025-11-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-subscription-billing-platform/spec.md`

## Summary

Build a production-grade subscription billing platform with REST/GraphQL APIs, supporting:
- Account management with Stripe integration
- Flexible pricing plans (flat-rate + usage-based)
- Subscription lifecycle management (trials, pausing, cancellation)
- Automated invoicing and payment collection
- Usage billing with tiered pricing
- **Complete observability stack (FR-145 to FR-156)**

**Technical Approach**: Python 3.11 + FastAPI async framework with PostgreSQL, following research decisions for Stripe integration, structlog logging, Prometheus metrics, and OpenTelemetry tracing.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0 (async), Pydantic v2, Stripe SDK 7.x, structlog 24.x
**Storage**: PostgreSQL 15+ with JSONB, Redis 7+ for caching/queues
**Testing**: pytest + pytest-asyncio, Faker for test data, httpx for API testing
**Target Platform**: Linux server (Docker containers), cloud-native deployment
**Project Type**: Web application (backend API only)
**Performance Goals**:
- 1000 req/s sustained throughput
- <200ms p95 API latency (FR-154)
- <100ms health check response (FR-145)
- <500ms p95 for complex queries

**Constraints**:
- <200ms p95 API latency for billing operations
- Immutable invoices after PAID status
- Idempotent payment processing
- Audit trail for all state changes

**Scale/Scope**:
- 10k+ active subscriptions
- 50k+ invoices/month
- Multi-currency support
- 180 implementation tasks across 16 user stories

## Observability Requirements (FR-145 to FR-156)

### Health & Readiness (FR-145, FR-146)
- **FR-145**: ✅ IMPLEMENTED - `/health` endpoint responds <100ms with service status
- **FR-146**: ✅ IMPLEMENTED - `/health/ready` checks database + Redis connectivity
- **Implementation**: `src/billing/api/v1/health.py` with async connection testing

### Metrics & Monitoring (FR-147, FR-150, FR-151)
- **FR-147**: ✅ IMPLEMENTED - `/metrics` endpoint in Prometheus format
- **FR-150**: ✅ IMPLEMENTED - Business metrics:
  - `invoices_generated_total` (counter)
  - `payments_attempted_total` (counter with status labels)
  - `mrr_dollars` (gauge)
  - `subscriptions_active` (gauge)
- **FR-151**: ✅ IMPLEMENTED - Performance metrics:
  - `api_request_duration_seconds` (histogram with method/path labels)
  - `db_connection_pool_usage` (gauge - via SQLAlchemy events)
  - `db_query_duration_seconds` (histogram)
- **Implementation**:
  - `src/billing/metrics.py` - business metrics definitions
  - `src/billing/middleware/metrics.py` - MetricsMiddleware for HTTP metrics
  - Prometheus client library integrated

### Logging (FR-148, FR-149)
- **FR-148**: ✅ IMPLEMENTED - JSON structured logging for all API requests:
  - `request_id` (UUID correlation)
  - `method` (HTTP method)
  - `path` (endpoint path)
  - `status_code` (response status)
  - `duration_ms` (request processing time)
- **FR-149**: ✅ IMPLEMENTED - Error logging with context:
  - Full stack traces
  - Correlation IDs via `request_id`
  - Contextual metadata (account_id, subscription_id, etc.)
- **Implementation**:
  - `src/billing/middleware/logging.py` - LoggingMiddleware with structlog
  - JSON output in production, colored console in development
  - Context binding via `contextvars`

### Distributed Tracing (FR-152)
- **FR-152**: ✅ IMPLEMENTED - OpenTelemetry tracing:
  - Automatic instrumentation for FastAPI endpoints
  - SQLAlchemy query tracing
  - Stripe API call tracing (via httpx instrumentation)
  - Span context propagation
- **Implementation**:
  - `src/billing/tracing.py` - OpenTelemetry setup
  - FastAPI instrumentation
  - SQLAlchemy instrumentation

### Alerting (FR-153 to FR-156)
- **FR-153**: ⚠️ REQUIRES DEPLOYMENT CONFIG - Alert on error rate >1% (5min window)
- **FR-154**: ⚠️ REQUIRES DEPLOYMENT CONFIG - Alert on p95 latency >500ms (5min window)
- **FR-155**: ⚠️ REQUIRES DEPLOYMENT CONFIG - Alert on database connection failures
- **FR-156**: ⚠️ REQUIRES DEPLOYMENT CONFIG - Alert on payment gateway failures >5% (15min window)
- **Implementation Plan**:
  - Prometheus Alertmanager rules (to be added in deployment phase)
  - Example rules provided in `deployment/prometheus/alerts.yml`
  - Integration with PagerDuty/Slack for notifications

### Observability Stack Summary

| Component | Technology | Status | Files |
|-----------|-----------|--------|-------|
| Health Checks | FastAPI endpoints | ✅ Implemented | `api/v1/health.py` |
| Metrics | Prometheus | ✅ Implemented | `metrics.py`, `middleware/metrics.py` |
| Logging | structlog | ✅ Implemented | `middleware/logging.py` |
| Tracing | OpenTelemetry | ✅ Implemented | `tracing.py` |
| Alerting | Alertmanager | ⚠️ Deployment config | `deployment/prometheus/` (pending) |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

### Code Quality Principles (I.1-5)

✅ **No Code is Best Code**:
- Leveraging FastAPI/SQLAlchemy instead of custom frameworks
- Using Stripe SDK instead of custom payment processing
- Declarative ORM models instead of imperative SQL

✅ **Succinct and Precise Code**:
- Service layer pattern with single-responsibility services
- Type hints throughout for clarity
- Early returns to reduce nesting

✅ **No Error Swallowing**:
- Comprehensive exception handlers in `main.py`
- Structured error logging with full context
- Explicit error propagation with rollback

✅ **No Unnecessary Branching**:
- Early returns for validation
- Enum-based status instead of string checks
- Data-driven configuration where applicable

✅ **Organized Code**:
- Feature-based organization (accounts, plans, subscriptions)
- Co-located schemas with models
- Clear separation: models, services, api, schemas

### Testing Standards (II.6-9)

✅ **No Fluff Tests**:
- Integration test infrastructure with real database
- Test data factories with Faker
- No mock-heavy tests planned

✅ **Prefer Integration Tests**:
- `tests/integration/` for end-to-end workflows
- Test database setup in `conftest.py`
- Real PostgreSQL connections in tests

✅ **Record/Replay Tests**:
- Webhook payload fixtures planned
- Stripe API response recordings for testing

✅ **Test What Matters**:
- Focus on business logic (billing calculations, state machines)
- Skip framework internals
- Test invoice generation, payment flows, subscription lifecycle

### User Experience (III.10-14)

N/A - Backend API only, no user-facing UI in this project

### Violations Requiring Justification

None - all constitution principles are followed.

## Project Structure

### Documentation (this feature)

```text
specs/001-subscription-billing-platform/
├── spec.md                 # Feature specification (16 user stories, 156 requirements)
├── plan.md                 # This file
├── research.md             # Phase 0 output (completed)
├── data-model.md           # Phase 1 output (completed)
├── quickstart.md           # Phase 1 output (completed)
├── contracts/              # Phase 1 output (OpenAPI schemas, completed)
│   ├── openapi.yml
│   └── graphql.schema
├── tasks.md                # Phase 2 output (180 tasks, in progress)
└── checklists/             # Feature-specific checklists
```

### Source Code (repository root)

```text
backend/
├── src/billing/
│   ├── main.py                    # FastAPI application, routers, exception handlers
│   ├── config.py                  # Pydantic settings (env vars, secrets)
│   ├── database.py                # Async SQLAlchemy engine, session factory
│   ├── metrics.py                 # Prometheus business metrics (FR-150)
│   ├── tracing.py                 # OpenTelemetry setup (FR-152)
│   │
│   ├── models/                    # SQLAlchemy ORM models (12 models)
│   ├── schemas/                   # Pydantic request/response schemas
│   ├── services/                  # Business logic layer
│   ├── adapters/                  # External service integrations (Stripe)
│   ├── api/v1/                    # FastAPI routers
│   │   ├── health.py             # Health/readiness endpoints (FR-145, FR-146)
│   │   ├── accounts.py           # Account + PaymentMethod endpoints
│   │   ├── plans.py              # Plan endpoints
│   │   └── subscriptions.py      # Subscription endpoints
│   ├── middleware/                # Request/response middleware
│   │   ├── logging.py            # Structured logging (FR-148, FR-149)
│   │   └── metrics.py            # Prometheus metrics (FR-147, FR-151)
│   └── workers/                   # Background jobs (ARQ) - pending
│
├── alembic/                       # Database migrations
│   └── versions/
│       └── 20251119_..._initial_schema.py
│
├── tests/
│   ├── conftest.py               # Pytest fixtures (async DB, test data)
│   ├── utils/factories.py        # Test data factories with Faker
│   └── integration/              # Integration tests with real DB
│
├── pyproject.toml                # Poetry dependencies
├── docker-compose.yml            # PostgreSQL + Redis for local dev
├── .env.example
└── README.md

deployment/                        # Pending deployment configurations
├── kubernetes/
│   ├── deployment.yml
│   ├── service.yml
│   └── ingress.yml
└── prometheus/
    ├── alerts.yml                # Alertmanager rules (FR-153 to FR-156)
    └── rules.yml                 # Recording rules for metrics
```

**Structure Decision**: Web application (backend only) structure selected because this is a REST/GraphQL API service with no frontend. Clear separation between models (data), services (business logic), and api (HTTP handlers).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations - constitution principles are followed throughout.

## Implementation Status

### ✅ Completed (31/180 tasks - 17.2%)

**Phase 1-2: Foundational Infrastructure (21 tasks)**
- Project setup (Poetry, Docker, config)
- FastAPI application with middleware
- Database layer (SQLAlchemy async, Alembic)
- All 12 ORM models
- Complete Pydantic schemas
- **Observability stack** (FR-145 to FR-152):
  - Health checks (`api/v1/health.py`)
  - Structured logging (`middleware/logging.py`)
  - Prometheus metrics (`middleware/metrics.py`, `metrics.py`)
  - OpenTelemetry tracing (`tracing.py`)
- Testing infrastructure (pytest, factories, fixtures)

**User Story 1: Account Management (12 tasks)**
- AccountService, PaymentMethodService
- StripeAdapter for payment gateway
- 9 REST API endpoints
- Soft deletes, multi-currency, timezone support

**User Story 2: Pricing Plans (8 tasks)**
- PlanService with versioning
- 7 REST API endpoints
- Flat-rate and usage-based pricing

**User Story 3: Subscription Management (11 tasks)**
- SubscriptionService with full lifecycle
- 9 REST API endpoints
- Trial periods, pause/resume, plan changes
- Subscription history for audit trail

### ⚠️ Pending (149 tasks)

**User Story 4: Invoicing (12 tasks)** - Critical
**User Story 5: Payments (12 tasks)** - Critical
**User Story 7: Usage Billing (12 tasks)** - High Priority
**User Story 8: Dunning (12 tasks)** - High Priority
**User Story 11: Webhooks (12 tasks)** - Required for integrations
**Alert Configuration (FR-153 to FR-156)** - Requires deployment manifests
**Production Polish (30 tasks)** - Auth, caching, rate limiting, deployment

## Observability Implementation Checklist

### Health & Readiness
- [x] FR-145: Health check endpoint (<100ms)
- [x] FR-146: Readiness check (DB + Redis)
- [ ] Kubernetes liveness/readiness probe configuration (deployment phase)

### Metrics
- [x] FR-147: Prometheus /metrics endpoint
- [x] FR-150: Business metrics (invoices, payments, MRR)
- [x] FR-151: Performance metrics (latency, DB pool)
- [ ] Grafana dashboards for visualization (deployment phase)

### Logging
- [x] FR-148: Structured API request logs (JSON)
- [x] FR-149: Error logs with stack traces and correlation
- [ ] Log aggregation (ELK/Loki) configuration (deployment phase)

### Tracing
- [x] FR-152: Distributed tracing (OpenTelemetry)
- [ ] Jaeger/Tempo backend configuration (deployment phase)

### Alerting
- [ ] FR-153: Error rate >1% alert (requires Alertmanager config)
- [ ] FR-154: p95 latency >500ms alert (requires Alertmanager config)
- [ ] FR-155: Database connection failure alert (requires Alertmanager config)
- [ ] FR-156: Payment gateway failure >5% alert (requires Alertmanager config)
- [ ] PagerDuty/Slack integration (deployment phase)

## Next Steps

1. **User Story 4: Invoicing** - Implement InvoiceService, invoice generation, line item calculation
2. **User Story 5: Payments** - Implement PaymentService, automatic collection, retry logic
3. **Deployment Configuration** - Create Kubernetes manifests, Prometheus Alertmanager rules (FR-153 to FR-156)
4. **User Story 7: Usage Billing** - Implement usage aggregation, tier calculation
5. **Production Polish** - Authentication, caching, rate limiting

## Success Criteria

**Observability (FR-145 to FR-156)**:
- [x] All health/metrics/logging endpoints functional
- [x] Structured logs with correlation IDs
- [x] Business and performance metrics exposed
- [x] Distributed tracing operational
- [ ] Alert rules deployed and tested (pending deployment)

**Overall**:
- [ ] 180/180 tasks implemented
- [ ] All 16 user stories complete
- [ ] Integration tests passing
- [ ] Production deployment ready
- [ ] Documentation complete

---

**Plan Status**: Phase 0 (Research) and Phase 1 (Design) complete. Implementation in progress (31/180 tasks). **Observability requirements FR-145 to FR-152 fully implemented in code**, FR-153 to FR-156 require deployment configuration.
