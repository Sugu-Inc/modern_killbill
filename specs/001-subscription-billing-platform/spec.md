# Feature Specification: Modern Subscription Billing Platform

**Feature Branch**: `001-subscription-billing-platform`
**Created**: 2025-11-19
**Status**: Draft
**Input**: Build a Modern Subscription Billing Platform based on target_spec.md

**Philosophy**: "Simplicity is the ultimate sophistication" - Focus on core billing needs with 20% of features delivering 80% of business value. Modern approach prioritizing developer experience, customer satisfaction, and operational efficiency.

## Clarifications

### Session 2025-11-19

- Q: What is the target system availability/uptime SLA? → A: 99.9% uptime (43 minutes downtime/month)
- Q: What is the data retention policy for different data types? → A: Invoices/Payments: 7 years, Audit logs: 3 years, Deleted accounts: 30 days

## User Scenarios & Testing *(mandatory)*

<!--
  Target system focuses on core subscription billing with modern user experience.
  Each story delivers standalone value with simplified implementation.
  Prioritized for startup → scale-up → enterprise journey.
-->

---

### User Story 1 - Quick Account Setup (Priority: P1)

**As a** SaaS founder,
**I want to** create customer accounts in seconds with minimal required fields,
**So that** I can start billing customers immediately without complex setup.

**Why this priority**: Zero-friction onboarding is critical for startup velocity. Must be trivial to create first customer account.

**Independent Test**: Create account with email and name, receive account ID in under a second. Can immediately create subscription. Delivers instant customer onboarding.

**Acceptance Scenarios**:

1. **Given** no existing account, **When** I create account with email and name, **Then** account is created with auto-detected timezone and default currency
2. **Given** an account, **When** I add payment method via secure token, **Then** payment method is stored and verified without manual configuration
3. **Given** an account, **When** I retrieve account details, **Then** I get account info with masked payment method in single request
4. **Given** duplicate email, **When** I create account, **Then** system creates separate account (emails are not unique identifiers, external_key is)

---

### User Story 2 - Dead Simple Pricing (Priority: P1)

**As a** product manager,
**I want to** define pricing plans with clear tier names and simple structure,
**So that** customers can understand pricing without confusion.

**Why this priority**: Pricing should be self-service and non-technical. Configuration should be simple and intuitive.

**Independent Test**: Create pricing plan with name, price, and billing interval, then immediately use it for subscriptions. Delivers instant pricing capability.

**Acceptance Scenarios**:

1. **Given** no plans exist, **When** I create plan with monthly and annual pricing, **Then** plan is available for subscriptions with both billing periods
2. **Given** a plan with trial, **When** I set trial period of 14 days, **Then** subscriptions start with trial before first charge
3. **Given** a usage-based plan, **When** I define base price plus metered usage with tiers, **Then** system bills base plus usage
4. **Given** existing subscriptions on old plan, **When** I create plan v2, **Then** old subscriptions continue on v1 pricing (automatic grandfathering)

---

### User Story 3 - One-Click Subscriptions (Priority: P1)

**As a** sales rep,
**I want to** create a subscription with one action,
**So that** customers can start using service immediately after signup.

**Why this priority**: Subscription creation should be instant, not multi-step. Core revenue generation flow.

**Independent Test**: Create subscription with account and plan, subscription becomes active and first invoice generated. Delivers instant customer activation.

**Acceptance Scenarios**:

1. **Given** account with payment method and plan, **When** I create subscription, **Then** subscription is created, first invoice generated, and payment attempted in single transaction
2. **Given** a plan with trial, **When** subscription is created, **Then** status is TRIAL and no payment attempted until trial ends
3. **Given** active subscription, **When** billing date arrives, **Then** invoice auto-generated and payment auto-attempted (no manual triggers needed)
4. **Given** subscription, **When** customer cancels, **Then** subscription status changes to CANCELLED and next billing is prevented

---

### User Story 4 - Smart Invoicing (Priority: P1)

**As a** finance team,
**I want** invoices to be automatically generated, calculated, and sent,
**So that** billing happens without manual intervention.

**Why this priority**: Automation is essential. Manual invoice operations don't scale. Critical for recurring revenue.

**Independent Test**: Wait for subscription billing date, verify invoice auto-generated with correct calculations and auto-delivered to customer. Delivers hands-free billing.

