# Migration Plan: Modern Subscription Billing Platform

**Version**: 1.0
**Date**: 2025-11-19
**Status**: Ready for Review
**Target**: Production deployment with zero data loss

---

## Executive Summary

This document outlines the strategy for migrating to the Modern Subscription Billing Platform with a focus on **safe, incremental rollout** with **zero data loss** and **minimal downtime**.

### Key Principles

- **Zero Data Loss**: All existing billing data must be preserved
- **Backward Compatibility**: Maintain API compatibility during migration
- **Incremental Rollout**: Phase-based deployment with rollback capability
- **Continuous Validation**: Data integrity checks at every step
- **Business Continuity**: No interruption to billing cycles or payments

---

## Migration Phases

### Phase 0: Pre-Migration Preparation (Week -2 to -1)

**Objective**: Prepare infrastructure and validate data export

#### Tasks

1. **Infrastructure Setup**
   - [x] Provision PostgreSQL 15 database (AWS RDS/Aurora)
   - [x] Provision Redis 7 cluster (ElastiCache)
   - [x] Set up Kubernetes cluster for application
   - [ ] Configure monitoring (Prometheus, Grafana, Alertmanager)
   - [ ] Set up log aggregation (CloudWatch/ELK/Loki)

2. **Data Assessment**
   - [ ] Export current billing data from legacy system
   - [ ] Validate data completeness (all required fields present)
   - [ ] Identify data quality issues (duplicates, invalid references)
   - [ ] Create data mapping documentation (legacy → new schema)

3. **Test Environment**
   - [ ] Deploy platform to staging environment
   - [ ] Load test data into staging database
   - [ ] Run migration scripts in staging
   - [ ] Validate migrated data against source

4. **Stripe Integration**
   - [ ] Verify Stripe account access (test and production keys)
   - [ ] Map existing Stripe customers to new accounts
   - [ ] Export payment method tokens for migration
   - [ ] Set up webhook endpoints in Stripe dashboard

**Success Criteria**:
- ✅ All infrastructure provisioned and tested
- ✅ Complete data export with validation
- ✅ Successful staging migration with <1% data loss
- ✅ Stripe integration tested in test mode

---

### Phase 1: Data Migration (Week 1, Day 1-3)

**Objective**: Migrate all historical billing data with validation

#### Data Migration Order

Execute in this specific order to maintain referential integrity:

1. **Accounts** (T024-T029)
   ```sql
   -- Legacy to new mapping
   INSERT INTO accounts (id, email, name, currency, timezone, tax_exempt, metadata, created_at, updated_at)
   SELECT
     uuid_generate_v4(),
     customer_email,
     customer_name,
     billing_currency,
     COALESCE(timezone, 'UTC'),
     is_tax_exempt,
     jsonb_build_object('legacy_id', id, 'source', 'migration'),
     created_date,
     updated_date
   FROM legacy_customers;
   ```

2. **Payment Methods** (T025)
   ```sql
   -- Migrate Stripe payment method references
   INSERT INTO payment_methods (id, account_id, gateway_payment_method_id, type, card_last4, card_brand, is_default)
   SELECT
     uuid_generate_v4(),
     a.id,
     lpm.stripe_payment_method_id,
     lpm.type,
     lpm.card_last_four,
     lpm.card_brand,
     lpm.is_default
   FROM legacy_payment_methods lpm
   JOIN accounts a ON a.metadata->>'legacy_id' = lpm.customer_id::text;
   ```

3. **Plans** (T035-T038)
   ```sql
   -- Migrate pricing plans with version tracking
   INSERT INTO plans (id, name, interval, amount, currency, trial_days, usage_type, tiers, active, version, created_at)
   SELECT
     uuid_generate_v4(),
     plan_name,
     billing_interval,
     price_cents,
     currency,
     COALESCE(trial_period_days, 0),
     CASE WHEN is_usage_based THEN 'tiered' ELSE NULL END,
     usage_tiers_json,
     is_active,
     1,
     created_date
   FROM legacy_plans;
   ```

