"""Analytics snapshot model for pre-calculated metrics."""
from datetime import date
from sqlalchemy import Column, String, Integer, Date
from sqlalchemy.dialects.postgresql import JSONB

from billing.models.base import Base


class AnalyticsSnapshot(Base):
    """
    Pre-calculated analytics metrics (MRR, churn, LTV).

    Updated by background worker every hour.
    """

    __tablename__ = "analytics_snapshots"

    metric_name = Column(String, nullable=False, index=True)  # mrr, churn_rate, ltv, etc.
    value = Column(Integer, nullable=False)  # Metric value (cents for revenue, basis points for percentages)
    period = Column(Date, nullable=False, default=date.today, index=True)  # Date of snapshot
    currency = Column(String(3), nullable=True)  # For revenue metrics
    extra_metadata = Column(JSONB, nullable=False, default=dict)  # Additional context

    def __repr__(self) -> str:
        """String representation."""
        return f"<AnalyticsSnapshot(metric={self.metric_name}, value={self.value}, period={self.period})>"