**Acceptance Scenarios**:

1. **Given** subscription with billing date today, **When** billing job runs, **Then** invoice is created with line items, tax calculated, and notification sent to customer
2. **Given** subscription upgrade mid-cycle, **When** change occurs, **Then** invoice shows prorated credit for old plan and prorated charge for new plan automatically
3. **Given** invoice with amount due, **When** I apply account credit, **Then** invoice balance reduces and credit is tracked
4. **Given** incorrect invoice, **When** I void invoice, **Then** new invoice is generated and customer is notified of correction

---

### User Story 5 - Worry-Free Payments (Priority: P1)

**As a** SaaS operator,
**I want** payment retries to happen automatically with smart scheduling,
**So that** I don't lose revenue from temporary payment failures.

**Why this priority**: Payment recovery is critical for cash flow. Should be intelligent and automatic.

**Independent Test**: Create failed payment, verify system retries per schedule and updates customer. Delivers automated revenue recovery.

**Acceptance Scenarios**:

1. **Given** invoice due, **When** invoice is created, **Then** payment is automatically attempted with duplicate charge prevention
2. **Given** payment failure (card declined), **When** failure occurs, **Then** system schedules retries at day 3, 5, 7, 10 and notifies customer each time
3. **Given** successful payment, **When** payment completes, **Then** invoice marked PAID, customer receives receipt, notification sent to application
4. **Given** all retries failed, **When** retry schedule exhausted, **Then** account enters OVERDUE status and subscription is blocked from access

---

### User Story 6 - Effortless Plan Changes (Priority: P1)

**As a** customer success manager,
**I want** plan upgrades/downgrades to "just work" with automatic proration,
**So that** customers can self-serve without my intervention.

**Why this priority**: Self-service plan changes reduce support load and enable growth. Must be seamless.

**Independent Test**: Upgrade subscription from Starter to Pro mid-cycle, verify prorated charges calculated automatically. Delivers self-service flexibility.

**Acceptance Scenarios**:

1. **Given** active subscription on Starter ($49/mo), **When** customer upgrades to Pro ($99/mo) on day 15 of month, **Then** system generates invoice with prorated credit and charge
2. **Given** subscription on annual plan, **When** customer downgrades to monthly, **Then** remaining annual credit is calculated and applied to monthly billing
3. **Given** downgrade request, **When** customer selects "end of period", **Then** downgrade is scheduled and customer continues on current plan until period ends
4. **Given** plan change, **When** change is processed, **Then** customer receives confirmation with prorated charges explained clearly

---

### User Story 7 - Simple Usage Billing (Priority: P2)

**As an** API platform owner,
**I want to** track usage and bill customers based on consumption,
**So that** pricing aligns with value delivered.

**Why this priority**: Usage billing is increasingly common for APIs, but should be simple to implement.

**Independent Test**: Send usage events, verify they appear on next invoice with correct tier pricing. Delivers metered billing capability.

**Acceptance Scenarios**:

1. **Given** a usage-based plan, **When** I submit usage events with unique identifiers, **Then** usage is tracked and deduplicated
2. **Given** usage data for billing period, **When** invoice is generated, **Then** usage charges are calculated from tiers (0-1K free, 1K-10K at $0.01, 10K+ at $0.005)
3. **Given** late usage data, **When** data arrives after invoice sent, **Then** supplemental invoice is auto-generated and sent within 24 hours
4. **Given** usage plus base subscription, **When** invoice is generated, **Then** invoice shows base fee plus usage charges with clear breakdown

---

### User Story 8 - Customer-Friendly Overdue (Priority: P2)

**As a** billing manager,
**I want** gentle dunning that preserves customer relationships,
**So that** we collect payment without driving customers away.

**Why this priority**: Collections should be automated but empathetic. Focus on retention, not just payment.

**Independent Test**: Create overdue invoice, verify customer receives 3 friendly notifications before service blocking. Delivers retention-focused collections.

**Acceptance Scenarios**:

1. **Given** invoice 3 days past due, **When** overdue check runs, **Then** customer receives friendly reminder "Payment failed, please update card"
2. **Given** invoice 7 days past due, **When** check runs, **Then** customer receives urgent notification "Service may be interrupted" and account status is WARNING
3. **Given** invoice 14 days past due, **When** check runs, **Then** account status is BLOCKED, service access is restricted, and customer receives "Service suspended" notification
4. **Given** blocked account, **When** customer pays, **Then** account is immediately unblocked, service restored, and customer receives "Welcome back" notification