4. **Subscriptions** (T044-T048)
   ```sql
   -- Migrate active subscriptions with period alignment
   INSERT INTO subscriptions (id, account_id, plan_id, status, quantity, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at)
   SELECT
     uuid_generate_v4(),
     a.id,
     p.id,
     CASE
       WHEN ls.status = 'active' THEN 'active'
       WHEN ls.status = 'trialing' THEN 'trialing'
       WHEN ls.status = 'canceled' THEN 'cancelled'
       ELSE 'active'
     END,
     ls.quantity,
     ls.current_period_start,
     ls.current_period_end,
     ls.cancel_at_period_end,
     ls.created_date,
     ls.updated_date
   FROM legacy_subscriptions ls
   JOIN accounts a ON a.metadata->>'legacy_id' = ls.customer_id::text
   JOIN plans p ON p.metadata->>'legacy_id' = ls.plan_id::text;
   ```

5. **Historical Invoices** (T055-T064)
   ```sql
   -- Migrate historical invoices (read-only, immutable after PAID)
   INSERT INTO invoices (id, account_id, subscription_id, number, status, amount_due, amount_paid, tax, currency, due_date, paid_at, line_items, metadata, created_at, updated_at)
   SELECT
     uuid_generate_v4(),
     a.id,
     s.id,
     li.invoice_number,
     li.status,
     li.total_amount_cents,
     li.paid_amount_cents,
     li.tax_amount_cents,
     li.currency,
     li.due_date,
     li.paid_date,
     li.line_items_json,
     jsonb_build_object('legacy_id', li.id, 'migrated_at', NOW()),
     li.created_date,
     li.updated_date
   FROM legacy_invoices li
   JOIN accounts a ON a.metadata->>'legacy_id' = li.customer_id::text
   LEFT JOIN subscriptions s ON s.metadata->>'legacy_subscription_id' = li.subscription_id::text;
   ```

6. **Historical Payments** (T067-T076)
   ```sql
   -- Migrate payment history
   INSERT INTO payments (id, invoice_id, amount, currency, status, payment_gateway_transaction_id, payment_method_id, failure_message, idempotency_key, created_at)
   SELECT
     uuid_generate_v4(),
     i.id,
     lp.amount_cents,
     lp.currency,
     lp.status,
     lp.stripe_charge_id,
     pm.id,
     lp.failure_message,
     lp.idempotency_key,
     lp.created_date
   FROM legacy_payments lp
   JOIN invoices i ON i.metadata->>'legacy_id' = lp.invoice_id::text
   LEFT JOIN payment_methods pm ON pm.gateway_payment_method_id = lp.stripe_payment_method_id;
   ```

7. **Usage Records** (T085-T092)
   ```sql
   -- Migrate usage data for current billing period only
   INSERT INTO usage_records (id, subscription_id, metric, quantity, timestamp, idempotency_key, metadata, created_at)
   SELECT
     uuid_generate_v4(),
     s.id,
     lu.metric_name,
     lu.quantity,
     lu.recorded_at,
     lu.idempotency_key,
     jsonb_build_object('legacy_id', lu.id),
     lu.created_date
   FROM legacy_usage_records lu
   JOIN subscriptions s ON s.metadata->>'legacy_subscription_id' = lu.subscription_id::text
   WHERE lu.recorded_at >= DATE_TRUNC('month', NOW());  -- Current billing period only
   ```

8. **Credits** (T100-T106)
   ```sql
   -- Migrate account credits
   INSERT INTO credits (id, account_id, amount, currency, reason, applied_to_invoice_id, created_at)
   SELECT
     uuid_generate_v4(),
     a.id,
     lc.amount_cents,
     lc.currency,
     lc.reason,
     NULL,  -- Will be reapplied during next invoice generation
     lc.created_date
   FROM legacy_credits lc
   JOIN accounts a ON a.metadata->>'legacy_id' = lc.customer_id::text
   WHERE lc.remaining_balance_cents > 0;  -- Only migrate unused credits
   ```

