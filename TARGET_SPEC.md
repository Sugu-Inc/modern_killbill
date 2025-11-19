# Feature Specification: Modern Subscription Billing Platform (Target State)

**Feature Branch**: `modernization-2025`
**Created**: 2025-11-19
**Status**: Target Architecture
**Input**: Simplified, cloud-native subscription billing platform for modern SaaS businesses

**Philosophy**: "Simplicity is the ultimate sophistication" - Focus on core billing needs with 20% of features delivering 80% of business value. Modern stack, cloud-native, AI-assisted development.

## Simplification Strategy

**Removed Complexity:**
- ❌ OSGI plugin system → Simple Python plugin interface
- ❌ Complex subscription bundles → Multiple subscriptions with better UX
- ❌ Catalog versioning complexity → Simple grandfathering
- ❌ Separate entitlement system → Integrated with subscriptions
- ❌ Complex overdue state machine → 3-state model (Current/Warning/Blocked)
- ❌ Multiple billing alignment options → Single sensible default
- ❌ Manual batch operations → Async background jobs
- ❌ Payment method complexity → Start with Card + ACH

**Modernized:**
- ✅ Python FastAPI with async/await
- ✅ Cloud-native (managed services for DB, cache, queue)
- ✅ Event-driven architecture (webhooks + internal events)
- ✅ External tax service integration (Stripe Tax, TaxJar)
- ✅ OAuth 2.0 / JWT authentication
- ✅ GraphQL for flexible queries (in addition to REST)
- ✅ Real-time WebSocket for live updates
- ✅ AI-assisted customer support integration

**Result**: ~70K lines of code (down from 144K), faster development, easier maintenance, better developer experience.

---

## User Scenarios & Testing *(mandatory)*

<!--
  Target system focuses on core subscription billing with modern UX.
  Each story delivers standalone value with simplified implementation.
  Prioritized for startup → scale-up → enterprise journey.
-->

---

### User Story 1 - Quick Account Setup (Priority: P1)

**As a** SaaS founder,
**I want to** create customer accounts in seconds with minimal required fields,
**So that** I can start billing customers immediately without complex setup.

**Why this priority**: Zero-friction onboarding is critical for startup velocity. Must be trivial to create first customer account.

**Independent Test**: Call POST /accounts with email and name, receive account ID in <100ms. Can immediately create subscription. Delivers instant customer onboarding.

**Acceptance Scenarios**:

1. **Given** no existing account, **When** I POST {"email": "jane@startup.io", "name": "Jane Doe"}, **Then** account is created with auto-detected timezone and default currency USD
2. **Given** an account, **When** I add payment method via Stripe Elements token, **Then** payment method is stored and verified without manual gateway configuration
3. **Given** an account, **When** I retrieve account details, **Then** I get account info with masked payment method in single API call
4. **Given** duplicate email, **When** I create account, **Then** system creates separate account (emails are not unique identifiers, external_key is)

**Simplified from current**: Removed complex billing address forms, payment method validation complexity, account hierarchy. Default sensible values, allow updates later.

---

### User Story 2 - Dead Simple Pricing (Priority: P1)

**As a** product manager,
**I want to** define pricing plans in JSON with clear tier names,
**So that** customers can understand pricing without confusion.

**Why this priority**: Pricing should be self-service and non-technical. JSON is easier than XML for modern developers.

**Independent Test**: POST /plans with JSON definition {"name": "Starter", "price": 49, "interval": "month"}, create subscription immediately. Delivers instant pricing capability.

**Acceptance Scenarios**:

1. **Given** no plans exist, **When** I create plan via JSON API {"name": "Pro", "monthly": 99, "annual": 999}, **Then** plan is available for subscriptions with both billing periods
2. **Given** a plan with trial, **When** I set {"trial_days": 14}, **Then** subscriptions start with 14-day trial before first charge
3. **Given** a usage plan, **When** I define {"base": 49, "usage": {"api_calls": {"per_unit": 0.01, "tiers": [...]}}}, **Then** system bills base + metered usage
4. **Given** existing subscriptions on old plan, **When** I create plan v2, **Then** old subscriptions continue on v1 pricing (automatic grandfathering)

**Simplified from current**: No XML, no complex catalog uploads, no phase management. Simple JSON, sensible defaults, automatic versioning.

---

### User Story 3 - One-Click Subscriptions (Priority: P1)

**As a** sales rep,
**I want to** create a subscription with one API call,
**So that** customers can start using service immediately after signup.

**Why this priority**: Subscription creation should be instant, not multi-step. Core revenue generation flow.

**Independent Test**: POST /subscriptions {"account_id": "xyz", "plan_id": "pro_monthly"}, subscription is ACTIVE and first invoice generated. Delivers instant customer activation.