---

### User Story 9 - Self-Service Credits (Priority: P2)

**As a** customer support rep,
**I want to** apply credits in seconds via simple interface,
**So that** I can resolve billing issues immediately.

**Why this priority**: Empowering support to resolve issues quickly improves customer satisfaction. Should be trivial.

**Independent Test**: Apply credit to account, verify it auto-applies to next invoice. Delivers instant issue resolution.

**Acceptance Scenarios**:

1. **Given** a customer complaint, **When** I create credit with amount and reason, **Then** credit is added and automatically applied to next invoice
2. **Given** incorrect charge, **When** I void invoice and create credit, **Then** customer receives refund or credit balance based on payment status
3. **Given** account with credit balance, **When** new invoice is generated, **Then** credit is auto-applied and customer only pays remaining balance
4. **Given** credit request, **When** I apply credit, **Then** customer receives notification explaining the credit

---

### User Story 10 - Global Ready (Priority: P2)

**As an** international SaaS business,
**I want to** bill customers in their local currency,
**So that** we can expand globally without currency friction.

**Why this priority**: Multi-currency is table stakes for international business. Should be simple to add currencies.

**Independent Test**: Create EUR account, verify invoices and payments in EUR. Delivers international capability.

**Acceptance Scenarios**:

1. **Given** plan with multi-currency pricing, **When** I create account with currency EUR, **Then** customer is billed in EUR for all transactions
2. **Given** EUR customer, **When** invoice is generated, **Then** amounts display with proper currency formatting and customer is charged in EUR
3. **Given** payment in EUR, **When** payment is processed, **Then** payment gateway handles currency processing automatically
4. **Given** 20+ supported currencies, **When** customer selects currency, **Then** plans show pricing in selected currency from predefined price list

---

### User Story 11 - Real-Time Integration (Priority: P2)

**As a** developer,
**I want** real-time notifications for all billing events,
**So that** my application stays synchronized with billing state.

**Why this priority**: Event-driven architecture is modern standard. Enables reactive applications.

**Independent Test**: Subscribe to event notifications, create invoice, receive notification within 5 seconds. Delivers real-time integration.

**Acceptance Scenarios**:

1. **Given** event endpoint configured, **When** invoice is created, **Then** notification sent to endpoint with event type and data within 5 seconds
2. **Given** payment succeeds, **When** payment completes, **Then** payment success notification is sent with payment and invoice details
3. **Given** notification fails (endpoint down), **When** delivery fails, **Then** system retries 5 times with exponential backoff
4. **Given** multiple event types, **When** I configure notifications, **Then** I can filter events by category

---

### User Story 12 - Smart Tax Handling (Priority: P2)

**As a** compliance-conscious business,
**I want** automatic tax calculation based on customer location,
**So that** we stay compliant without manual tax management.

**Why this priority**: Tax compliance is critical but shouldn't require complex internal management. Leverage external expertise.

**Independent Test**: Create invoice for taxable customer location, verify tax auto-calculated and added. Delivers tax compliance.

**Acceptance Scenarios**:

1. **Given** customer in taxable jurisdiction, **When** invoice is generated, **Then** system calculates appropriate tax and adds to invoice
2. **Given** tax-exempt customer, **When** I set account tax-exempt flag, **Then** no tax is calculated on invoices
3. **Given** EU customer with VAT ID, **When** invoice is generated, **Then** system validates VAT ID and applies reverse charge if valid
4. **Given** tax rate change, **When** invoice is generated, **Then** current tax rate is used automatically

---

### User Story 13 - Beautiful Invoices (Priority: P3)

**As a** SaaS business owner,
**I want** professional invoice documents with my branding,
**So that** customers receive polished billing documents.

**Why this priority**: Professional appearance matters for B2B. Should be easy to customize.

**Independent Test**: Generate invoice, receive document with logo and brand colors. Delivers professional presentation.

**Acceptance Scenarios**:

1. **Given** brand settings configured, **When** invoice is generated, **Then** document includes company logo, brand colors, and custom footer
2. **Given** invoice in EUR, **When** document is generated, **Then** formatting follows EU conventions
3. **Given** invoice created, **When** customer views invoice, **Then** they can download document or view online version
4. **Given** custom template, **When** I upload custom template, **Then** invoices use custom template