#### Validation Queries

After each migration step, run validation:

```sql
-- Count validation
SELECT
  'accounts' AS entity,
  (SELECT COUNT(*) FROM legacy_customers) AS legacy_count,
  (SELECT COUNT(*) FROM accounts) AS new_count,
  (SELECT COUNT(*) FROM accounts) - (SELECT COUNT(*) FROM legacy_customers) AS difference;

-- Revenue reconciliation
SELECT
  SUM(amount_paid) / 100.0 AS total_revenue_new,
  (SELECT SUM(paid_amount_cents) FROM legacy_invoices WHERE status = 'paid') / 100.0 AS total_revenue_legacy,
  ABS(SUM(amount_paid) - (SELECT SUM(paid_amount_cents) FROM legacy_invoices WHERE status = 'paid')) AS discrepancy_cents
FROM invoices
WHERE status = 'paid';

-- Active subscriptions validation
SELECT
  s.status,
  COUNT(*) AS new_count,
  (SELECT COUNT(*) FROM legacy_subscriptions WHERE status = s.status) AS legacy_count
FROM subscriptions s
GROUP BY s.status;
```

**Rollback Plan**:
- Keep legacy system database available (read-only mode)
- If critical data mismatch detected (>1% revenue discrepancy), abort migration
- Restore from PostgreSQL snapshot (RPO: point-in-time)

---

### Phase 2: Parallel Run (Week 1, Day 4-7)

**Objective**: Run new platform alongside legacy system without customer-facing changes

#### Approach

1. **Read-Only Operation**
   - Deploy new platform in read-only mode
   - All API endpoints return 503 for write operations
   - Only health checks and analytics endpoints active

2. **Background Sync**
   - Set up continuous data sync from legacy → new system
   - Frequency: Every 15 minutes (RPO requirement)
   - Monitor sync lag and data drift

3. **Validation**
   - Compare new platform calculations against legacy
   - Validate invoice generation logic (without sending)
   - Test payment processing in Stripe test mode
   - Verify tax calculations match legacy

4. **Load Testing**
   - Simulate peak load (100 invoices/second)
   - Verify p95 latency <200ms
   - Confirm database query performance <50ms p99
   - Test concurrent usage event ingestion (10K/minute)

**Success Criteria**:
- ✅ <1% calculation discrepancy between systems
- ✅ All performance targets met under load
- ✅ Zero sync failures over 3 days
- ✅ Health checks green 99.9% of time

---

### Phase 3: Shadow Mode (Week 2, Day 1-3)

**Objective**: Process real transactions on both systems for comparison

#### Approach

1. **Dual Write**
   - All writes go to both legacy and new system
   - New system transactions are not committed (rollback after comparison)
   - Log discrepancies for investigation

2. **Comparison Logic**
   ```python
   async def dual_write_compare(operation, data):
       # Execute on legacy system
       legacy_result = await legacy_system.execute(operation, data)

       # Execute on new system
       new_result = await new_platform.execute(operation, data)

       # Compare results
       if not results_match(legacy_result, new_result):
           await log_discrepancy(operation, data, legacy_result, new_result)
           await alert_team("Data discrepancy detected")

       # Rollback new system transaction
       await new_platform.rollback()

       return legacy_result  # Always return legacy result to customer
   ```

3. **Discrepancy Investigation**
   - Track all mismatches by operation type
   - Priority: Payment processing, invoice generation, proration
   - Fix issues in new platform before proceeding

4. **Webhook Preparation**
   - Configure webhook endpoints in Stripe (point to new platform)
   - Test webhook delivery and retry logic
   - Verify signature validation

**Success Criteria**:
- ✅ <0.1% discrepancy rate on financial calculations
- ✅ Zero payment processing errors
- ✅ All identified issues resolved
- ✅ Webhook delivery >99% success rate

---

### Phase 4: Dark Launch (Week 2, Day 4-7)

