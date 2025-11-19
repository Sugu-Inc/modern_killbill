# Tasks: Modern Subscription Billing Platform

**Input**: Design documents from `/home/user/killbill_modern/specs/001-subscription-billing-platform/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Technology Stack**: Python 3.11+, FastAPI, PostgreSQL 15+, Redis 7+, SQLAlchemy 2.0, Alembic, Stripe SDK

**Organization**: Tasks grouped by user story for independent implementation and incremental testing. Each story delivers standalone value.

**Test Strategy**: Integration tests for critical business logic (proration, state transitions, invoice generation). Skip framework feature tests. Test with real PostgreSQL database.

## Format: `- [ ] [ID] [P?] [Story] Description [Risk]`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (e.g., US1, US2)
- **[Risk]**: Review priority for human oversight
  - **[Review - High risk]**: Financial calculations, payments, security, compliance
  - **[Review - Low risk]**: Business logic, infrastructure, integrations
  - **[FYI]**: Setup, documentation, read-only features
- File paths: `backend/src/billing/` (per plan.md structure)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and repository structure

- [x] T001 Create project structure per plan.md: backend/, backend/src/billing/, backend/tests/, backend/alembic/ [FYI]
- [x] T002 Initialize Python 3.11+ project with Poetry and pyproject.toml dependencies (FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, Stripe SDK, httpx, pytest, structlog, prometheus-client, opentelemetry-sdk) [FYI]
- [x] T003 [P] Configure Ruff linting and Black formatting in pyproject.toml [FYI]
- [x] T004 [P] Create .gitignore with Python, __pycache__, .env, venv/, .pytest_cache/ [FYI]
- [x] T005 [P] Create .env.example with DATABASE_URL, REDIS_URL, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET placeholders [FYI]
- [x] T006 [P] Create README.md with project overview and quickstart instructions [FYI]
- [x] T007 [P] Create docker-compose.yml with PostgreSQL 15 and Redis 7 services [FYI]

**Checkpoint**: Project structure initialized, dependencies installed

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure required before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database & Configuration

- [x] T008 Implement backend/src/billing/config.py using pydantic-settings for DATABASE_URL, REDIS_URL, STRIPE_SECRET_KEY, LOG_LEVEL [Review - Low risk]
- [x] T009 Implement backend/src/billing/database.py with SQLAlchemy async engine, sessionmaker, and get_db() dependency [Review - Low risk]
- [x] T010 Setup Alembic in backend/alembic/ with env.py configured for async SQLAlchemy [Review - Low risk]
- [x] T011 Create backend/src/billing/models/base.py with declarative Base class [Review - Low risk]

### Core Application

- [x] T012 Implement backend/src/billing/main.py with FastAPI app, CORS middleware, exception handlers [Review - Low risk]
- [x] T013 [P] Implement backend/src/billing/api/deps.py with get_db(), get_current_user() (JWT auth skeleton) [Review - Low risk]
- [x] T014 [P] Implement backend/src/billing/middleware/logging.py with structlog request/response logging, request_id context [Review - Low risk]
- [x] T015 [P] Implement backend/src/billing/middleware/metrics.py with Prometheus metrics (api_request_duration_seconds histogram, api_errors_total counter) [Review - Low risk]

### Observability (FR-145 to FR-156)

- [x] T016 [P] Implement backend/src/billing/api/v1/health.py with GET /health (liveness), GET /health/ready (readiness checking DB/Redis) [Review - Low risk]
- [x] T017 [P] Implement backend/src/billing/metrics.py with Prometheus metrics: invoices_generated_total, payments_attempted_total{status}, mrr_dollars gauge [Review - Low risk]
- [x] T018 [P] Setup OpenTelemetry tracing in backend/src/billing/tracing.py with FastAPI and SQLAlchemy instrumentation [Review - Low risk]

### Testing Infrastructure

- [x] T019 Create backend/tests/conftest.py with async test database fixtures (pytest-asyncio, test DB session) [FYI]
- [x] T020 [P] Implement backend/tests/utils/factories.py with Faker-based test data generators [FYI]
- [x] T021 [P] Create backend/tests/integration/test_health.py to verify health endpoints work [FYI]

**Checkpoint**: Foundation complete - user stories can now be implemented in parallel

---

## Phase 3: User Story 1 - Quick Account Setup (Priority: P1) 🎯 MVP

**Goal**: Enable zero-friction account creation with email, name, and optional payment method

**Independent Test**: Create account via API, retrieve account details, verify account ID returned instantly

### Tests for US1

> **Write these FIRST, ensure they FAIL, then implement**

- [x] T022 [P] [US1] Integration test for account creation in backend/tests/integration/test_accounts.py (test_create_account_minimal, test_create_account_with_payment_method, test_duplicate_email_creates_separate_accounts) [FYI]
- [x] T023 [P] [US1] Integration test for account retrieval in backend/tests/integration/test_accounts.py (test_get_account_with_masked_payment_method) [FYI]

### Implementation for US1

- [x] T024 [P] [US1] Create Account model in backend/src/billing/models/account.py (UUID id, email, name, currency, timezone, tax_exempt, metadata JSONB, created_at, updated_at) [FYI]
- [x] T025 [P] [US1] Create PaymentMethod model in backend/src/billing/models/payment_method.py (account_id FK, gateway_payment_method_id, type, card_last4, card_brand, is_default) [FYI]
- [x] T026 [P] [US1] Create Pydantic schemas in backend/src/billing/schemas/account.py (AccountCreate, AccountResponse, AccountUpdate) [FYI]
- [x] T027 [P] [US1] Create Pydantic schemas in backend/src/billing/schemas/payment_method.py (PaymentMethodCreate, PaymentMethodResponse) [FYI]
- [x] T028 [US1] Create Alembic migration for accounts and payment_methods tables (indexes on email, created_at) [Review - Low risk]
- [x] T029 [US1] Implement AccountService in backend/src/billing/services/account_service.py (create_account with timezone detection, add_payment_method with Stripe token verification) [Review - Low risk]
- [x] T030 [US1] Implement Stripe adapter in backend/src/billing/integrations/stripe.py (create_customer, attach_payment_method, verify_payment_method) [Review - High risk]
- [x] T031 [US1] Implement POST /v1/accounts endpoint in backend/src/billing/api/v1/accounts.py [Review - Low risk]
- [x] T032 [US1] Implement GET /v1/accounts/{account_id} endpoint in backend/src/billing/api/v1/accounts.py (mask payment method details) [FYI]
- [x] T033 [US1] Implement POST /v1/accounts/{account_id}/payment-methods endpoint in backend/src/billing/api/v1/accounts.py [Review - High risk]

**Checkpoint**: US1 complete - accounts can be created, payment methods attached, accounts retrieved

---

## Phase 4: User Story 2 - Dead Simple Pricing (Priority: P1)

**Goal**: Enable product managers to define pricing plans (monthly/annual, trial, usage-based) with versioning

**Independent Test**: Create plan with name, price, interval; verify plan available for subscriptions immediately

### Tests for US2

- [x] T034 [P] [US2] Integration test for plan creation in backend/tests/integration/test_plans.py (test_create_monthly_annual_plan, test_create_plan_with_trial, test_create_usage_based_plan_with_tiers, test_plan_versioning) [FYI]

### Implementation for US2

- [x] T035 [P] [US2] Create Plan model in backend/src/billing/models/plan.py (UUID id, name, interval, amount, currency, trial_days, usage_type, tiers JSONB, active, version, created_at) [FYI]
- [x] T036 [P] [US2] Create Pydantic schemas in backend/src/billing/schemas/plan.py (PlanCreate, PlanResponse, PlanUpdate, UsageTier) [FYI]
- [x] T037 [US2] Create Alembic migration for plans table (index on active) [Review - Low risk]
- [x] T038 [US2] Implement PlanService in backend/src/billing/services/plan_service.py (create_plan with automatic versioning, calculate_usage_charge for tiered pricing) [Review - High risk]
- [x] T039 [US2] Implement POST /v1/plans endpoint in backend/src/billing/api/v1/plans.py [Review - Low risk]
- [x] T040 [US2] Implement GET /v1/plans endpoint with filtering by active in backend/src/billing/api/v1/plans.py [FYI]
- [x] T041 [US2] Implement GET /v1/plans/{plan_id} endpoint in backend/src/billing/api/v1/plans.py [FYI]

**Checkpoint**: US2 complete - pricing plans can be created and queried

---

## Phase 5: User Story 3 - One-Click Subscriptions (Priority: P1)

**Goal**: Enable instant subscription creation with automatic invoice generation and payment attempt

**Independent Test**: Create subscription, verify status ACTIVE/TRIAL, first invoice auto-generated

### Tests for US3

- [x] T042 [P] [US3] Integration test for subscription creation in backend/tests/integration/test_subscriptions.py (test_create_subscription_with_payment, test_create_subscription_with_trial, test_auto_invoice_on_billing_date, test_cancel_subscription) [FYI]
- [x] T043 [P] [US3] Integration test for subscription state transitions in backend/tests/integration/test_subscriptions.py (test_trial_to_active_transition, test_cancelled_prevents_next_billing) [FYI]

### Implementation for US3

- [x] T044 [P] [US3] Create Subscription model in backend/src/billing/models/subscription.py (UUID id, account_id FK, plan_id FK, status enum, quantity, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at) [FYI]
- [x] T045 [P] [US3] Create SubscriptionHistory model in backend/src/billing/models/subscription.py (for audit trail of status/plan changes) [FYI]
- [x] T046 [P] [US3] Create Pydantic schemas in backend/src/billing/schemas/subscription.py (SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate, SubscriptionStatus enum) [FYI]
- [x] T047 [US3] Create Alembic migration for subscriptions and subscription_history tables (indexes on account_id, status, current_period_end) [Review - Low risk]
- [x] T048 [US3] Implement SubscriptionService in backend/src/billing/services/subscription_service.py (create_subscription, handle_trial_logic, cancel_subscription, check_and_transition_trial_to_active) [Review - High risk]
- [x] T049 [US3] Implement POST /v1/subscriptions endpoint in backend/src/billing/api/v1/subscriptions.py [Review - Low risk]
- [x] T050 [US3] Implement GET /v1/subscriptions/{subscription_id} endpoint in backend/src/billing/api/v1/subscriptions.py [FYI]
- [x] T051 [US3] Implement DELETE /v1/subscriptions/{subscription_id} (cancel) endpoint in backend/src/billing/api/v1/subscriptions.py [FYI]
- [x] T052 [US3] Implement background worker for billing cycle job in backend/src/billing/workers/billing_cycle.py (ARQ worker to auto-generate invoices on current_period_end) [Review - High risk]

**Checkpoint**: US3 complete - subscriptions can be created, trials work, auto-billing scheduled

---

## Phase 6: User Story 4 - Smart Invoicing (Priority: P1)

**Goal**: Automatic invoice generation with line items, tax calculation, and customer notification

**Independent Test**: Trigger billing job, verify invoice auto-generated with correct calculations, notification sent

### Tests for US4

- [x] T053 [P] [US4] Integration test for invoice generation in backend/tests/integration/test_invoices.py (test_auto_generate_invoice_from_subscription, test_proration_on_mid_cycle_upgrade, test_apply_credit_to_invoice, test_void_invoice) [FYI]
- [x] T054 [P] [US4] Integration test for proration calculations in backend/tests/integration/test_invoices.py (test_calculate_proration_for_upgrade, test_calculate_proration_for_downgrade) [FYI]

### Implementation for US4

- [x] T055 [P] [US4] Create Invoice model in backend/src/billing/models/invoice.py (UUID id, account_id FK, subscription_id FK, number auto-generated, status enum, amount_due, amount_paid, tax, currency, due_date, paid_at, line_items JSONB, metadata JSONB, created_at, updated_at - immutable after PAID) [FYI]
- [x] T056 [P] [US4] Create Pydantic schemas in backend/src/billing/schemas/invoice.py (InvoiceResponse, InvoiceLineItem, InvoiceStatus enum) [FYI]
- [x] T057 [US4] Create Alembic migration for invoices table (indexes on account_id, subscription_id, status, due_date) [Review - Low risk]
- [x] T058 [US4] Implement InvoiceService in backend/src/billing/services/invoice_service.py (generate_invoice_for_subscription, calculate_proration, apply_credit, void_invoice, calculate_tax via external service) [Review - High risk]
- [x] T059 [US4] Implement tax service integration in backend/src/billing/integrations/tax_service.py (calculate_tax using Stripe Tax API) [Review - High risk]
- [x] T060 [US4] Implement invoice number generator with sequential numbering in backend/src/billing/services/invoice_service.py [Review - Low risk]
- [x] T061 [US4] Implement GET /v1/invoices endpoint in backend/src/billing/api/v1/invoices.py (filter by account, status) [FYI]
- [x] T062 [US4] Implement GET /v1/invoices/{invoice_id} endpoint in backend/src/billing/api/v1/invoices.py [FYI]
- [x] T063 [US4] Implement POST /v1/invoices/{invoice_id}/void endpoint in backend/src/billing/api/v1/invoices.py [Review - High risk]
- [x] T064 [US4] Add invoice generation to billing cycle worker in backend/src/billing/workers/billing_cycle.py (integrate InvoiceService) [Review - High risk]

**Checkpoint**: US4 complete - invoices auto-generate with tax, proration works, voiding works

---

## Phase 7: User Story 5 - Worry-Free Payments (Priority: P1)

**Goal**: Automatic payment attempts with smart retry scheduling and customer notifications

**Independent Test**: Create invoice, verify payment auto-attempted, failed payments trigger retries per schedule

### Tests for US5

- [x] T065 [P] [US5] Integration test for payment processing in backend/tests/integration/test_payments.py (test_auto_attempt_payment_on_invoice_creation, test_payment_retry_schedule, test_successful_payment_marks_invoice_paid, test_all_retries_failed_marks_account_overdue) [FYI]
- [x] T066 [P] [US5] Integration test for idempotency in backend/tests/integration/test_payments.py (test_duplicate_charge_prevention) [FYI]

### Implementation for US5

- [x] T067 [P] [US5] Create Payment model in backend/src/billing/models/payment.py (UUID id, invoice_id FK, amount, currency, status enum, payment_gateway_transaction_id, payment_method_id FK, failure_message, idempotency_key, created_at) [FYI]
- [x] T068 [P] [US5] Create Pydantic schemas in backend/src/billing/schemas/payment.py (PaymentResponse, PaymentStatus enum) [FYI]
- [x] T069 [US5] Create Alembic migration for payments table (indexes on invoice_id, status, idempotency_key) [Review - Low risk]
- [x] T070 [US5] Implement PaymentService in backend/src/billing/services/payment_service.py (attempt_payment with Stripe integration, schedule_retry, process_retry_schedule [day 3,5,7,10], mark_account_overdue) [Review - High risk]
- [ ] T071 [US5] Extend Stripe adapter in backend/src/billing/integrations/stripe.py (charge_payment_method with idempotency key, handle_webhook_events for payment confirmations) [Review - High risk]
- [x] T072 [US5] Implement POST /v1/payments/retry endpoint in backend/src/billing/api/v1/payments.py (manual retry trigger) [Review - Low risk]
- [x] T073 [US5] Implement GET /v1/payments endpoint in backend/src/billing/api/v1/payments.py (filter by invoice, status) [FYI]
- [ ] T074 [US5] Implement Stripe webhook handler in backend/src/billing/api/webhooks/stripe.py (verify signature, process payment_intent.succeeded, payment_intent.payment_failed) [Review - High risk]
- [ ] T075 [US5] Implement background worker for payment retries in backend/src/billing/workers/payment_retry.py (ARQ scheduled job to process retry queue) [Review - High risk]
- [x] T076 [US5] Add payment attempt to billing cycle worker in backend/src/billing/workers/billing_cycle.py (auto-attempt payment after invoice generation) [Review - High risk]

**Checkpoint**: US5 complete - payments auto-attempt, retries work, overdue handling implemented

---

## Phase 8: User Story 6 - Effortless Plan Changes (Priority: P1)

**Goal**: Self-service plan upgrades/downgrades with automatic proration calculation

**Independent Test**: Upgrade subscription mid-cycle, verify prorated invoice generated automatically

### Tests for US6

- [x] T077 [P] [US6] Integration test for plan changes in backend/tests/integration/test_plan_changes.py (test_mid_cycle_upgrade_generates_prorated_invoice, test_annual_to_monthly_downgrade_applies_credit, test_end_of_period_downgrade_scheduling) [FYI]
- [x] T078 [P] [US6] Integration test for proration edge cases in backend/tests/integration/test_plan_changes.py (test_proration_on_day_1, test_proration_on_last_day, test_proration_with_quantity_changes) [FYI]

### Implementation for US6

- [x] T079 [US6] Implement change_plan method in backend/src/billing/services/subscription_service.py (immediate upgrade with proration, end-of-period downgrade scheduling, quantity changes) [Review - High risk]
- [x] T080 [US6] Enhance proration logic in backend/src/billing/services/invoice_service.py (handle upgrades, downgrades, annual-to-monthly conversions, per-seat quantity changes) [Review - High risk]
- [x] T081 [US6] Implement PATCH /v1/subscriptions/{subscription_id} endpoint in backend/src/billing/api/v1/subscriptions.py (change plan, change quantity, schedule_change_at_period_end flag) [Review - Low risk]
- [ ] T082 [US6] Implement background job to process scheduled plan changes in backend/src/billing/workers/billing_cycle.py (check for pending changes at period end) [Review - High risk]

**Checkpoint**: US6 complete - plan changes work with proration, scheduling supported

---

## Phase 9: User Story 7 - Simple Usage Billing (Priority: P2)

**Goal**: Track metered usage events and calculate tier-based charges on invoices

**Independent Test**: Submit usage events, verify they appear on next invoice with correct tier pricing

### Tests for US7

- [x] T083 [P] [US7] Integration test for usage tracking in backend/tests/integration/test_usage.py (test_submit_usage_event_with_idempotency, test_usage_charge_calculation_with_tiers, test_late_usage_generates_supplemental_invoice) [FYI]
- [x] T084 [P] [US7] Integration test for usage deduplication in backend/tests/integration/test_usage.py (test_duplicate_usage_events_ignored) [FYI]

### Implementation for US7

- [x] T085 [P] [US7] Create UsageRecord model in backend/src/billing/models/usage_record.py (UUID id, subscription_id FK, metric, quantity, timestamp, idempotency_key unique, metadata JSONB, created_at) [FYI]
- [x] T086 [P] [US7] Create Pydantic schemas in backend/src/billing/schemas/usage_record.py (UsageRecordCreate, UsageRecordResponse) [FYI]
- [x] T087 [US7] Create Alembic migration for usage_records table (indexes on subscription_id, timestamp, unique index on idempotency_key) [Review - Low risk]
- [x] T088 [US7] Implement UsageService in backend/src/billing/services/usage_service.py (record_usage with deduplication, aggregate_usage_for_period, calculate_tiered_charges) [Review - High risk]
- [x] T089 [US7] Integrate usage charge calculation into InvoiceService in backend/src/billing/services/invoice_service.py (add usage line items to invoice) [Review - High risk]
- [x] T090 [US7] Implement POST /v1/usage endpoint in backend/src/billing/api/v1/usage.py (submit usage events with idempotency_key) [Review - Low risk]
- [x] T091 [US7] Implement GET /v1/subscriptions/{subscription_id}/usage endpoint in backend/src/billing/api/v1/subscriptions.py (query usage for period) [FYI]
- [ ] T092 [US7] Implement background job for late usage processing in backend/src/billing/workers/usage_finalizer.py (generate supplemental invoices for usage arriving after period close, within 7-day window) [Review - High risk]

**Checkpoint**: US7 complete - usage tracking works, tier billing implemented, late usage handled

---

## Phase 10: User Story 8 - Customer-Friendly Overdue (Priority: P2)

**Goal**: Gentle dunning process with progressive notifications and service blocking

**Independent Test**: Create overdue invoice, verify 3 notifications sent before service blocking

### Tests for US8

- [x] T093 [P] [US8] Integration test for dunning process in backend/tests/integration/test_dunning.py (test_3_day_reminder_sent, test_7_day_warning_with_account_warning_status, test_14_day_service_blocking, test_payment_unblocks_account) [FYI]

### Implementation for US8

- [x] T094 [US8] Implement DunningService in backend/src/billing/services/dunning_service.py (check_overdue_invoices, send_reminder [day 3], send_warning [day 7], block_account [day 14], unblock_on_payment) [Review - Low risk]
- [x] T095 [US8] Add account status field to Account model in backend/src/billing/models/account.py (status enum: ACTIVE, WARNING, BLOCKED) [Review - Low risk]
- [x] T096 [US8] Create Alembic migration to add status column to accounts table [Review - Low risk]
- [ ] T097 [US8] Implement background worker for dunning process in backend/src/billing/workers/dunning.py (ARQ scheduled daily job) [Review - Low risk]
- [x] T098 [US8] Implement notification service integration in backend/src/billing/integrations/notification_service.py (send email/SMS via external service) [Review - Low risk]

**Checkpoint**: US8 complete - dunning process runs automatically, service blocking works

---

## Phase 11: User Story 9 - Self-Service Credits (Priority: P2)

**Goal**: Support reps can apply credits instantly with automatic application to next invoice

**Independent Test**: Apply credit, verify auto-applied to next invoice, remaining balance tracked

### Tests for US9

- [ ] T099 [P] [US9] Integration test for credits in backend/tests/integration/test_credits.py (test_create_credit_auto_applies_to_next_invoice, test_void_invoice_creates_credit, test_credit_reduces_invoice_balance) [FYI]

### Implementation for US9

- [ ] T100 [P] [US9] Create Credit model in backend/src/billing/models/credit.py (UUID id, account_id FK, amount, currency, reason, applied_to_invoice_id FK nullable, created_at) [FYI]
- [ ] T101 [P] [US9] Create Pydantic schemas in backend/src/billing/schemas/credit.py (CreditCreate, CreditResponse) [FYI]
- [ ] T102 [US9] Create Alembic migration for credits table (indexes on account_id, applied_to_invoice_id) [Review - Low risk]
- [ ] T103 [US9] Implement CreditService in backend/src/billing/services/credit_service.py (create_credit, apply_credit_to_invoice, get_available_credits_for_account) [Review - High risk]
- [ ] T104 [US9] Integrate credit application into InvoiceService in backend/src/billing/services/invoice_service.py (auto-apply credits when generating invoice) [Review - High risk]
- [ ] T105 [US9] Implement POST /v1/credits endpoint in backend/src/billing/api/v1/credits.py [Review - Low risk]
- [ ] T106 [US9] Implement GET /v1/accounts/{account_id}/credits endpoint in backend/src/billing/api/v1/accounts.py [FYI]

**Checkpoint**: US9 complete - credits can be created and auto-apply to invoices

---

## Phase 12: User Story 10 - Global Ready (Priority: P2)

**Goal**: Support multi-currency billing with proper formatting per currency

**Independent Test**: Create EUR account, verify invoices and payments in EUR with proper formatting

### Tests for US10

- [ ] T107 [P] [US10] Integration test for multi-currency in backend/tests/integration/test_multi_currency.py (test_create_eur_account, test_invoice_in_eur, test_payment_in_eur, test_currency_formatting) [FYI]

### Implementation for US10

- [ ] T108 [US10] Implement currency validation and formatting utilities in backend/src/billing/utils/currency.py (validate_currency, format_amount_for_currency, supported_currencies list) [Review - Low risk]
- [ ] T109 [US10] Add multi-currency support to Plan model (allow multiple currency prices per plan in backend/src/billing/models/plan.py) [Review - High risk]
- [ ] T110 [US10] Update PlanService to handle currency-specific pricing in backend/src/billing/services/plan_service.py [Review - High risk]
- [ ] T111 [US10] Update invoice and payment formatting to use currency utils in backend/src/billing/services/invoice_service.py and payment_service.py [Review - Low risk]
- [ ] T112 [US10] Configure Stripe integration for multi-currency in backend/src/billing/integrations/stripe.py (set currency when creating charges) [Review - High risk]

**Checkpoint**: US10 complete - multi-currency billing works with 20+ currencies

---

## Phase 13: User Story 11 - Real-Time Integration (Priority: P2)

**Goal**: Send real-time webhook notifications for all billing events with retry logic

**Independent Test**: Subscribe to webhooks, create invoice, verify notification received within 5 seconds

### Tests for US11

- [ ] T113 [P] [US11] Integration test for webhooks in backend/tests/integration/test_webhooks.py (test_invoice_created_event_sent, test_payment_succeeded_event_sent, test_webhook_retry_on_failure) [FYI]

### Implementation for US11

- [ ] T114 [P] [US11] Create WebhookEvent model in backend/src/billing/models/webhook_event.py (UUID id, event_type, payload JSONB, endpoint_url, status enum, retry_count, created_at, delivered_at) [FYI]
- [ ] T115 [P] [US11] Create Pydantic schemas in backend/src/billing/schemas/webhook_event.py (WebhookEventResponse, WebhookEventType enum) [FYI]
- [ ] T116 [US11] Create Alembic migration for webhook_events table (indexes on status, event_type) [Review - Low risk]
- [ ] T117 [US11] Implement WebhookService in backend/src/billing/services/webhook_service.py (send_event, retry_failed_events with exponential backoff [5 retries], filter_events_by_category) [Review - Low risk]
- [ ] T118 [US11] Implement POST /v1/webhook-endpoints endpoint in backend/src/billing/api/v1/webhook_endpoints.py (configure webhook endpoint URL) [Review - Low risk]
- [ ] T119 [US11] Implement background worker for webhook delivery in backend/src/billing/workers/webhook_delivery.py (ARQ async job for non-blocking delivery) [Review - Low risk]
- [ ] T120 [US11] Integrate webhook events into InvoiceService, PaymentService, SubscriptionService (emit events for state changes) [Review - Low risk]

**Checkpoint**: US11 complete - webhooks deliver in real-time with retry logic

---

## Phase 14: User Story 12 - Smart Tax Handling (Priority: P2)

**Goal**: Automatic tax calculation based on customer location with exemption support

**Independent Test**: Create invoice for taxable location, verify tax auto-calculated and added

### Tests for US12

- [ ] T121 [P] [US12] Integration test for tax calculation in backend/tests/integration/test_tax.py (test_calculate_tax_for_jurisdiction, test_tax_exempt_account, test_eu_vat_reverse_charge, test_auto_update_on_rate_change) [FYI]

### Implementation for US12

- [ ] T122 [US12] Enhance TaxService in backend/src/billing/integrations/tax_service.py (calculate_tax_for_invoice, validate_vat_id, apply_reverse_charge_if_valid, get_current_tax_rate) [Review - High risk]
- [ ] T123 [US12] Add tax_id and vat_id fields to Account model in backend/src/billing/models/account.py [Review - Low risk]
- [ ] T124 [US12] Create Alembic migration to add tax_id, vat_id to accounts table [Review - Low risk]
- [ ] T125 [US12] Update InvoiceService to call TaxService for all invoice generation in backend/src/billing/services/invoice_service.py [Review - High risk]
- [ ] T126 [US12] Implement PATCH /v1/accounts/{account_id} endpoint to update tax_exempt flag in backend/src/billing/api/v1/accounts.py [Review - Low risk]

**Checkpoint**: US12 complete - tax auto-calculates, exemptions work, VAT reverse charge supported

---

## Phase 15: User Story 13 - Beautiful Invoices (Priority: P3)

**Goal**: Professional invoice documents with branding (logo, colors, custom footer)

**Independent Test**: Generate invoice, verify document includes logo and brand colors

### Implementation for US13

- [ ] T127 [US13] Implement invoice PDF generator in backend/src/billing/services/invoice_pdf_service.py using WeasyPrint or ReportLab (render HTML to PDF with branding) [FYI]
- [ ] T128 [US13] Create invoice HTML template in backend/src/billing/templates/invoice.html with Jinja2 (support logo, brand colors, custom footer, currency formatting) [FYI]
- [ ] T129 [US13] Implement GET /v1/invoices/{invoice_id}/pdf endpoint in backend/src/billing/api/v1/invoices.py (return PDF document) [FYI]
- [ ] T130 [US13] Add branding settings to config in backend/src/billing/config.py (COMPANY_NAME, LOGO_URL, BRAND_PRIMARY_COLOR, BRAND_SECONDARY_COLOR) [FYI]

**Checkpoint**: US13 complete - invoices can be rendered as branded PDFs

---

## Phase 16: User Story 14 - Flexible API Access (Priority: P3)

**Goal**: GraphQL API for complex nested queries with pagination

**Independent Test**: Query account with nested subscriptions and invoices in single request

### Implementation for US14

- [ ] T131 [P] [US14] Define GraphQL schema using Strawberry in backend/src/billing/graphql/schema.py (Account, Plan, Subscription, Invoice types) [FYI]
- [ ] T132 [P] [US14] Implement GraphQL resolvers in backend/src/billing/graphql/resolvers/ (account_resolver.py, subscription_resolver.py, invoice_resolver.py) [FYI]
- [ ] T133 [US14] Setup DataLoader for N+1 prevention in backend/src/billing/graphql/dataloaders.py (account_loader, plan_loader, subscription_loader) [FYI]
- [ ] T134 [US14] Implement cursor-based pagination for GraphQL queries in backend/src/billing/graphql/pagination.py [FYI]
- [ ] T135 [US14] Mount Strawberry GraphQL app in backend/src/billing/main.py at /graphql endpoint [FYI]

**Checkpoint**: US14 complete - GraphQL API available with efficient nested querying

---

## Phase 17: User Story 15 - Analytics Ready (Priority: P3)

**Goal**: Pre-calculated SaaS metrics (MRR, churn, LTV) available via API

**Independent Test**: Retrieve MRR metric, verify current MRR and 12-month trend returned

### Implementation for US15

- [ ] T136 [P] [US15] Create AnalyticsSnapshot model in backend/src/billing/models/analytics_snapshot.py (metric_name, value, period date, metadata JSONB, created_at) [Review - Low risk]
- [ ] T137 [US15] Create Alembic migration for analytics_snapshots table (indexes on metric_name, period) [Review - Low risk]
- [ ] T138 [US15] Implement AnalyticsService in backend/src/billing/services/analytics_service.py (calculate_mrr, calculate_churn_rate, calculate_ltv, calculate_usage_trends) [Review - Low risk]
- [ ] T139 [US15] Implement GET /v1/analytics/mrr endpoint in backend/src/billing/api/v1/analytics.py [Review - Low risk]
- [ ] T140 [US15] Implement GET /v1/analytics/churn endpoint in backend/src/billing/api/v1/analytics.py [Review - Low risk]
- [ ] T141 [US15] Implement GET /v1/analytics/ltv endpoint in backend/src/billing/api/v1/analytics.py [Review - Low risk]
- [ ] T142 [US15] Implement background worker for analytics calculation in backend/src/billing/workers/analytics.py (ARQ hourly job to update snapshots) [Review - Low risk]

**Checkpoint**: US15 complete - analytics metrics auto-calculate and available via API

---

## Phase 18: User Story 16 - Pause Subscriptions (Priority: P3)

**Goal**: Allow customers to temporarily pause subscriptions with auto-resume

**Independent Test**: Pause subscription, verify no invoices during pause, auto-resume on date

### Tests for US16

- [ ] T143 [P] [US16] Integration test for pause/resume in backend/tests/integration/test_subscription_pause.py (test_pause_stops_billing, test_auto_resume_on_date, test_auto_cancel_after_90_days, test_usage_tracking_stops_during_pause) [FYI]

### Implementation for US16

- [ ] T144 [US16] Add PAUSED status and pause_resumes_at field to Subscription model in backend/src/billing/models/subscription.py [Review - Low risk]
- [ ] T145 [US16] Create Alembic migration to add pause_resumes_at to subscriptions table [Review - Low risk]
- [ ] T146 [US16] Implement pause_subscription and resume_subscription methods in backend/src/billing/services/subscription_service.py (auto-cancel if paused > 90 days) [Review - High risk]
- [ ] T147 [US16] Implement POST /v1/subscriptions/{subscription_id}/pause endpoint in backend/src/billing/api/v1/subscriptions.py [Review - Low risk]
- [ ] T148 [US16] Implement POST /v1/subscriptions/{subscription_id}/resume endpoint in backend/src/billing/api/v1/subscriptions.py [Review - Low risk]
- [ ] T149 [US16] Update billing cycle worker to skip paused subscriptions in backend/src/billing/workers/billing_cycle.py [Review - Low risk]
- [ ] T150 [US16] Add background job to auto-resume subscriptions in backend/src/billing/workers/billing_cycle.py (check pause_resumes_at dates) [Review - Low risk]

**Checkpoint**: US16 complete - subscriptions can be paused and auto-resume

---

## Phase 19: Polish & Cross-Cutting Concerns

**Purpose**: Production readiness, security, performance optimization

### Authentication & Authorization (RBAC - 4 roles per spec)

- [ ] T151 [P] Implement JWT authentication with RS256 signing in backend/src/billing/auth/jwt.py (create_access_token, verify_token) [Review - High risk]
- [ ] T152 [P] Implement RBAC decorator in backend/src/billing/auth/rbac.py with roles: Super Admin, Billing Admin, Support Rep, Finance Viewer [Review - High risk]
- [ ] T153 Integrate auth into get_current_user() dependency in backend/src/billing/api/deps.py [Review - High risk]
- [ ] T154 [P] Add role-based access control to all API endpoints (apply RBAC decorator) [Review - High risk]

### Audit Logging (FR-143)

- [ ] T155 [P] Create AuditLog model in backend/src/billing/models/audit_log.py (entity_type, entity_id, action, user_id, changes JSONB, created_at) [Review - High risk]
- [ ] T156 Create Alembic migration for audit_logs table (indexes on entity_type, entity_id, created_at) [Review - High risk]
- [ ] T157 Implement audit logging decorator in backend/src/billing/utils/audit.py [Review - High risk]
- [ ] T158 Apply audit logging to all create/update/delete operations in services [Review - High risk]

### Performance & Caching

- [ ] T159 [P] Implement Redis caching layer in backend/src/billing/cache.py (cache_get, cache_set, cache_invalidate) [Review - Low risk]
- [ ] T160 [P] Implement rate limiting middleware using Redis in backend/src/billing/middleware/rate_limit.py (1000 req/hour per API key) [Review - Low risk]
- [ ] T161 Add caching to frequently accessed endpoints (GET plans, GET accounts) [Review - Low risk]
- [ ] T162 Add database query optimization: ensure all foreign keys indexed, add composite indexes for common filters [Review - Low risk]

### Data Retention & Cleanup (FR-142 to FR-144)

- [ ] T163 [P] Implement data retention worker in backend/src/billing/workers/data_retention.py (delete audit logs > 3 years, purge soft-deleted accounts after 30 days) [Review - High risk]
- [ ] T164 Implement soft delete for accounts in backend/src/billing/models/account.py (deleted_at field) [Review - High risk]
- [ ] T165 Create Alembic migration to add deleted_at to accounts table [Review - High risk]

### Error Handling & Validation

- [ ] T166 [P] Implement global exception handlers in backend/src/billing/main.py (ValidationError, SQLAlchemyError, StripeError, generic Exception) [Review - Low risk]
- [ ] T167 [P] Add input validation to all Pydantic schemas (email format, UUID format, positive amounts, valid currencies) [Review - Low risk]
- [ ] T168 [P] Implement structured error responses with error codes and remediation hints in backend/src/billing/schemas/error.py [Review - Low risk]

### Documentation

- [ ] T169 [P] Generate OpenAPI documentation at /docs endpoint (FastAPI auto-generates) [FYI]
- [ ] T170 [P] Add API examples and descriptions to all endpoint docstrings [FYI]
- [ ] T171 [P] Create CONTRIBUTING.md with development workflow and testing guidelines [FYI]

### Docker & Deployment

- [ ] T172 [P] Create Dockerfile for backend with Python 3.11 slim base [FYI]
- [ ] T173 [P] Create Kubernetes deployment manifests in k8s/ (deployment.yaml, service.yaml, ingress.yaml, configmap.yaml) [FYI]
- [ ] T174 [P] Configure liveness probe to use /health endpoint in k8s deployment [FYI]
- [ ] T175 [P] Configure readiness probe to use /health/ready endpoint in k8s deployment [FYI]
- [ ] T176 [P] Add Prometheus scraping annotations to k8s service for /metrics endpoint [FYI]

### Final Integration Tests

- [ ] T177 End-to-end test: Create account → Create plan → Create subscription → Generate invoice → Process payment → Verify invoice PAID [FYI]
- [ ] T178 End-to-end test: Create subscription → Upgrade mid-cycle → Verify prorated invoice → Process payment [FYI]
- [ ] T179 End-to-end test: Create usage-based subscription → Submit usage → Generate invoice → Verify usage charges on invoice [FYI]
- [ ] T180 Load test: Verify 100 invoices/sec generation rate using Locust or k6 [FYI]

**Checkpoint**: Platform production-ready with 99.9% uptime capability

---

## Implementation Strategy

### MVP Scope (Recommended First Delivery)

**User Story 1 only**: Quick Account Setup
- Delivers: Create accounts, add payment methods, retrieve accounts
- Time estimate: 1-2 weeks
- Validates: Core infrastructure, database, API framework, Stripe integration
- Tests: Account creation flow works end-to-end

### Incremental Rollout

**Phase 1 (Weeks 1-6)**: P1 User Stories (US1-US6) - Core billing flow
- Accounts → Plans → Subscriptions → Invoices → Payments → Plan Changes
- Delivers: Complete recurring billing platform
- Enables: Monthly/annual subscriptions with auto-billing

**Phase 2 (Weeks 7-10)**: P2 User Stories (US7-US12) - Advanced features
- Usage billing, dunning, credits, multi-currency, webhooks, tax
- Delivers: Usage-based pricing and global expansion capability
- Enables: API platform billing, international customers

**Phase 3 (Weeks 11-12)**: P3 User Stories (US13-US16) - Polish
- Invoice PDFs, GraphQL, analytics, pause
- Delivers: Enterprise features and customer experience improvements

**Phase 4 (Week 13)**: Polish & production hardening
- Auth, audit, caching, monitoring, deployment

---

## Parallel Execution Opportunities

Tasks marked with **[P]** can run in parallel within the same phase:

### Phase 2 (Foundational): All tasks except T008-T011 (dependencies) can run in parallel
### Phase 3 (US1): T022-T027 can run in parallel (different files)
### Phase 4 (US2): T034-T036 can run in parallel
### Phase 5 (US3): T042-T046 can run in parallel
### Phase 6 (US4): T053-T056 can run in parallel
### Phase 7 (US5): T065-T068 can run in parallel
### Phase 19 (Polish): Most tasks can run in parallel (marked with [P])

**Estimated total tasks**: 180
**Estimated parallel reduction**: 40% (72 tasks can run simultaneously)
**Effective sequential tasks**: ~108

---

## Validation Checklist

✅ All tasks follow format: `- [ ] [ID] [P?] [Story] Description with file path`
✅ Tasks organized by user story for independent implementation
✅ Each user story has independent test criteria
✅ Tests focused on business logic (proration, state transitions, invoice generation)
✅ Framework features not tested (per constitution)
✅ Integration tests use real PostgreSQL database (per constitution)
✅ Phase 2 foundational tasks block all user story work
✅ Each phase deliverable and independently testable
✅ MVP scope clearly defined (US1 only)
✅ Parallel execution opportunities identified
✅ File paths use backend/ prefix per plan.md structure
✅ Observability requirements (FR-145 to FR-156) covered in Phase 2
✅ All 10 entities from data-model.md included
✅ All 16 user stories from spec.md covered

---

**Ready for implementation**: Tasks are specific enough for autonomous execution
**Testing philosophy**: Test what matters incrementally, verify each story independently
**Path to production**: MVP → P1 → P2 → P3 → Polish