---

### User Story 14 - Flexible API Access (Priority: P3)

**As a** developer,
**I want** complete API for flexible data querying,
**So that** I can build custom admin interfaces efficiently.

**Why this priority**: Modern APIs should support flexible querying to prevent over-fetching and enable efficient data access.

**Independent Test**: Query account with nested subscriptions and invoices in single request. Delivers efficient data access.

**Acceptance Scenarios**:

1. **Given** flexible query endpoint, **When** I query account with nested subscriptions and invoices, **Then** I receive nested data in single request
2. **Given** standard API, **When** I retrieve account, **Then** I receive account data with links to related resources
3. **Given** pagination needed, **When** I query large result sets, **Then** cursor-based pagination is used
4. **Given** API documentation, **When** I visit documentation, **Then** I see interactive API explorer and examples

---

### User Story 15 - Analytics Ready (Priority: P3)

**As a** data analyst,
**I want** subscription metrics (MRR, churn, LTV) calculated automatically,
**So that** I can track business health without custom queries.

**Why this priority**: SaaS metrics should be built-in. Enable data-driven decisions.

**Independent Test**: Retrieve MRR metric, receive current MRR and historical trend. Delivers business intelligence.

**Acceptance Scenarios**:

1. **Given** active subscriptions, **When** I retrieve MRR metric, **Then** I receive current MRR, growth rate, and 12-month trend
2. **Given** subscription changes, **When** I retrieve churn metric, **Then** I receive churn rate, voluntary vs involuntary breakdown
3. **Given** customer base, **When** I retrieve LTV metric, **Then** I receive average LTV, LTV:CAC ratio, payback period
4. **Given** usage data, **When** I retrieve usage trends, **Then** I receive usage patterns by plan and customer segment

---

### User Story 16 - Pause Subscriptions (Priority: P3)

**As a** retention-focused business,
**I want** customers to pause subscriptions temporarily,
**So that** we retain customers who might otherwise cancel.

**Why this priority**: Pause is proven retention tactic. Should be trivial to implement.

**Independent Test**: Pause subscription for 30 days, verify no invoices generated during pause. Delivers retention mechanism.

**Acceptance Scenarios**:

1. **Given** active subscription, **When** customer requests pause, **Then** subscription enters PAUSED state and billing stops
2. **Given** paused subscription with resume date, **When** resume date arrives, **Then** subscription auto-resumes to ACTIVE and billing continues
3. **Given** paused subscription, **When** pause period exceeds 90 days, **Then** system auto-cancels and notifies customer
4. **Given** usage-based subscription, **When** subscription is paused, **Then** usage tracking stops and resumes with reactivation

---

### Edge Cases

#### Account & Payment Edge Cases
- What happens when account has no payment method and invoice is due?
  - Invoice generates but payment is skipped; customer receives "Add payment method" notification; subscription continues in grace period (7 days)
- What happens when customer adds payment method after failed payment?
  - System auto-retries payment within 1 hour of payment method addition
- What happens when payment succeeds at gateway but notification fails?
  - Reconciliation job (runs hourly) detects successful charge and updates invoice to PAID

#### Subscription & Billing Edge Cases
- What happens when subscription is upgraded multiple times in one day?
  - Only final state is invoiced; all intermediate changes are consolidated into single prorated invoice
- What happens when subscription start date is in past?
  - System generates backdated invoice for missed periods and charges immediately
- What happens when plan is deleted but subscriptions exist?
  - Plan is soft-deleted; existing subscriptions continue; new subscriptions blocked; error message suggests alternative plan

#### Usage Billing Edge Cases
- What happens when same usage event is sent twice?
  - Second event is ignored (deduplication by unique identifier); success response returned
- What happens when usage data arrives 3 days after billing period ends?
  - Supplemental invoice is generated with late usage charges; customer receives notification
- What happens when usage exceeds quota/cap?
  - Based on plan configuration: either bill overage or reject usage events with appropriate error

#### Tax & Currency Edge Cases
- What happens when tax calculation service is unavailable?
  - Invoice generation queued and retried every 5 minutes; if unavailable >1 hour, invoice generated without tax (flagged for review)
- What happens when customer changes country mid-subscription?
  - Tax jurisdiction changes on next invoice; no retroactive adjustment
