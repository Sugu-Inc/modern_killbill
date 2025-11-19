"""Pydantic schemas for AnalyticsSnapshot model."""
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class AnalyticsSnapshotBase(BaseModel):
    """Base analytics snapshot schema with common fields."""

    metric_name: str = Field(..., min_length=1, description="Metric name (mrr, churn_rate, ltv, etc.)")
    value: int = Field(..., description="Metric value (cents for revenue, basis points for percentages)")
    period: date = Field(..., description="Date of snapshot")
    currency: str | None = Field(default=None, min_length=3, max_length=3, description="Currency for revenue metrics")
    extra_metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class AnalyticsSnapshotCreate(AnalyticsSnapshotBase):
    """Schema for creating a new analytics snapshot."""

    pass


class AnalyticsSnapshot(AnalyticsSnapshotBase):
    """Schema for returning analytics snapshot data."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalyticsSnapshotList(BaseModel):
    """Schema for paginated analytics snapshot list."""

    items: list[AnalyticsSnapshot]
    total: int
    page: int
    page_size: int


class MetricTimeSeries(BaseModel):
    """Schema for time series data of a metric."""

    metric_name: str
    currency: str | None
    data_points: list[dict[str, Any]]  # [{period: "2025-01-01", value: 100000}, ...]


class AnalyticsDashboard(BaseModel):
    """Schema for analytics dashboard data."""

    mrr: int | None
    arr: int | None
    active_subscriptions: int
    churn_rate: int | None  # Basis points
    ltv: int | None
    period: date
    currency: str
