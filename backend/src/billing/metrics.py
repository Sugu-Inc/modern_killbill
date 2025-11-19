"""Business metrics for Prometheus monitoring."""
from prometheus_client import Counter, Gauge

# Business metrics for monitoring

# Invoice metrics
invoices_generated_total = Counter(
    "invoices_generated_total",
    "Total number of invoices generated",
    labelnames=["currency"],
)

invoices_voided_total = Counter(
    "invoices_voided_total",
    "Total number of invoices voided",
    labelnames=["reason"],
)

# Payment metrics
payments_attempted_total = Counter(
    "payments_attempted_total",
    "Total payment attempts",
    labelnames=["status", "currency"],  # status: success, failed, pending
)

payment_amount_total = Counter(
    "payment_amount_total",
    "Total payment amount in cents",
    labelnames=["status", "currency"],
)

# Subscription metrics
subscriptions_created_total = Counter(
    "subscriptions_created_total",
    "Total subscriptions created",
    labelnames=["plan_interval"],  # month, year
)

subscriptions_cancelled_total = Counter(
    "subscriptions_cancelled_total",
    "Total subscriptions cancelled",
    labelnames=["reason"],
)

subscriptions_active_gauge = Gauge(
    "subscriptions_active",
    "Number of currently active subscriptions",
)

# Revenue metrics
mrr_dollars = Gauge(
    "mrr_dollars",
    "Monthly Recurring Revenue in dollars",
    labelnames=["currency"],
)

arr_dollars = Gauge(
    "arr_dollars",
    "Annual Recurring Revenue in dollars",
    labelnames=["currency"],
)

# Usage metrics
usage_events_total = Counter(
    "usage_events_total",
    "Total usage events received",
    labelnames=["metric_name"],
)

usage_events_deduplicated_total = Counter(
    "usage_events_deduplicated_total",
    "Total duplicate usage events rejected",
    labelnames=["metric_name"],
)

# Credit metrics
credits_applied_total = Counter(
    "credits_applied_total",
    "Total credits applied to invoices",
    labelnames=["currency"],
)

credits_amount_total = Counter(
    "credits_amount_total",
    "Total credit amount in cents",
    labelnames=["currency"],
)

# Account metrics
accounts_created_total = Counter(
    "accounts_created_total",
    "Total accounts created",
)

accounts_overdue_gauge = Gauge(
    "accounts_overdue",
    "Number of accounts with overdue invoices",
)

accounts_blocked_gauge = Gauge(
    "accounts_blocked",
    "Number of blocked accounts",
)

# Webhook metrics
webhooks_sent_total = Counter(
    "webhooks_sent_total",
    "Total webhook events sent",
    labelnames=["event_type", "status"],  # status: delivered, failed, pending
)

webhooks_retry_total = Counter(
    "webhooks_retry_total",
    "Total webhook retry attempts",
    labelnames=["event_type"],
)