- What happens when currency exchange rate fluctuates?
  - Prices are fixed in plan currency; payment gateway handles settlement conversion; no dynamic pricing

#### Overdue & Collections Edge Cases
- What happens when payment arrives while account is blocked?
  - Account immediately unblocked; customer receives "Welcome back" notification; service access restored within 5 minutes
- What happens when customer disputes overdue status?
  - Support can set "dispute_hold" flag; prevents further dunning; escalates to finance review

## Requirements *(mandatory)*

### Functional Requirements

#### Account Management (FR-001 to FR-015)

- **FR-001**: System MUST allow account creation with email and name (minimal required fields)
- **FR-002**: System MUST auto-detect timezone from IP address on account creation (can be overridden)
- **FR-003**: System MUST support adding payment methods via secure payment token
- **FR-004**: System MUST tokenize payment methods and never store raw card numbers
- **FR-005**: System MUST support search by email, external_key, or account_id
- **FR-006**: System MUST maintain audit log of all account changes with timestamp and user
- **FR-007**: System MUST support account deletion with data protection compliant data export
- **FR-008**: System MUST allow custom metadata on accounts
- **FR-009**: System MUST support setting tax_exempt flag per account
- **FR-010**: System MUST validate email format on account creation
- **FR-011**: System MUST support multiple payment methods with one default
- **FR-012**: System MUST auto-detect country from IP for tax purposes (can be overridden)
- **FR-013**: System MUST support account currency (USD, EUR, GBP, CAD, AUD, etc.)
- **FR-014**: System MUST prevent account deletion with active subscriptions or unpaid invoices
- **FR-015**: System MUST export account data for consumption

#### Plan Management (FR-016 to FR-025)

- **FR-016**: System MUST allow plan creation via standard data format
- **FR-017**: System MUST support monthly and annual billing intervals
- **FR-018**: System MUST support trial periods (configurable trial days)
- **FR-019**: System MUST support fixed pricing, usage pricing, or hybrid
- **FR-020**: System MUST support tiered usage pricing (quantity breaks)
- **FR-021**: System MUST support multi-currency pricing per plan
- **FR-022**: System MUST auto-version plans when pricing changes (grandfather old subscriptions)
- **FR-023**: System MUST support plan soft-deletion (hide from new subscriptions, preserve existing)
- **FR-024**: System MUST validate plan structure before saving
- **FR-025**: System MUST allow plan metadata

#### Subscription Management (FR-026 to FR-040)

- **FR-026**: System MUST create subscription, invoice, and payment attempt in single atomic transaction
- **FR-027**: System MUST support subscription states: TRIAL, ACTIVE, PAUSED, CANCELLED, EXPIRED
- **FR-028**: System MUST auto-transition TRIAL to ACTIVE after trial period
- **FR-029**: System MUST support immediate and end-of-term cancellation
- **FR-030**: System MUST calculate prorated charges for mid-period upgrades/downgrades
- **FR-031**: System MUST support scheduled plan changes (effective at period end)
- **FR-032**: System MUST auto-generate invoices on subscription billing date
- **FR-033**: System MUST support subscription pause with auto-resume date
- **FR-034**: System MUST auto-cancel subscriptions paused >90 days
- **FR-035**: System MUST prevent duplicate active subscriptions for same account+plan
- **FR-036**: System MUST support external_key for customer reference
- **FR-037**: System MUST calculate next billing date based on interval (monthly/annual)
- **FR-038**: System MUST allow subscription backdating for migrations
- **FR-039**: System MUST support subscription metadata
- **FR-040**: System MUST block new subscriptions on overdue accounts

#### Invoice Management (FR-041 to FR-055)

- **FR-041**: System MUST auto-generate invoices with sequential numbering
- **FR-042**: System MUST support invoice states: DRAFT, OPEN, PAID, VOID
- **FR-043**: System MUST auto-finalize invoices (no manual commit step)
- **FR-044**: System MUST calculate tax via external service
- **FR-045**: System MUST generate invoice documents via template rendering
- **FR-046**: System MUST auto-send invoice to customer on creation
- **FR-047**: System MUST support invoice line items with description, quantity, amount
- **FR-048**: System MUST apply account credits automatically to new invoices
- **FR-049**: System MUST support invoice voiding with reason
- **FR-050**: System MUST support supplemental invoices for late usage charges
- **FR-051**: System MUST calculate invoice balance as (amount - payments - credits)
- **FR-052**: System MUST support invoice due date (typically +30 days from invoice date)
- **FR-053**: System MUST prevent invoice modification after finalization (immutable)
- **FR-054**: System MUST support invoice preview (dry-run before committing)
- **FR-055**: System MUST export invoices via standard interface