**Acceptance Scenarios**:

1. **Given** account with payment method and plan, **When** I POST /subscriptions with account + plan, **Then** subscription is created, first invoice generated, and payment attempted in single transaction
2. **Given** a plan with trial, **When** subscription is created, **Then** status is TRIAL and no payment attempted until trial ends
3. **Given** active subscription, **When** billing date arrives, **Then** invoice auto-generated and payment auto-attempted (no manual triggers needed)
4. **Given** subscription, **When** customer cancels via API, **Then** subscription status changes to CANCELLED and next billing is prevented

**Simplified from current**: No separate invoice commit step, no complex billing alignment, no bundle creation. Single atomic operation creates subscription + invoice + payment attempt.

---

### User Story 4 - Smart Invoicing (Priority: P1)

**As a** finance team,
**I want** invoices to be automatically generated, calculated, and sent,
**So that** billing happens without manual intervention.

**Why this priority**: Automation is essential. Manual invoice operations don't scale. Critical for recurring revenue.

**Independent Test**: Wait for subscription billing date, verify invoice auto-generated with correct proration and auto-emailed to customer. Delivers hands-free billing.

**Acceptance Scenarios**:

1. **Given** subscription with billing date today, **When** billing job runs, **Then** invoice is created with line items, tax calculated via external service, and email sent to customer
2. **Given** subscription upgrade mid-month, **When** change occurs, **Then** invoice shows prorated credit for old plan and prorated charge for new plan automatically
3. **Given** invoice with amount due, **When** I apply account credit, **Then** invoice balance reduces and credit is tracked
4. **Given** incorrect invoice, **When** I void invoice, **Then** new invoice is generated and customer is notified of correction

**Simplified from current**: No draft/commit workflow, invoices auto-finalize. No manual PDF generation, auto-sent via email service. Tax via external API (Stripe Tax/TaxJar).

---

### User Story 5 - Worry-Free Payments (Priority: P1)

**As a** SaaS operator,
**I want** payment retries to happen automatically with smart scheduling,
**So that** I don't lose revenue from temporary payment failures.

**Why this priority**: Payment recovery is critical for cash flow. Should be intelligent and automatic.

**Independent Test**: Create failed payment, verify system retries per schedule (day 3, 5, 7) and updates customer. Delivers automated revenue recovery.

**Acceptance Scenarios**:

1. **Given** invoice due, **When** invoice is created, **Then** payment is automatically attempted via Stripe/gateway with idempotency
2. **Given** payment failure (card declined), **When** failure occurs, **Then** system schedules retries at day 3, 5, 7, 10 and emails customer each time
3. **Given** successful payment, **When** payment completes, **Then** invoice marked PAID, customer receives receipt, webhook sent to app
4. **Given** all retries failed, **When** retry schedule exhausted, **Then** account enters OVERDUE status and subscription is blocked from access

**Simplified from current**: Smart default retry schedule (no configuration needed). Integrated with Stripe for optimal retry timing. Auto-email customer on failures.

---

### User Story 6 - Effortless Plan Changes (Priority: P1)

**As a** customer success manager,
**I want** plan upgrades/downgrades to "just work" with automatic proration,
**So that** customers can self-serve without my intervention.

**Why this priority**: Self-service plan changes reduce support load and enable growth. Must be seamless.

**Independent Test**: Upgrade subscription from Starter to Pro mid-month, verify prorated charges calculated automatically. Delivers self-service flexibility.

**Acceptance Scenarios**:

1. **Given** active subscription on Starter ($49/mo), **When** customer upgrades to Pro ($99/mo) on day 15 of month, **Then** system generates invoice with $24.50 credit (unused Starter) and $49.50 charge (Pro prorated)
2. **Given** subscription on annual plan, **When** customer downgrades to monthly, **Then** remaining annual credit is calculated and applied to monthly billing
3. **Given** downgrade request, **When** customer selects "end of period", **Then** downgrade is scheduled and customer continues on current plan until period ends
4. **Given** plan change, **When** change is processed, **Then** customer receives email confirmation with prorated charges explained clearly

**Simplified from current**: Automatic proration calculation (no manual adjustments). Single API call for upgrades/downgrades. Clear communication to customer.

---

### User Story 7 - Simple Usage Billing (Priority: P2)

**As a** API platform owner,
**I want to** track usage and bill customers based on consumption,
**So that** pricing aligns with value delivered.

**Why this priority**: Usage billing is increasingly common for APIs, but should be simple to implement.

**Independent Test**: Send 1000 usage events via API, verify they appear on next invoice with correct tier pricing. Delivers metered billing capability.

**Acceptance Scenarios**:

