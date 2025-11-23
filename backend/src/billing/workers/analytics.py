"""
Background worker for analytics calculation.

Updates analytics snapshots hourly for:
- MRR (Monthly Recurring Revenue)
- Churn Rate
- LTV (Customer Lifetime Value)
- Usage Trends

Implements FR-117: Calculate MRR updated hourly
Schedule: Runs every hour via ARQ worker

Usage (with ARQ):
    arq billing.workers.analytics.WorkerSettings
"""

from datetime import date, datetime
from decimal import Decimal
import structlog

from billing.database import get_async_session
from billing.services.analytics_service import AnalyticsService
from billing.models.analytics_snapshot import MetricName

logger = structlog.get_logger(__name__)


async def calculate_and_store_mrr(ctx: dict) -> dict:
    """
    Calculate MRR and store snapshot.

    ARQ worker task that runs hourly to update MRR snapshot.

    Args:
        ctx: ARQ context (contains job info)

    Returns:
        Dict with calculation results
    """
    logger.info("analytics_worker_started", metric="mrr")

    try:
        async with get_async_session() as db:
            analytics_service = AnalyticsService(db)

            # Calculate current MRR
            mrr_data = await analytics_service.calculate_mrr()

            # Store snapshot
            snapshot = await analytics_service.save_snapshot(
                metric_name=MetricName.MRR,
                value=mrr_data["total_mrr"],
                period=date.today(),
                metadata={
                    "new_mrr": float(mrr_data["new_mrr"]),
                    "expansion_mrr": float(mrr_data["expansion_mrr"]),
                    "contraction_mrr": float(mrr_data["contraction_mrr"]),
                    "churned_mrr": float(mrr_data["churned_mrr"]),
                    "breakdown_by_plan": {
                        plan: float(amount)
                        for plan, amount in mrr_data["breakdown_by_plan"].items()
                    }
                }
            )

            # Also store component MRR metrics
            await analytics_service.save_snapshot(
                metric_name=MetricName.NEW_MRR,
                value=mrr_data["new_mrr"],
                period=date.today()
            )

            await analytics_service.save_snapshot(
                metric_name=MetricName.EXPANSION_MRR,
                value=mrr_data["expansion_mrr"],
                period=date.today()
            )

            await analytics_service.save_snapshot(
                metric_name=MetricName.CONTRACTION_MRR,
                value=mrr_data["contraction_mrr"],
                period=date.today()
            )

            await analytics_service.save_snapshot(
                metric_name=MetricName.CHURNED_MRR,
                value=mrr_data["churned_mrr"],
                period=date.today()
            )

            logger.info(
                "mrr_calculation_completed",
                total_mrr=float(mrr_data["total_mrr"]),
                snapshot_id=snapshot.id
            )

            return {
                "metric": "mrr",
                "value": float(mrr_data["total_mrr"]),
                "snapshot_id": snapshot.id,
                "status": "success"
            }

    except Exception as e:
        logger.exception("mrr_calculation_failed", error=str(e))
        return {
            "metric": "mrr",
            "status": "failed",
            "error": str(e)
        }


async def calculate_and_store_churn(ctx: dict) -> dict:
    """
    Calculate churn rate and store snapshot.

    ARQ worker task that runs daily to update churn rate.

    Args:
        ctx: ARQ context

    Returns:
        Dict with calculation results
    """
    logger.info("analytics_worker_started", metric="churn_rate")

    try:
        async with get_async_session() as db:
            analytics_service = AnalyticsService(db)

            # Calculate churn rate (last 30 days)
            churn_data = await analytics_service.calculate_churn_rate()

            # Store snapshot
            snapshot = await analytics_service.save_snapshot(
                metric_name=MetricName.CHURN_RATE,
                value=Decimal(str(churn_data["churn_rate"])),
                period=date.today(),
                metadata={
                    "voluntary_churn": churn_data["voluntary_churn"],
                    "involuntary_churn": churn_data["involuntary_churn"],
                    "customers_at_start": churn_data["customers_at_start"],
                    "customers_lost": churn_data["customers_lost"],
                    "customers_at_end": churn_data["customers_at_end"],
                    "period_start": churn_data["period_start"],
                    "period_end": churn_data["period_end"]
                }
            )

            logger.info(
                "churn_calculation_completed",
                churn_rate=churn_data["churn_rate"],
                snapshot_id=snapshot.id
            )

            return {
                "metric": "churn_rate",
                "value": churn_data["churn_rate"],
                "snapshot_id": snapshot.id,
                "status": "success"
            }

    except Exception as e:
        logger.exception("churn_calculation_failed", error=str(e))
        return {
            "metric": "churn_rate",
            "status": "failed",
            "error": str(e)
        }