**Objective**: Route subset of traffic to new platform for real-world validation

#### Approach

1. **Traffic Routing (5% → 20% → 50%)**
   - Use feature flags to route traffic
   - Start with internal test accounts (5%)
   - Expand to low-volume customers (20%)
   - Increase to 50% of traffic by end of phase

2. **Selection Criteria**
   ```python
   def should_use_new_platform(account_id):
       # Internal accounts always use new platform
       if account.is_internal:
           return True

       # Gradually increase percentage
       rollout_percentage = get_rollout_percentage()  # 5% → 50%
       account_hash = hash(account_id) % 100
       return account_hash < rollout_percentage
   ```

3. **Monitoring**
   - Real-time error rate alerts (>0.1% triggers investigation)
   - Revenue reconciliation every hour
   - Customer support ticket monitoring
   - API latency p95/p99 tracking

4. **Rollback Capability**
   - Instant traffic cutover to legacy (via feature flag)
   - Keep legacy system warm and ready
   - Maximum switchover time: 30 seconds

**Success Criteria**:
- ✅ Error rate <0.1% on new platform
- ✅ Zero customer complaints about billing issues
- ✅ Revenue matches legacy system (±0.01%)
- ✅ API latency meets SLO (<200ms p95)

---

### Phase 5: Full Cutover (Week 3, Day 1-2)

**Objective**: Route 100% traffic to new platform and decommission legacy

#### Cutover Plan

**Day 1 Morning (Low Traffic Window)**:

1. **T-60 min**: Freeze legacy system (read-only mode)
2. **T-45 min**: Final data sync from legacy → new
3. **T-30 min**: Validate data integrity (run all validation queries)
4. **T-15 min**: Update DNS/load balancer to point to new platform
5. **T-10 min**: Switch feature flags (100% traffic to new)
6. **T-5 min**: Verify health checks green
7. **T-0**: Monitor first transactions on new platform
8. **T+30 min**: Validate first billing cycle completed successfully
9. **T+60 min**: Revenue reconciliation check
10. **T+120 min**: Declare cutover successful if all metrics green

**Rollback Trigger**:
- Error rate >1% for >5 minutes
- Payment processing failure rate >5%
- Database connection issues
- API latency >500ms p95 for >5 minutes

**Rollback Procedure** (15 minutes):
1. Switch feature flags back to legacy (2 min)
2. Update load balancer to legacy endpoints (3 min)
3. Verify legacy system health (5 min)
4. Sync any new data from new → legacy (5 min)

**Day 1 Afternoon - Day 2**:

- Monitor all systems closely (24/7 coverage)
- Run hourly revenue reconciliation
- Check for customer support tickets
- Verify webhook delivery logs
- Monitor dunning process for overdue accounts

**Success Criteria**:
- ✅ 100% traffic on new platform
- ✅ Error rate <0.1% sustained for 24 hours
- ✅ Zero revenue discrepancies
- ✅ All SLOs met (uptime, latency, throughput)
- ✅ No P0/P1 incidents

---

### Phase 6: Legacy Decommission (Week 3, Day 3-7)

**Objective**: Safely decommission legacy system after validation period

#### Decommission Steps

1. **Data Archival**
   - Export legacy database to long-term storage (S3/Glacier)
   - Retention period: 7 years (compliance requirement)
   - Format: PostgreSQL dump + CSV exports

2. **System Shutdown**
   - Stop legacy application servers
   - Keep database in read-only mode for 30 days (safety period)
   - After 30 days, snapshot and shutdown database

3. **Documentation Update**
   - Update runbooks to remove legacy references
   - Archive legacy system documentation
   - Update incident response procedures

4. **Cost Optimization**
   - Decommission legacy infrastructure
   - Right-size new platform resources based on actual usage
   - Review and optimize database instance sizes

---

## Data Validation Checklist

Run these checks at each phase:

### Financial Integrity