1. **Given** a usage-based plan, **When** I POST usage events {"subscription_id": "xyz", "metric": "api_calls", "quantity": 1000}, **Then** usage is tracked and deduplicated by idempotency_key
2. **Given** usage data for billing period, **When** invoice is generated, **Then** usage charges are calculated from tiers (0-1K free, 1K-10K at $0.01, 10K+ at $0.005)
3. **Given** late usage data, **When** data arrives after invoice sent, **Then** supplemental invoice is auto-generated and sent within 24 hours
4. **Given** usage + base subscription, **When** invoice is generated, **Then** invoice shows base fee + usage charges with clear breakdown

**Simplified from current**: Usage events via simple REST API (no complex batching). Automatic aggregation and tier calculation. Deduplication built-in.

---

### User Story 8 - Customer-Friendly Overdue (Priority: P2)

**As a** billing manager,
**I want** gentle dunning that preserves customer relationships,
**So that** we collect payment without driving customers away.

**Why this priority**: Collections should be automated but empathetic. Focus on retention, not just payment.

**Independent Test**: Create overdue invoice, verify customer receives 3 friendly emails before service blocking. Delivers retention-focused collections.

**Acceptance Scenarios**:

1. **Given** invoice 3 days past due, **When** overdue check runs, **Then** customer receives friendly reminder email "Payment failed, please update card"
2. **Given** invoice 7 days past due, **When** check runs, **Then** customer receives urgent email "Service may be interrupted" and account status is WARNING
3. **Given** invoice 14 days past due, **When** check runs, **Then** account status is BLOCKED, service access is restricted, and customer receives "Service suspended" email
4. **Given** blocked account, **When** customer pays, **Then** account is immediately unblocked, service restored, and customer receives "Welcome back" email

**Simplified from current**: 3-state model (Current/Warning/Blocked) instead of complex state machine. Friendly email templates. 14-day maximum before blocking.

---

### User Story 9 - Self-Service Credits (Priority: P2)

**As a** customer support rep,
**I want to** apply credits in seconds via simple interface,
**So that** I can resolve billing issues immediately.

**Why this priority**: Empowering support to resolve issues quickly improves customer satisfaction. Should be trivial.

**Independent Test**: Apply $25 credit to account, verify it auto-applies to next invoice. Delivers instant issue resolution.

**Acceptance Scenarios**:

1. **Given** a customer complaint, **When** I POST /credits {"account_id": "xyz", "amount": 25, "reason": "Goodwill - downtime"}, **Then** credit is added and automatically applied to next invoice
2. **Given** incorrect charge, **When** I void invoice and create credit, **Then** customer receives refund or credit balance based on payment status
3. **Given** account with credit balance, **When** new invoice is generated, **Then** credit is auto-applied and customer only pays remaining balance
4. **Given** credit request, **When** I apply credit, **Then** customer receives email notification explaining the credit

**Simplified from current**: Simple credit API (no complex adjustment workflow). Auto-application to invoices. Clear customer communication.

---

### User Story 10 - Global Ready (Priority: P2)

**As a** international SaaS business,
**I want to** bill customers in their local currency,
**So that** we can expand globally without currency friction.

**Why this priority**: Multi-currency is table stakes for international business. Should be simple to add currencies.

**Independent Test**: Create EUR account, verify invoices and payments in EUR. Delivers international capability.

**Acceptance Scenarios**:

1. **Given** plan with multi-currency pricing, **When** I create account with currency=EUR, **Then** customer is billed in EUR for all transactions
2. **Given** EUR customer, **When** invoice is generated, **Then** amounts display as "€49.00" with proper formatting and customer is charged in EUR
3. **Given** payment in EUR, **When** payment is processed via Stripe, **Then** Stripe handles currency conversion and settlement automatically
4. **Given** 20+ supported currencies, **When** customer selects currency, **Then** plans show pricing in selected currency (from predefined price list)

**Simplified from current**: Leverage Stripe's multi-currency support (no manual currency management). Price plans in major currencies (USD, EUR, GBP, etc.). Auto-formatting.

---

### User Story 11 - Real-Time Integration (Priority: P2)

**As a** developer,
**I want** real-time webhooks for all billing events,
**So that** my application stays synchronized with billing state.

**Why this priority**: Event-driven architecture is modern standard. Enables reactive applications.

**Independent Test**: Subscribe to webhooks, create invoice, receive webhook within 5 seconds. Delivers real-time integration.

**Acceptance Scenarios**:

1. **Given** webhook endpoint configured, **When** invoice is created, **Then** POST request sent to endpoint with {"event": "invoice.created", "data": {...}} within 5 seconds
2. **Given** payment succeeds, **When** payment completes, **Then** webhook "payment.succeeded" is sent with payment and invoice details
3. **Given** webhook fails (endpoint down), **When** delivery fails, **Then** system retries 5 times with exponential backoff (1s, 2s, 4s, 8s, 16s)
4. **Given** multiple event types, **When** I configure webhook, **Then** I can filter events (invoice.*, payment.*, subscription.*)

