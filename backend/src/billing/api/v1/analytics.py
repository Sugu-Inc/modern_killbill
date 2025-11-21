"""
Analytics API endpoints for SaaS metrics.

Provides endpoints for:
- GET /v1/analytics/mrr - Monthly Recurring Revenue
- GET /v1/analytics/churn - Churn rate metrics
- GET /v1/analytics/ltv - Customer Lifetime Value

Implements FR-119: Expose analytics endpoints for MRR, churn, and LTV
"""

from datetime import date, timedelta
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db
from billing.services.analytics_service import AnalyticsService
from billing.models.analytics_snapshot import MetricName
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


# Response Models

class MRRResponse(BaseModel):
    """MRR (Monthly Recurring Revenue) response."""

    total_mrr: float = Field(..., description="Total MRR in dollars")
    new_mrr: float = Field(..., description="MRR from new customers")
    expansion_mrr: float = Field(..., description="MRR from upgrades")
    contraction_mrr: float = Field(..., description="MRR lost from downgrades")
    churned_mrr: float = Field(..., description="MRR lost from cancellations")
    breakdown_by_plan: dict = Field(..., description="MRR breakdown by plan name")
    period: str = Field(..., description="Date for this MRR snapshot (YYYY-MM-DD)")
    calculated_at: str = Field(..., description="Calculation timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "total_mrr": 125000.00,
                "new_mrr": 15000.00,
                "expansion_mrr": 5000.00,
                "contraction_mrr": 2000.00,
                "churned_mrr": 3000.00,
                "breakdown_by_plan": {
                    "Starter": 25000.00,
                    "Pro": 75000.00,
                    "Enterprise": 25000.00
                },
                "period": "2025-11-21",
                "calculated_at": "2025-11-21T08:00:00Z"
            }
        }


class MRRHistoryItem(BaseModel):
    """Historical MRR data point."""

    period: str = Field(..., description="Date (YYYY-MM-DD)")
    value: float = Field(..., description="MRR value in dollars")


class MRRHistoryResponse(BaseModel):
    """MRR history response with trend data."""

    current_mrr: float
    history: list[MRRHistoryItem]
    growth_rate: float = Field(..., description="MRR growth rate (%)")
    trend: str = Field(..., description="Trend: increasing, decreasing, or stable")


class ChurnResponse(BaseModel):
    """Churn rate response."""

    churn_rate: float = Field(..., description="Total churn rate (%)")
    voluntary_churn: float = Field(..., description="Voluntary churn rate (%)")
    involuntary_churn: float = Field(..., description="Involuntary churn rate (payment failures) (%)")
    customers_at_start: int = Field(..., description="Customers at period start")
    customers_lost: int = Field(..., description="Customers lost during period")
    customers_at_end: int = Field(..., description="Customers at period end")
    period_start: str = Field(..., description="Period start date (YYYY-MM-DD)")
    period_end: str = Field(..., description="Period end date (YYYY-MM-DD)")
    calculated_at: str = Field(..., description="Calculation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "churn_rate": 2.5,
                "voluntary_churn": 1.75,
                "involuntary_churn": 0.75,
                "customers_at_start": 1000,
                "customers_lost": 25,
                "customers_at_end": 1050,
                "period_start": "2025-10-21",
                "period_end": "2025-11-21",
                "calculated_at": "2025-11-21T08:00:00Z"
            }
        }


class LTVResponse(BaseModel):
    """Customer Lifetime Value response."""

    ltv: float = Field(..., description="Customer Lifetime Value in dollars")
    arpu: float = Field(..., description="Average Revenue Per User (monthly)")
    average_lifetime_months: float = Field(..., description="Average customer lifetime in months")
    monthly_churn_rate: float = Field(..., description="Monthly churn rate (%)")
    active_customers: int = Field(..., description="Current active customers")
    calculated_at: str = Field(..., description="Calculation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "ltv": 4500.00,
                "arpu": 125.00,
                "average_lifetime_months": 36.0,
                "monthly_churn_rate": 2.78,
                "active_customers": 1050,
                "calculated_at": "2025-11-21T08:00:00Z"
            }
        }


# Endpoints