#### Payment Processing (FR-056 to FR-070)

- **FR-056**: System MUST auto-attempt payment when invoice is created
- **FR-057**: System MUST integrate with payment gateway for processing
- **FR-058**: System MUST support payment states: PENDING, SUCCEEDED, FAILED
- **FR-059**: System MUST retry failed payments at day 3, 5, 7, 10 (smart schedule)
- **FR-060**: System MUST handle async notifications from payment gateway for payment status
- **FR-061**: System MUST use idempotency keys to prevent duplicate charges
- **FR-062**: System MUST support refunds via payment gateway
- **FR-063**: System MUST send payment receipt notification on successful payment
- **FR-064**: System MUST send payment failure notification with update payment link
- **FR-065**: System MUST update invoice status to PAID when full payment received
- **FR-066**: System MUST create account credit for overpayments
- **FR-067**: System MUST maintain payment audit log with gateway transaction IDs
- **FR-068**: System MUST support payment method verification (zero-value authorization)
- **FR-069**: System MUST handle partial payments (apply to invoice balance)
- **FR-070**: System MUST reconcile payments with payment gateway daily

#### Usage Billing (FR-071 to FR-080)

- **FR-071**: System MUST accept usage events via interface with unique identifiers
- **FR-072**: System MUST deduplicate usage events by unique identifier
- **FR-073**: System MUST aggregate usage by subscription and billing period
- **FR-074**: System MUST calculate usage charges based on tiered pricing
- **FR-075**: System MUST include usage charges on invoices with detailed breakdown
- **FR-076**: System MUST support multiple usage metrics per subscription (api_calls, storage_gb, etc.)
- **FR-077**: System MUST accept usage timestamp for backdating events
- **FR-078**: System MUST generate supplemental invoice for late usage (within 7 days of period end)
- **FR-079**: System MUST support usage caps with overage billing or rejection
- **FR-080**: System MUST export usage data for analytics

#### Overdue Management (FR-081 to FR-090)

- **FR-081**: System MUST evaluate overdue status daily
- **FR-082**: System MUST support 3 overdue states: CURRENT, WARNING (7 days), BLOCKED (14 days)
- **FR-083**: System MUST send dunning notification at each state transition
- **FR-084**: System MUST prevent new subscriptions on BLOCKED accounts
- **FR-085**: System MUST block subscription access on BLOCKED accounts (via notification to application)
- **FR-086**: System MUST auto-clear overdue status when payment received
- **FR-087**: System MUST support manual overdue override for disputes
- **FR-088**: System MUST maintain overdue history per account
- **FR-089**: System MUST use friendly dunning notification templates (not threatening)
- **FR-090**: System MUST calculate overdue days from invoice due date

#### Credits & Adjustments (FR-091 to FR-095)

- **FR-091**: System MUST allow creating account credits
- **FR-092**: System MUST auto-apply credits to next invoice
- **FR-093**: System MUST track credit reason and timestamp
- **FR-094**: System MUST support credit balance reporting per account
- **FR-095**: System MUST notify customer when credit is applied

#### Tax Calculation (FR-096 to FR-100)

- **FR-096**: System MUST integrate with external tax calculation service
- **FR-097**: System MUST calculate tax based on customer location and product taxability
- **FR-098**: System MUST respect account tax_exempt flag (no tax calculation)
- **FR-099**: System MUST validate EU VAT IDs via external validation service
- **FR-100**: System MUST include tax breakdown on invoices (rate, jurisdiction, amount)

#### Multi-Currency (FR-101 to FR-105)

- **FR-101**: System MUST support account currency at creation (immutable)
- **FR-102**: System MUST price plans in major currencies (USD, EUR, GBP, CAD, AUD, JPY)
- **FR-103**: System MUST format currency according to locale
- **FR-104**: System MUST process payments in account currency
- **FR-105**: System MUST prevent currency changes on existing accounts

#### Event Notifications & Integration (FR-106 to FR-115)