**Simplified from current**: Webhook-first design (not after-thought). Simple event payload structure. Built-in retry logic. No separate notification plugins.

---

### User Story 12 - Smart Tax Handling (Priority: P2)

**As a** compliance-conscious business,
**I want** automatic tax calculation based on customer location,
**So that** we stay compliant without manual tax management.

**Why this priority**: Tax compliance is critical but shouldn't require billing system complexity. Outsource to experts.

**Independent Test**: Create invoice for CA customer, verify sales tax auto-calculated and added. Delivers tax compliance.

**Acceptance Scenarios**:

1. **Given** customer in California, **When** invoice is generated, **Then** system calls Stripe Tax API and adds 9.5% sales tax to invoice
2. **Given** tax-exempt customer, **When** I set account.tax_exempt=true, **Then** no tax is calculated on invoices
3. **Given** EU customer with VAT ID, **When** invoice is generated, **Then** system validates VAT ID and applies reverse charge if valid
4. **Given** tax rate change, **When** invoice is generated, **Then** current tax rate is used (Stripe Tax handles rate updates)

**Simplified from current**: No internal tax calculation. Integrate with Stripe Tax or TaxJar API. They handle jurisdictions, exemptions, rate changes. Simple on/off flag per account.

---

### User Story 13 - Beautiful Invoices (Priority: P3)

**As a** SaaS business owner,
**I want** professional invoice PDFs with my branding,
**So that** customers receive polished billing documents.

**Why this priority**: Professional appearance matters for B2B. Should be easy to customize.

**Independent Test**: Generate invoice, receive PDF with logo and brand colors. Delivers professional presentation.

**Acceptance Scenarios**:

1. **Given** brand settings configured, **When** invoice is generated, **Then** PDF includes company logo, brand colors, and custom footer
2. **Given** invoice in EUR, **When** PDF is generated, **Then** formatting follows EU conventions (€1.234,56 instead of €1,234.56)
3. **Given** invoice created, **When** customer views invoice, **Then** they can download PDF or view HTML version
4. **Given** custom template, **When** I upload Jinja template, **Then** invoices use custom template for PDF/email

**Simplified from current**: Modern HTML-to-PDF rendering (Playwright/Puppeteer). Jinja templates for customization. Automatic email delivery.

---

### User Story 14 - API-First Everything (Priority: P3)

**As a** developer,
**I want** complete GraphQL API for flexible data querying,
**So that** I can build custom admin interfaces efficiently.

**Why this priority**: Modern APIs should support flexible querying. GraphQL prevents over-fetching and N+1 queries.

**Independent Test**: Query account with nested subscriptions and invoices in single GraphQL request. Delivers efficient data access.

**Acceptance Scenarios**:

1. **Given** GraphQL endpoint, **When** I query `{ account(id: "xyz") { subscriptions { invoices { payments } } } }`, **Then** I receive nested data in single request
2. **Given** REST API, **When** I GET /accounts/xyz, **Then** I receive account data with HATEOAS links to related resources
3. **Given** pagination needed, **When** I query large result sets, **Then** cursor-based pagination is used (no offset/limit)
4. **Given** API documentation, **When** I visit /docs, **Then** I see interactive OpenAPI 3.0 and GraphQL playground

**Simplified from current**: GraphQL for complex queries, REST for simple CRUD. Auto-generated docs. Cursor pagination for all lists.

---

### User Story 15 - Analytics Ready (Priority: P3)

**As a** data analyst,
**I want** subscription metrics (MRR, churn, LTV) calculated automatically,
**So that** I can track business health without custom queries.

**Why this priority**: SaaS metrics should be built-in. Enable data-driven decisions.

**Independent Test**: Call GET /analytics/mrr, receive current MRR and 12-month trend. Delivers business intelligence.

**Acceptance Scenarios**:

1. **Given** active subscriptions, **When** I GET /analytics/mrr, **Then** I receive current MRR, growth rate, and 12-month trend
2. **Given** subscription changes, **When** I GET /analytics/churn, **Then** I receive churn rate, voluntary vs involuntary breakdown
3. **Given** customer base, **When** I GET /analytics/ltv, **Then** I receive average LTV, LTV:CAC ratio, payback period
4. **Given** usage data, **When** I GET /analytics/usage_trends, **Then** I receive usage patterns by plan and customer segment

**Simplified from current**: Pre-calculated metrics (updated hourly). Simple REST endpoints. Export to CSV for deeper analysis. Integration with Amplitude/Mixpanel via events.

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