@router.get(
    "/analytics/mrr",
    response_model=MRRResponse,
    summary="Get Monthly Recurring Revenue (MRR)",
    description="""
    Calculate current Monthly Recurring Revenue and breakdown.

    **MRR Components:**
    - **Total MRR**: Sum of all active recurring subscriptions (normalized to monthly)
    - **New MRR**: Revenue from new customers in the last 30 days
    - **Expansion MRR**: Additional revenue from upgrades
    - **Contraction MRR**: Lost revenue from downgrades
    - **Churned MRR**: Lost revenue from cancellations

    **Use Cases:**
    - Track revenue growth over time
    - Identify revenue drivers (new vs expansion)
    - Monitor churn impact on revenue
    - Compare MRR across plans

    **Performance:** Cached for 1 hour, updated hourly by background worker.
    """
)
async def get_mrr(
    as_of_date: Optional[str] = Query(
        None,
        description="Calculate MRR as of this date (YYYY-MM-DD). Defaults to today."
    ),
    db: AsyncSession = Depends(get_db)
) -> MRRResponse:
    """
    Get Monthly Recurring Revenue metrics.

    Args:
        as_of_date: Optional date for historical MRR (format: YYYY-MM-DD)
        db: Database session

    Returns:
        MRR metrics and breakdown

    Raises:
        HTTPException 400: If date format is invalid
        HTTPException 500: If calculation fails
    """
    try:
        # Parse date if provided
        calculation_date = None
        if as_of_date:
            try:
                calculation_date = date.fromisoformat(as_of_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid date format: {as_of_date}. Use YYYY-MM-DD."
                )

        # Calculate MRR
        analytics_service = AnalyticsService(db)
        mrr_data = await analytics_service.calculate_mrr(as_of_date=calculation_date)

        # Convert Decimal to float for JSON serialization
        response = MRRResponse(
            total_mrr=float(mrr_data["total_mrr"]),
            new_mrr=float(mrr_data["new_mrr"]),
            expansion_mrr=float(mrr_data["expansion_mrr"]),
            contraction_mrr=float(mrr_data["contraction_mrr"]),
            churned_mrr=float(mrr_data["churned_mrr"]),
            breakdown_by_plan={
                plan: float(amount)
                for plan, amount in mrr_data["breakdown_by_plan"].items()
            },
            period=mrr_data["period"],
            calculated_at=mrr_data["calculated_at"]
        )

        logger.info(
            "mrr_endpoint_called",
            total_mrr=response.total_mrr,
            as_of_date=as_of_date
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("mrr_calculation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate MRR"
        )


@router.get(
    "/analytics/mrr/history",
    response_model=MRRHistoryResponse,
    summary="Get MRR History",
    description="""
    Get historical MRR data for trend analysis.

    Returns MRR snapshots for the specified number of days,
    along with growth rate and trend analysis.
    """
)
async def get_mrr_history(
    days: int = Query(
        30,
        ge=7,
        le=365,
        description="Number of days of history (7-365)"
    ),
    db: AsyncSession = Depends(get_db)
) -> MRRHistoryResponse:
    """
    Get MRR historical data and trends.

    Args:
        days: Number of days of history to retrieve
        db: Database session

    Returns:
        MRR history with trend analysis
    """
    try:
        analytics_service = AnalyticsService(db)

        # Get historical snapshots
        snapshots = await analytics_service.get_metric_history(
            metric_name=MetricName.MRR,
            days=days
        )

        if not snapshots:
            # No historical data, calculate current
            current_mrr_data = await analytics_service.calculate_mrr()
            current_mrr = float(current_mrr_data["total_mrr"])
            history = []
            growth_rate = 0.0
            trend = "stable"
        else:
            # Build history list
            history = [
                MRRHistoryItem(
                    period=snapshot.period.isoformat(),
                    value=float(snapshot.value)
                )
                for snapshot in reversed(snapshots)  # Oldest to newest
            ]

            current_mrr = float(snapshots[0].value)  # Most recent

            # Calculate growth rate
            if len(snapshots) > 1:
                oldest_mrr = float(snapshots[-1].value)
                if oldest_mrr > 0:
                    growth_rate = ((current_mrr - oldest_mrr) / oldest_mrr) * 100
                else:
                    growth_rate = 0.0

                # Determine trend
                if growth_rate > 5:
                    trend = "increasing"
                elif growth_rate < -5:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                growth_rate = 0.0
                trend = "stable"

        return MRRHistoryResponse(
            current_mrr=current_mrr,
            history=history,
            growth_rate=round(growth_rate, 2),
            trend=trend
        )

    except Exception as e:
        logger.exception("mrr_history_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve MRR history"
        )


@router.get(
    "/analytics/churn",
    response_model=ChurnResponse,
    summary="Get Churn Rate",
    description="""
    Calculate customer churn rate for a period.

    **Churn Rate** = (Customers Lost / Customers at Start) × 100

    **Types:**
    - **Voluntary Churn**: Customer-initiated cancellations
    - **Involuntary Churn**: Payment failures, account issues

    **Use Cases:**
    - Track customer retention
    - Identify churn drivers
    - Measure effectiveness of retention efforts
    - Compare churn across cohorts

    **Default Period:** Last 30 days
    """
)
async def get_churn(
    period_start: Optional[str] = Query(
        None,
        description="Period start date (YYYY-MM-DD). Defaults to 30 days ago."
    ),
    period_end: Optional[str] = Query(
        None,
        description="Period end date (YYYY-MM-DD). Defaults to today."
    ),
    db: AsyncSession = Depends(get_db)
) -> ChurnResponse:
    """
    Get customer churn rate metrics.

    Args:
        period_start: Optional start date (format: YYYY-MM-DD)
        period_end: Optional end date (format: YYYY-MM-DD)
        db: Database session

    Returns:
        Churn rate metrics

    Raises:
        HTTPException 400: If date format is invalid
        HTTPException 500: If calculation fails
    """
    try:
        # Parse dates if provided
        start_date = None
        end_date = None

        if period_start:
            try:
                start_date = date.fromisoformat(period_start)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid start date format: {period_start}. Use YYYY-MM-DD."
                )

        if period_end:
            try:
                end_date = date.fromisoformat(period_end)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid end date format: {period_end}. Use YYYY-MM-DD."
                )

        # Calculate churn
        analytics_service = AnalyticsService(db)
        churn_data = await analytics_service.calculate_churn_rate(
            period_start=start_date,
            period_end=end_date
        )

        logger.info(
            "churn_endpoint_called",
            churn_rate=churn_data["churn_rate"],
            period_start=churn_data["period_start"],
            period_end=churn_data["period_end"]
        )

        return ChurnResponse(**churn_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("churn_calculation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate churn rate"
        )


@router.get(
    "/analytics/ltv",
    response_model=LTVResponse,
    summary="Get Customer Lifetime Value (LTV)",
    description="""
    Calculate Customer Lifetime Value metrics.

    **LTV** = ARPU × Average Customer Lifetime (months)
    **Average Lifetime** = 1 / Monthly Churn Rate

    **Components:**
    - **LTV**: Total expected revenue per customer
    - **ARPU**: Average Revenue Per User (monthly)
    - **Average Lifetime**: Expected customer lifespan in months
    - **Churn Rate**: Monthly customer churn percentage

    **Use Cases:**
    - Determine customer acquisition budget (LTV:CAC ratio)
    - Identify high-value customer segments
    - Optimize pricing strategy
    - Forecast long-term revenue

    **Benchmark:** LTV:CAC ratio should be > 3:1 for healthy SaaS
    """
)
async def get_ltv(
    db: AsyncSession = Depends(get_db)
) -> LTVResponse:
    """
    Get Customer Lifetime Value metrics.

    Args:
        db: Database session

    Returns:
        LTV metrics including ARPU and average lifetime

    Raises:
        HTTPException 500: If calculation fails
    """
    try:
        analytics_service = AnalyticsService(db)
        ltv_data = await analytics_service.calculate_ltv()

        # Convert Decimal to float
        response = LTVResponse(
            ltv=float(ltv_data["ltv"]),
            arpu=float(ltv_data["arpu"]),
            average_lifetime_months=ltv_data["average_lifetime_months"],
            monthly_churn_rate=ltv_data["monthly_churn_rate"],
            active_customers=ltv_data["active_customers"],
            calculated_at=ltv_data["calculated_at"]
        )

        logger.info(
            "ltv_endpoint_called",
            ltv=response.ltv,
            arpu=response.arpu
        )

        return response

    except Exception as e:
        logger.exception("ltv_calculation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate LTV"
        )
