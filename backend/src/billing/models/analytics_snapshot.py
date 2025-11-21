"""
Analytics snapshot model for pre-calculated SaaS metrics.

Stores hourly snapshots of key metrics:
- MRR (Monthly Recurring Revenue)
- Churn Rate (voluntary and involuntary)
- LTV (Lifetime Value)
- Usage trends by plan and customer segment

Implements FR-117 to FR-121 (Analytics & Reporting requirements).
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB

from billing.models.base import Base


class AnalyticsSnapshot(Base):
    """
    Pre-calculated analytics metrics snapshot.

    Stores point-in-time metrics calculated by background workers.
    Updated hourly via analytics worker (FR-117).
    """

    __tablename__ = "analytics_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Metric identification
    metric_name = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Metric name: mrr, churn_rate, ltv, usage_trend"
    )

    # Metric value (decimal for financial precision)
    value = Column(
        Numeric(precision=15, scale=2),
        nullable=False,
        comment="Metric value (e.g., $12,345.67 for MRR)"
    )

    # Time period for this snapshot
    period = Column(
        Date,
        nullable=False,
        index=True,
        comment="Date for this metric snapshot"
    )

    # Additional metric metadata
    metadata = Column(
        JSONB,
        nullable=True,
        comment="Additional metric details (breakdown by plan, segment, etc.)"
    )

    # Audit fields
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Snapshot calculation timestamp"
    )

    # Composite index for efficient queries
    __table_args__ = (
        Index(
            'ix_analytics_snapshots_metric_period',
            'metric_name',
            'period',
            unique=True  # One snapshot per metric per period
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AnalyticsSnapshot("
            f"metric={self.metric_name}, "
            f"value={self.value}, "
            f"period={self.period}"
            f")>"
        )


# Metric name constants
class MetricName:
    """Constants for analytics metric names."""

    MRR = "mrr"
    CHURN_RATE = "churn_rate"
    LTV = "ltv"
    USAGE_TREND = "usage_trend"
    ARR = "arr"
    ARPU = "arpu"
    NEW_MRR = "new_mrr"
    EXPANSION_MRR = "expansion_mrr"
    CONTRACTION_MRR = "contraction_mrr"
    CHURNED_MRR = "churned_mrr"