**Simplified from current**: Simple PAUSED state. Auto-resume on date. 90-day maximum pause (prevent indefinite pause abuse).

---

### Edge Cases

#### Account & Payment Edge Cases
- What happens when account has no payment method and invoice is due?
  - Invoice generates but payment is skipped; customer receives "Add payment method" email; subscription continues in grace period (7 days)
- What happens when customer adds payment method after failed payment?
  - System auto-retries payment within 1 hour of payment method addition
- What happens when payment succeeds on Stripe but webhook fails?
  - Reconciliation job (runs hourly) detects successful Stripe charge and updates invoice to PAID

#### Subscription & Billing Edge Cases
- What happens when subscription is upgraded multiple times in one day?
  - Only final state is invoiced; all intermediate changes are consolidated into single prorated invoice
- What happens when subscription start date is in past?
  - System generates backdated invoice for missed periods and charges immediately
- What happens when plan is deleted but subscriptions exist?
  - Plan is soft-deleted; existing subscriptions continue; new subscriptions blocked; error message suggests alternative plan

#### Usage Billing Edge Cases
- What happens when same usage event is sent twice?
  - Second event is ignored (deduplication by idempotency_key); 200 response returned
- What happens when usage data arrives 3 days after billing period ends?
  - Supplemental invoice is generated with late usage charges; customer receives notification
- What happens when usage exceeds quota/cap?
  - Based on plan config: either bill overage or reject usage events with 429 error

#### Tax & Currency Edge Cases
- What happens when tax service (Stripe Tax) is down?
  - Invoice generation queued and retried every 5 minutes; if down >1 hour, invoice generated without tax (flagged for review)
- What happens when customer changes country mid-subscription?
  - Tax jurisdiction changes on next invoice; no retroactive adjustment
- What happens when currency exchange rate fluctuates?
  - Prices are fixed in plan currency; Stripe handles settlement conversion; no dynamic pricing

#### Overdue & Collections Edge Cases
- What happens when payment arrives while account is blocked?
  - Account immediately unblocked; customer receives "Welcome back" email; service access restored within 5 minutes
- What happens when customer disputes overdue status?
  - Support can set "dispute_hold" flag; prevents further dunning; escalates to finance review

## Requirements *(mandatory)*

### Functional Requirements

#### Account Management (FR-001 to FR-015)

- **FR-001**: System MUST allow account creation with email and name (minimal required fields)
- **FR-002**: System MUST auto-detect timezone from IP address on account creation (can be overridden)
- **FR-003**: System MUST support adding payment methods via Stripe Elements or Checkout
- **FR-004**: System MUST tokenize payment methods and never store raw card numbers
- **FR-005**: System MUST support search by email, external_key, or account_id
- **FR-006**: System MUST maintain audit log of all account changes with timestamp and user
- **FR-007**: System MUST support account deletion with GDPR-compliant data export
- **FR-008**: System MUST allow custom metadata as JSON object on accounts
- **FR-009**: System MUST support setting tax_exempt flag per account
- **FR-010**: System MUST validate email format on account creation
- **FR-011**: System MUST support multiple payment methods with one default
- **FR-012**: System MUST auto-detect country from IP for tax purposes (can be overridden)
- **FR-013**: System MUST support account currency (USD, EUR, GBP, CAD, AUD, etc.)
- **FR-014**: System MUST prevent account deletion with active subscriptions or unpaid invoices
- **FR-015**: System MUST export account data as JSON for API consumption

#### Plan Management (FR-016 to FR-025)

- **FR-016**: System MUST allow plan creation via JSON API (no XML)
- **FR-017**: System MUST support monthly and annual billing intervals
- **FR-018**: System MUST support trial periods (trial_days field on plan)
- **FR-019**: System MUST support fixed pricing, usage pricing, or hybrid
- **FR-020**: System MUST support tiered usage pricing (quantity breaks)
- **FR-021**: System MUST support multi-currency pricing per plan
- **FR-022**: System MUST auto-version plans when pricing changes (grandfather old subscriptions)
- **FR-023**: System MUST support plan soft-deletion (hide from new subscriptions, preserve existing)
- **FR-024**: System MUST validate plan JSON structure before saving
- **FR-025**: System MUST allow plan metadata as JSON object

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
- **FR-039**: System MUST support subscription metadata as JSON object
- **FR-040**: System MUST block new subscriptions on overdue accounts

#### Invoice Management (FR-041 to FR-055)