- **FR-106**: System MUST send event notifications for all major events (invoice.*, payment.*, subscription.*)
- **FR-107**: System MUST deliver event notifications within 5 seconds of event
- **FR-108**: System MUST retry failed notifications 5 times with exponential backoff
- **FR-109**: System MUST support notification signature verification
- **FR-110**: System MUST allow event filtering per endpoint
- **FR-111**: System MUST maintain notification delivery audit log
- **FR-112**: System MUST support multiple notification endpoints
- **FR-113**: System MUST send invoice.created, invoice.paid, payment.failed, subscription.cancelled events minimum
- **FR-114**: System MUST include full event payload in notification (not just IDs)
- **FR-115**: System MUST allow manual notification retry

#### Analytics & Reporting (FR-116 to FR-120)

- **FR-116**: System MUST calculate MRR (Monthly Recurring Revenue) updated hourly
- **FR-117**: System MUST calculate churn rate (voluntary and involuntary) monthly
- **FR-118**: System MUST expose analytics endpoints for MRR, churn, and LTV
- **FR-119**: System MUST export data for external analytics tools
- **FR-120**: System MUST send events to analytics platforms via integration

#### API & Developer Experience (FR-121 to FR-130)

- **FR-121**: System MUST expose standard API with complete specification
- **FR-122**: System MUST expose flexible query API for complex data retrieval
- **FR-123**: System MUST use cursor-based pagination for all list endpoints
- **FR-124**: System MUST authenticate API requests via bearer token
- **FR-125**: System MUST rate limit API requests (1000 req/hour per API key)
- **FR-126**: System MUST provide interactive API documentation
- **FR-127**: System MUST return clear error messages with remediation hints
- **FR-128**: System MUST support API versioning
- **FR-129**: System MUST respond to API requests efficiently
- **FR-130**: System MUST support event notifications for real-time updates (alternative to polling)

#### Security & Compliance (FR-131 to FR-140)

- **FR-131**: System MUST use modern authentication for API access
- **FR-132**: System MUST encrypt all data at rest
- **FR-133**: System MUST use encrypted connections for all API communications
- **FR-134**: System MUST maintain audit log of all data mutations
- **FR-135**: System MUST support data protection compliant data export within 48 hours
- **FR-136**: System MUST support data protection compliant data deletion with cascade
- **FR-137**: System MUST be payment card industry compliant via tokenization (no card storage)
- **FR-138**: System MUST support role-based access control for admin users
- **FR-139**: System MUST hash API keys securely
- **FR-140**: System MUST support IP whitelisting for API access (optional)

#### Data Retention (FR-141 to FR-143)

- **FR-141**: System MUST retain invoices and payment records for 7 years for financial compliance
- **FR-142**: System MUST retain audit logs for 3 years for security and compliance purposes
- **FR-143**: System MUST soft-delete account data with 30-day retention before permanent deletion

### Key Entities

- **Account**: Customer with billing information. Contains: email, name, currency, timezone, default_payment_method_id, tax_exempt, metadata, created_at.

- **Plan**: Pricing definition. Contains: name, interval (month/year), amount, currency, trial_days, usage_type (licensed/metered), tiers (for usage), metadata, active (boolean).

- **Subscription**: Customer enrollment in plan. Contains: account_id, plan_id, status (TRIAL/ACTIVE/PAUSED/CANCELLED), current_period_start, current_period_end, cancel_at_period_end, pause_resumes_at, metadata.

- **Invoice**: Billing statement. Contains: account_id, subscription_id, number (auto-generated), status (DRAFT/OPEN/PAID/VOID), amount_due, amount_paid, tax, currency, due_date, paid_at, line_items (array), created_at.

- **Payment**: Money received. Contains: invoice_id, amount, currency, status (PENDING/SUCCEEDED/FAILED), payment_gateway_transaction_id, payment_method_id, failure_message, created_at.

- **PaymentMethod**: Stored payment instrument. Contains: account_id, gateway_payment_method_id, type (card/ach), card_last4, card_brand, card_exp_month, card_exp_year, is_default, created_at.

- **UsageRecord**: Metered consumption. Contains: subscription_id, metric (string), quantity, timestamp, idempotency_key (for deduplication), metadata, created_at.

- **Credit**: Account balance. Contains: account_id, amount, currency, reason, applied_to_invoice_id, created_at. Credits auto-apply to next invoice.