- [ ] Total revenue matches (±$0.01)
  ```sql
  SELECT
    SUM(amount_paid) / 100.0 AS new_platform_revenue,
    (SELECT SUM(paid_amount_cents) FROM legacy_invoices WHERE status = 'paid') / 100.0 AS legacy_revenue
  FROM invoices WHERE status = 'paid';
  ```

- [ ] MRR calculation correct
  ```sql
  SELECT
    SUM(CASE WHEN p.interval = 'month' THEN p.amount ELSE p.amount / 12 END) / 100.0 AS mrr
  FROM subscriptions s
  JOIN plans p ON s.plan_id = p.id
  WHERE s.status = 'active';
  ```

- [ ] Account balances reconcile
  ```sql
  SELECT
    a.id,
    a.email,
    COALESCE(SUM(c.amount), 0) AS total_credits,
    COALESCE(SUM(i.amount_due - i.amount_paid), 0) AS outstanding_balance
  FROM accounts a
  LEFT JOIN credits c ON c.account_id = a.id AND c.applied_to_invoice_id IS NULL
  LEFT JOIN invoices i ON i.account_id = a.id AND i.status IN ('open', 'past_due')
  GROUP BY a.id, a.email
  HAVING COALESCE(SUM(c.amount), 0) + COALESCE(SUM(i.amount_due - i.amount_paid), 0) <> 0;
  ```

### Data Completeness

- [ ] All accounts migrated (zero missing)
- [ ] All active subscriptions migrated
- [ ] All unpaid invoices migrated
- [ ] All payment methods linked correctly
- [ ] All webhook events for past 30 days migrated

### Operational Validation

- [ ] Billing cycle worker running successfully
- [ ] Payment retry worker processing failed payments
- [ ] Dunning process sending notifications
- [ ] Webhooks delivering to customer endpoints
- [ ] Analytics MRR/churn calculations accurate

---

## Rollback Scenarios

### Scenario 1: Data Corruption Detected

**Trigger**: Revenue discrepancy >$1,000 OR >100 customer complaints

**Action**:
1. Immediately switch traffic back to legacy (feature flag)
2. Investigate data corruption root cause
3. Restore new platform database from last good snapshot
4. Re-run migration with fixes
5. Resume from Phase 2 (Parallel Run)

### Scenario 2: Performance Degradation

**Trigger**: API latency >500ms p95 for >10 minutes

**Action**:
1. Check database connection pool exhaustion
2. Scale up database instance (vertical scaling)
3. If not resolved in 15 min, switch to legacy
4. Investigate query performance issues
5. Optimize and retry dark launch

### Scenario 3: Payment Processing Failures

**Trigger**: Payment failure rate >10% (excluding legitimate declines)

**Action**:
1. Immediately switch to legacy for payment processing only
2. Investigate Stripe integration issues
3. Verify webhook signature validation
4. Test payment flows in staging
5. Resume after fix verified

---

## Monitoring & Alerts

### Critical Alerts (PagerDuty - immediate response)

- Revenue discrepancy >$100 in any hour
- Payment processing failure rate >5%
- API error rate >1% for >5 minutes
- Database connection failures
- Health check failures for >1 minute

### Warning Alerts (Slack - review within 1 hour)

- Revenue discrepancy >$10 in any hour
- API latency p95 >200ms for >10 minutes
- Webhook delivery failure rate >5%
- Background worker queue depth >1000
- Sync lag >30 minutes

### Informational Alerts (Email - daily digest)

- Data migration progress updates
- Daily revenue reconciliation report
- Customer support ticket summary
- Performance metrics dashboard

---

## Success Metrics

### Technical Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Uptime** | 99.9% | 30-day rolling window |
| **API Latency (p95)** | <200ms | 5-minute window |
| **Database Queries (p99)** | <50ms | 5-minute window |
| **Error Rate** | <0.1% | 5-minute window |
| **Invoice Generation Rate** | 100/sec | Sustained throughput |
| **Usage Ingestion Rate** | 10K events/min | Peak load |