- **FR-041**: System MUST auto-generate invoices with sequential numbering
- **FR-042**: System MUST support invoice states: DRAFT, OPEN, PAID, VOID
- **FR-043**: System MUST auto-finalize invoices (no manual commit step)
- **FR-044**: System MUST calculate tax via external service (Stripe Tax or TaxJar)
- **FR-045**: System MUST generate invoice PDF via HTML template rendering
- **FR-046**: System MUST auto-email invoice PDF to customer on creation
- **FR-047**: System MUST support invoice line items with description, quantity, amount
- **FR-048**: System MUST apply account credits automatically to new invoices
- **FR-049**: System MUST support invoice voiding with reason
- **FR-050**: System MUST support supplemental invoices for late usage charges
- **FR-051**: System MUST calculate invoice balance as (amount - payments - credits)
- **FR-052**: System MUST support invoice due date (typically +30 days from invoice date)
- **FR-053**: System MUST prevent invoice modification after finalization (immutable)
- **FR-054**: System MUST support invoice preview (dry-run before committing)
- **FR-055**: System MUST export invoices as JSON via API

#### Payment Processing (FR-056 to FR-070)

- **FR-056**: System MUST auto-attempt payment when invoice is created
- **FR-057**: System MUST integrate with Stripe as primary payment gateway
- **FR-058**: System MUST support payment states: PENDING, SUCCEEDED, FAILED
- **FR-059**: System MUST retry failed payments at day 3, 5, 7, 10 (smart schedule)
- **FR-060**: System MUST handle async webhook from Stripe for payment status
- **FR-061**: System MUST use idempotency keys to prevent duplicate charges
- **FR-062**: System MUST support refunds via Stripe API
- **FR-063**: System MUST send payment receipt email on successful payment
- **FR-064**: System MUST send payment failure email with update payment link
- **FR-065**: System MUST update invoice status to PAID when full payment received
- **FR-066**: System MUST create account credit for overpayments
- **FR-067**: System MUST maintain payment audit log with Stripe transaction IDs
- **FR-068**: System MUST support payment method verification ($0 auth)
- **FR-069**: System MUST handle partial payments (apply to invoice balance)
- **FR-070**: System MUST reconcile payments with Stripe dashboard daily

#### Usage Billing (FR-071 to FR-080)

- **FR-071**: System MUST accept usage events via REST API with idempotency_key
- **FR-072**: System MUST deduplicate usage events by idempotency_key
- **FR-073**: System MUST aggregate usage by subscription and billing period
- **FR-074**: System MUST calculate usage charges based on tiered pricing
- **FR-075**: System MUST include usage charges on invoices with detailed breakdown
- **FR-076**: System MUST support multiple usage metrics per subscription (api_calls, storage_gb, etc.)
- **FR-077**: System MUST accept usage timestamp for backdating events
- **FR-078**: System MUST generate supplemental invoice for late usage (within 7 days of period end)
- **FR-079**: System MUST support usage caps with overage billing or rejection
- **FR-080**: System MUST export usage data via API for analytics

#### Overdue Management (FR-081 to FR-090)

- **FR-081**: System MUST evaluate overdue status daily
- **FR-082**: System MUST support 3 overdue states: CURRENT, WARNING (7 days), BLOCKED (14 days)
- **FR-083**: System MUST send dunning email at each state transition
- **FR-084**: System MUST prevent new subscriptions on BLOCKED accounts
- **FR-085**: System MUST block subscription access on BLOCKED accounts (via webhook to app)
- **FR-086**: System MUST auto-clear overdue status when payment received
- **FR-087**: System MUST support manual overdue override for disputes
- **FR-088**: System MUST maintain overdue history per account
- **FR-089**: System MUST use friendly dunning email templates (not threatening)
- **FR-090**: System MUST calculate overdue days from invoice due date

#### Credits & Adjustments (FR-091 to FR-095)

- **FR-091**: System MUST allow creating account credits via API
- **FR-092**: System MUST auto-apply credits to next invoice
- **FR-093**: System MUST track credit reason and timestamp
- **FR-094**: System MUST support credit balance reporting per account
- **FR-095**: System MUST email customer when credit is applied

#### Tax Calculation (FR-096 to FR-100)

- **FR-096**: System MUST integrate with Stripe Tax or TaxJar API
- **FR-097**: System MUST calculate tax based on customer location and product taxability
- **FR-098**: System MUST respect account.tax_exempt flag (no tax calculation)
- **FR-099**: System MUST validate EU VAT IDs via VIES API
- **FR-100**: System MUST include tax breakdown on invoices (rate, jurisdiction, amount)

#### Multi-Currency (FR-101 to FR-105)

- **FR-101**: System MUST support account currency at creation (immutable)
- **FR-102**: System MUST price plans in major currencies (USD, EUR, GBP, CAD, AUD, JPY)
- **FR-103**: System MUST format currency according to locale (€1.234,56 vs €1,234.56)
- **FR-104**: System MUST process payments in account currency via Stripe
- **FR-105**: System MUST prevent currency changes on existing accounts

#### Webhooks & Integration (FR-106 to FR-115)