async def calculate_and_store_ltv(ctx: dict) -> dict:
    """
    Calculate LTV and store snapshot.

    ARQ worker task that runs daily to update LTV.

    Args:
        ctx: ARQ context

    Returns:
        Dict with calculation results
    """
    logger.info("analytics_worker_started", metric="ltv")

    try:
        async with get_async_session() as db:
            analytics_service = AnalyticsService(db)

            # Calculate LTV
            ltv_data = await analytics_service.calculate_ltv()

            # Store snapshot
            snapshot = await analytics_service.save_snapshot(
                metric_name=MetricName.LTV,
                value=ltv_data["ltv"],
                period=date.today(),
                metadata={
                    "arpu": float(ltv_data["arpu"]),
                    "average_lifetime_months": ltv_data["average_lifetime_months"],
                    "monthly_churn_rate": ltv_data["monthly_churn_rate"],
                    "active_customers": ltv_data["active_customers"]
                }
            )

            # Also store ARPU separately
            await analytics_service.save_snapshot(
                metric_name=MetricName.ARPU,
                value=ltv_data["arpu"],
                period=date.today()
            )

            logger.info(
                "ltv_calculation_completed",
                ltv=float(ltv_data["ltv"]),
                snapshot_id=snapshot.id
            )

            return {
                "metric": "ltv",
                "value": float(ltv_data["ltv"]),
                "snapshot_id": snapshot.id,
                "status": "success"
            }

    except Exception as e:
        logger.exception("ltv_calculation_failed", error=str(e))
        return {
            "metric": "ltv",
            "status": "failed",
            "error": str(e)
        }


async def calculate_all_analytics(ctx: dict) -> dict:
    """
    Calculate all analytics metrics in one job.

    Convenience function to run all analytics calculations.
    Useful for manual triggering or initial setup.

    Args:
        ctx: ARQ context

    Returns:
        Dict with results for all metrics
    """
    logger.info("calculating_all_analytics")

    results = {
        "started_at": datetime.utcnow().isoformat(),
        "metrics": {}
    }

    # Calculate MRR
    mrr_result = await calculate_and_store_mrr(ctx)
    results["metrics"]["mrr"] = mrr_result

    # Calculate Churn
    churn_result = await calculate_and_store_churn(ctx)
    results["metrics"]["churn"] = churn_result

    # Calculate LTV
    ltv_result = await calculate_and_store_ltv(ctx)
    results["metrics"]["ltv"] = ltv_result

    results["completed_at"] = datetime.utcnow().isoformat()

    # Count successes and failures
    successes = sum(1 for r in results["metrics"].values() if r["status"] == "success")
    failures = sum(1 for r in results["metrics"].values() if r["status"] == "failed")

    results["summary"] = {
        "total_metrics": 3,
        "successful": successes,
        "failed": failures
    }

    logger.info(
        "all_analytics_completed",
        successful=successes,
        failed=failures
    )

    return results


# ARQ Worker Configuration
# This configuration would be used by ARQ to schedule the worker

class WorkerSettings:
    """
    ARQ worker settings for analytics calculation.

    Schedule:
    - MRR: Every hour
    - Churn: Daily at 02:00 UTC
    - LTV: Daily at 03:00 UTC
    - All metrics: Can be triggered manually

    Usage:
        arq billing.workers.analytics.WorkerSettings
    """

    functions = [
        calculate_and_store_mrr,
        calculate_and_store_churn,
        calculate_and_store_ltv,
        calculate_all_analytics,
    ]

    # Cron jobs (if supported by ARQ version)
    cron_jobs = [
        # Calculate MRR every hour
        {
            "function": calculate_and_store_mrr,
            "cron": "0 * * * *",  # Every hour at minute 0
            "timeout": 600,  # 10 minutes timeout
        },
        # Calculate Churn daily at 02:00 UTC
        {
            "function": calculate_and_store_churn,
            "cron": "0 2 * * *",  # Daily at 02:00
            "timeout": 600,
        },
        # Calculate LTV daily at 03:00 UTC
        {
            "function": calculate_and_store_ltv,
            "cron": "0 3 * * *",  # Daily at 03:00
            "timeout": 600,
        },
    ]

    # Redis connection for ARQ
    redis_settings = {
        "host": "localhost",  # Override with environment variable
        "port": 6379,
        "database": 0,
    }

    # Job retention
    keep_result = 86400  # Keep results for 24 hours

    # Worker configuration
    max_jobs = 10
    job_timeout = 600  # 10 minutes default timeout


# Manual trigger function (useful for CLI or API endpoint)
async def trigger_analytics_update() -> dict:
    """
    Manually trigger analytics update.

    Can be called from CLI or management endpoint.

    Returns:
        Dict with update results
    """
    logger.info("manual_analytics_trigger")

    # In a real implementation, this would enqueue the job to ARQ
    # For now, run directly
    ctx = {"job_id": f"manual_{datetime.utcnow().isoformat()}"}
    results = await calculate_all_analytics(ctx)

    return results


if __name__ == "__main__":
    """
    Run analytics worker manually for testing.

    Usage:
        python -m billing.workers.analytics
    """
    import asyncio

    async def main():
        print("Running analytics calculations...")
        ctx = {"job_id": "test_run"}
        results = await calculate_all_analytics(ctx)

        print("\n" + "="*60)
        print("Analytics Calculation Results")
        print("="*60)

        for metric, result in results["metrics"].items():
            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"\n{status_icon} {metric.upper()}")

            if result["status"] == "success":
                print(f"   Value: {result['value']}")
                print(f"   Snapshot ID: {result['snapshot_id']}")
            else:
                print(f"   Error: {result.get('error', 'Unknown error')}")

        print("\n" + "="*60)
        print(f"Summary: {results['summary']['successful']}/{results['summary']['total_metrics']} successful")
        print("="*60 + "\n")

    asyncio.run(main())