- **EventNotification**: Event notification. Contains: event_type (string), payload, endpoint_url, status (PENDING/DELIVERED/FAILED), retry_count, created_at.

- **AnalyticsSnapshot**: Pre-calculated metrics. Contains: metric_name (mrr/churn/ltv), value, period (date), metadata, created_at. Updated hourly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

#### Performance & Scalability

- **SC-001**: System responds to 95% of API requests in under 200 milliseconds
- **SC-002**: System handles 100 invoices per second generation rate
- **SC-003**: System scales to 100,000 active subscriptions without performance degradation
- **SC-004**: Complex queries resolve in under 500 milliseconds for 95th percentile
- **SC-005**: Event notification delivery success rate above 95% on first attempt
- **SC-006**: Data queries complete in under 50 milliseconds for 99% of reads
- **SC-007**: System handles 10,000 usage events per minute ingestion

#### Accuracy & Reliability

- **SC-008**: Invoice calculations are 100% accurate (zero tolerance for financial errors)
- **SC-009**: Proration calculations accurate to the penny
- **SC-010**: Payment processing success rate above 99% (excluding customer card failures)
- **SC-011**: Tax calculations match external tax service 100%
- **SC-012**: Zero duplicate charges (idempotency enforcement)
- **SC-013**: Usage event deduplication 100% effective

#### Developer Experience

- **SC-014**: Developers complete basic integration in under 2 hours using API documentation
- **SC-015**: API documentation completeness score 100% (all endpoints documented)
- **SC-016**: Error messages include remediation guidance in 100% of API errors
- **SC-017**: API schema provides complete type documentation
- **SC-018**: 90% of common tasks achievable via single API call

#### Business Operations

- **SC-019**: Payment retry mechanism recovers 40% of failed payments within 10 days
- **SC-020**: Involuntary churn reduced by 30% through smart retry
- **SC-021**: Billing support tickets reduced by 70% through automation
- **SC-022**: Time to add new pricing plan: under 10 minutes
- **SC-023**: MRR calculation updated hourly (real-time business metrics)

#### Customer Experience

- **SC-024**: Invoice delivery to customer within 5 minutes of generation
- **SC-025**: Customer self-service plan changes complete in under 30 seconds
- **SC-026**: Dunning notification open rate above 50% (friendly messaging)
- **SC-027**: 95% of customers successfully update payment method via self-service link
- **SC-028**: Invoice document generation under 2 seconds per invoice

#### Code Quality & Maintenance

- **SC-029**: Codebase size 50% smaller than legacy system
- **SC-030**: Test coverage above 80% for all critical paths
- **SC-031**: New feature development 3x faster due to simplified architecture
- **SC-032**: Onboarding new developer to codebase in under 1 day
- **SC-033**: Zero-downtime deployments achievable

#### Integration & Extensibility

- **SC-034**: Payment gateway integration handles 100% of payment operations
- **SC-035**: Tax service integration eliminates manual tax configuration
- **SC-036**: Event notifications enable 100% of common integration patterns
- **SC-037**: Flexible query API enables custom admin dashboards without backend changes

#### Operational Efficiency

- **SC-038**: System operates with minimal DevOps overhead
- **SC-039**: Automated billing reduces finance team workload by 80%
- **SC-040**: Cloud costs under $1,000 per month for 10,000 active subscriptions
- **SC-041**: Database backup and restore completes in under 30 minutes
- **SC-042**: Monitoring detects 100% of critical errors within 5 minutes
- **SC-051**: System maintains 99.9% uptime (maximum 43 minutes downtime per month)

#### Compliance & Security

- **SC-043**: Payment card compliance maintained via tokenization (no internal card storage)
- **SC-044**: Data protection export completes within 24 hours
- **SC-045**: Audit trail captures 100% of data mutations
- **SC-046**: Zero security vulnerabilities in production (continuous scanning)
- **SC-047**: API rate limiting prevents abuse (no successful DoS attacks)

#### Migration & Adoption

- **SC-048**: Legacy data migration completes with 100% accuracy
- **SC-049**: Parallel run period validates 99.9% invoice accuracy vs legacy
- **SC-050**: Customers experience zero disruption during migration

---

**End of Specification**

This specification represents a simplified, modern subscription billing platform that delivers core billing functionality with excellent user experience, developer experience, and operational efficiency.