- **FR-106**: System MUST send webhooks for all major events (invoice.*, payment.*, subscription.*)
- **FR-107**: System MUST deliver webhooks within 5 seconds of event
- **FR-108**: System MUST retry failed webhooks 5 times with exponential backoff
- **FR-109**: System MUST support webhook signature verification (HMAC)
- **FR-110**: System MUST allow webhook event filtering per endpoint
- **FR-111**: System MUST maintain webhook delivery audit log
- **FR-112**: System MUST support multiple webhook endpoints
- **FR-113**: System MUST send invoice.created, invoice.paid, payment.failed, subscription.cancelled events minimum
- **FR-114**: System MUST include full event payload in webhook (not just IDs)
- **FR-115**: System MUST allow manual webhook retry via API

#### Analytics & Reporting (FR-116 to FR-120)

- **FR-116**: System MUST calculate MRR (Monthly Recurring Revenue) updated hourly
- **FR-117**: System MUST calculate churn rate (voluntary and involuntary) monthly
- **FR-118**: System MUST expose analytics endpoints (/analytics/mrr, /analytics/churn, /analytics/ltv)
- **FR-119**: System MUST export data as CSV for external analytics tools
- **FR-120**: System MUST send events to analytics platform (Amplitude, Mixpanel) via integration

#### API & Developer Experience (FR-121 to FR-130)

- **FR-121**: System MUST expose REST API with OpenAPI 3.0 specification
- **FR-122**: System MUST expose GraphQL API for flexible querying
- **FR-123**: System MUST use cursor-based pagination for all list endpoints
- **FR-124**: System MUST authenticate API requests via Bearer token (JWT)
- **FR-125**: System MUST rate limit API requests (1000 req/hour per API key)
- **FR-126**: System MUST provide interactive API documentation at /docs
- **FR-127**: System MUST return clear error messages with remediation hints
- **FR-128**: System MUST support API versioning via header (API-Version: 2025-01-01)
- **FR-129**: System MUST respond to API requests in <200ms for 95th percentile
- **FR-130**: System MUST support webhooks for real-time updates (alternative to polling)

#### Security & Compliance (FR-131 to FR-140)

- **FR-131**: System MUST use OAuth 2.0 for API authentication
- **FR-132**: System MUST encrypt all data at rest (AES-256)
- **FR-133**: System MUST use HTTPS for all API communications
- **FR-134**: System MUST maintain audit log of all data mutations
- **FR-135**: System MUST support GDPR data export within 48 hours
- **FR-136**: System MUST support GDPR data deletion with cascade
- **FR-137**: System MUST be PCI-DSS compliant via Stripe tokenization (no card storage)
- **FR-138**: System MUST support role-based access control (RBAC) for admin users
- **FR-139**: System MUST hash API keys using bcrypt
- **FR-140**: System MUST support IP whitelisting for API access (optional)

### Key Entities

- **Account**: Customer with billing information. Contains: email, name, currency, timezone, default_payment_method_id, tax_exempt, metadata (JSON), created_at.

- **Plan**: Pricing definition. Contains: name, interval (month/year), amount, currency, trial_days, usage_type (licensed/metered), tiers (for usage), metadata (JSON), active (boolean).

- **Subscription**: Customer enrollment in plan. Contains: account_id, plan_id, status (TRIAL/ACTIVE/PAUSED/CANCELLED), current_period_start, current_period_end, cancel_at_period_end, pause_resumes_at, metadata (JSON).

- **Invoice**: Billing statement. Contains: account_id, subscription_id, number (auto-generated), status (DRAFT/OPEN/PAID/VOID), amount_due, amount_paid, tax, currency, due_date, paid_at, line_items (array), created_at.

- **Payment**: Money received. Contains: invoice_id, amount, currency, status (PENDING/SUCCEEDED/FAILED), stripe_payment_intent_id, payment_method_id, failure_message, created_at.

- **PaymentMethod**: Stored payment instrument. Contains: account_id, stripe_payment_method_id, type (card/ach), card_last4, card_brand, card_exp_month, card_exp_year, is_default, created_at.

- **UsageRecord**: Metered consumption. Contains: subscription_id, metric (string), quantity, timestamp, idempotency_key (for deduplication), metadata (JSON), created_at.

- **Credit**: Account balance. Contains: account_id, amount, currency, reason, applied_to_invoice_id, created_at. Credits auto-apply to next invoice.

- **WebhookEvent**: Event notification. Contains: event_type (string), payload (JSON), endpoint_url, status (PENDING/DELIVERED/FAILED), retry_count, created_at.

- **AnalyticsSnapshot**: Pre-calculated metrics. Contains: metric_name (mrr/churn/ltv), value, period (date), metadata (JSON), created_at. Updated hourly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