### Business Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Revenue Accuracy** | 100% (±$0.01) | Daily reconciliation |
| **Customer Complaints** | <10 during migration | Support ticket tracking |
| **Failed Payments (new issues)** | 0 | Stripe error logs |
| **Missed Billing Cycles** | 0 | Cron job monitoring |
| **Data Loss** | 0 records | Count validation |

---

## Team Responsibilities

### Migration Team

- **Lead**: Migration project manager
- **DBAs**: Data migration scripts and validation
- **Backend Engineers**: Platform deployment and monitoring
- **DevOps**: Infrastructure provisioning and scaling
- **QA**: Testing and validation at each phase

### On-Call Coverage

- **Week 1-2**: 24/7 on-call for migration team
- **Week 3**: Business hours coverage + on-call rotation
- **Week 4+**: Standard on-call rotation

---

## Communication Plan

### Internal Stakeholders

- **Daily Standups**: Migration progress and blockers (15 min)
- **Phase Completion Reports**: Email to leadership after each phase
- **Incident Reports**: Immediate Slack notification for any rollback

### External Customers

- **Pre-Migration Notice**: 2 weeks before cutover
  - Subject: "Billing Platform Upgrade - No Action Required"
  - Content: Improved features, zero downtime migration

- **Post-Migration Notice**: 1 week after successful cutover
  - Subject: "Billing Platform Upgrade Complete"
  - Content: New features available, API documentation updated

### Support Team

- **Training Session**: 1 week before cutover (new admin dashboard)
- **FAQ Document**: Common migration questions and answers
- **Escalation Path**: Direct line to migration team during Week 1-3

---

## Appendix A: Migration Scripts

All migration scripts located in: `backend/scripts/migration/`

- `01_migrate_accounts.sql` - Account migration with validation
- `02_migrate_payment_methods.sql` - Payment method migration
- `03_migrate_plans.sql` - Pricing plan migration
- `04_migrate_subscriptions.sql` - Subscription migration
- `05_migrate_invoices.sql` - Historical invoice migration
- `06_migrate_payments.sql` - Payment history migration
- `07_migrate_usage.sql` - Usage record migration
- `08_migrate_credits.sql` - Account credit migration
- `validate_migration.sql` - Comprehensive validation queries
- `rollback_migration.sql` - Emergency rollback procedures

---

## Appendix B: Cutover Checklist

**24 Hours Before**:
- [ ] Notify all stakeholders of cutover time
- [ ] Verify staging environment matches production data
- [ ] Test rollback procedure in staging
- [ ] Prepare runbooks for on-call team
- [ ] Set up war room (Zoom link + Slack channel)

**1 Hour Before**:
- [ ] All hands on deck (migration team)
- [ ] Verify monitoring dashboards working
- [ ] Check PagerDuty escalation policies
- [ ] Confirm Stripe webhook endpoints ready
- [ ] Review rollback trigger criteria

**During Cutover**:
- [ ] Follow cutover plan timeline strictly
- [ ] Log all actions in war room Slack channel
- [ ] Monitor dashboards continuously
- [ ] Document any anomalies immediately

**Post-Cutover (First 24 Hours)**:
- [ ] Hourly revenue reconciliation
- [ ] Check customer support tickets every 2 hours
- [ ] Verify billing cycle jobs running
- [ ] Monitor error logs for new issues
- [ ] Prepare executive summary report

---

## Appendix C: Emergency Contacts

- **Migration Lead**: [on-call phone]
- **Database Admin**: [on-call phone]
- **Platform Lead**: [on-call phone]
- **DevOps Lead**: [on-call phone]
- **Stripe Support**: [emergency contact]

---

**Document Version Control**:
- v1.0 (2025-11-19): Initial migration plan
- Next Review: After Phase 2 completion

**Approval Required From**:
- [ ] CTO
- [ ] VP Engineering
- [ ] Head of Finance
- [ ] Head of Customer Success

---

**End of Migration Plan**