#### Performance & Scalability

- **SC-001**: API responds to 95% of requests in <200ms
- **SC-002**: System handles 100 invoices/second generation rate
- **SC-003**: System scales to 100,000 active subscriptions without performance degradation
- **SC-004**: GraphQL queries resolve in <500ms for 95th percentile
- **SC-005**: Webhook delivery success rate >95% on first attempt
- **SC-006**: Database queries optimized to <50ms for 99% of reads
- **SC-007**: System handles 10,000 usage events/minute ingestion

#### Accuracy & Reliability

- **SC-008**: Invoice calculations 100% accurate (zero tolerance for financial errors)
- **SC-009**: Proration calculations accurate to the penny
- **SC-010**: Payment processing success rate >99% (excluding customer card failures)
- **SC-011**: Tax calculations match Stripe Tax/TaxJar 100% (external validation)
- **SC-012**: Zero duplicate charges (idempotency enforcement)
- **SC-013**: Usage event deduplication 100% effective

#### Developer Experience

- **SC-014**: Developers complete basic integration in <2 hours using API docs
- **SC-015**: API documentation completeness score 100% (all endpoints documented)
- **SC-016**: Error messages include remediation guidance in 100% of API errors
- **SC-017**: GraphQL schema introspection provides complete type documentation
- **SC-018**: 90% of common tasks achievable via single API call

#### Business Operations

- **SC-019**: Payment retry mechanism recovers 40% of failed payments within 10 days
- **SC-020**: Involuntary churn reduced by 30% through smart retry
- **SC-021**: Billing support tickets reduced by 70% through automation
- **SC-022**: Time to add new pricing plan: <10 minutes (vs weeks in legacy)
- **SC-023**: MRR calculation updated hourly (real-time business metrics)

#### Customer Experience

- **SC-024**: Invoice email delivery within 5 minutes of generation
- **SC-025**: Customer self-service plan changes complete in <30 seconds
- **SC-026**: Dunning email open rate >50% (friendly messaging)
- **SC-027**: 95% of customers successfully update payment method via self-service link
- **SC-028**: Invoice PDF generation <2 seconds per invoice

#### Code Quality & Maintenance

- **SC-029**: Codebase size <75,000 lines (vs 144,000 in legacy)
- **SC-030**: Test coverage >80% for all critical paths
- **SC-031**: New feature development 3x faster due to simplified architecture
- **SC-032**: Onboarding new developer to codebase in <1 day
- **SC-033**: Zero-downtime deployments achievable

#### Integration & Extensibility

- **SC-034**: Stripe integration handles 100% of payment operations (no custom gateway code)
- **SC-035**: Tax service integration eliminates manual tax configuration
- **SC-036**: Webhook events enable 100% of common integration patterns
- **SC-037**: GraphQL enables custom admin dashboards without backend changes

#### Operational Efficiency

- **SC-038**: System operates with 1 DevOps engineer (vs 3 in legacy)
- **SC-039**: Automated billing reduces finance team workload by 80%
- **SC-040**: Cloud costs <$1,000/month for 10,000 active subscriptions
- **SC-041**: Database backup and restore completes in <30 minutes
- **SC-042**: Monitoring detects 100% of critical errors within 5 minutes

#### Compliance & Security

- **SC-043**: PCI-DSS compliance maintained via Stripe (no internal card storage)
- **SC-044**: GDPR data export completes within 24 hours
- **SC-045**: Audit trail captures 100% of data mutations
- **SC-046**: Zero security vulnerabilities in production (continuous scanning)
- **SC-047**: API rate limiting prevents abuse (no successful DoS attacks)

#### Migration & Adoption

- **SC-048**: Legacy data migration completes with 100% accuracy
- **SC-049**: Parallel run period validates 99.9% invoice accuracy vs legacy
- **SC-050**: Customers experience zero disruption during migration

---

**End of Target Specification**

This specification represents a simplified, modern subscription billing platform that delivers 80% of Kill Bill's value with 50% of the code complexity. Built with Python FastAPI, cloud-native services, and AI-assisted development for rapid iteration and easy maintenance.

**Key Simplifications**:
- 16 user stories (vs 20) with focus on core subscription billing
- 140 functional requirements (vs 205) by removing edge cases
- Leverage Stripe for payments and Stripe Tax for compliance
- Event-driven architecture with webhooks
- GraphQL + REST for flexible data access
- ~70K lines of code vs 144K (51% reduction)

**Modern Stack**:
- Python 3.11+ with FastAPI (async/await)
- PostgreSQL on managed cloud (AWS RDS/Aurora)
- Redis for caching (ElastiCache)
- Stripe for payments and tax
- OAuth 2.0 / JWT for auth
- Docker + Kubernetes for deployment
