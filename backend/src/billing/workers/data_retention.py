"""Data retention worker for GDPR compliance and data cleanup.

Handles:
- Deleting audit logs older than 3 years
- Purging soft-deleted accounts after 30 days
- Removing orphaned data
"""
import structlog
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.audit_log import AuditLog
from billing.models.account import Account
from billing.database import get_async_session

logger = structlog.get_logger(__name__)


class DataRetentionService:
    """Service for managing data retention policies."""

    def __init__(self, db: AsyncSession):
        """Initialize data retention service."""
        self.db = db

    async def delete_old_audit_logs(self, retention_days: int = 1095) -> int:
        """
        Delete audit logs older than retention period.

        Default retention: 3 years (1095 days) for compliance.

        Args:
            retention_days: Number of days to retain audit logs

        Returns:
            Number of audit logs deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        logger.info(
            "deleting_old_audit_logs",
            cutoff_date=cutoff_date.isoformat(),
            retention_days=retention_days,
        )

        # Delete in batches to avoid long-running transactions
        batch_size = 1000
        total_deleted = 0

        while True:
            # Find IDs of old audit logs
            query = (
                select(AuditLog.id)
                .where(AuditLog.created_at < cutoff_date)
                .limit(batch_size)
            )

            result = await self.db.execute(query)
            ids_to_delete = [row[0] for row in result.fetchall()]

            if not ids_to_delete:
                break

            # Delete batch
            delete_stmt = delete(AuditLog).where(AuditLog.id.in_(ids_to_delete))
            await self.db.execute(delete_stmt)
            await self.db.commit()

            batch_deleted = len(ids_to_delete)
            total_deleted += batch_deleted

            logger.info(
                "audit_logs_batch_deleted",
                batch_size=batch_deleted,
                total_deleted=total_deleted,
            )

        logger.info(
            "audit_logs_deletion_complete",
            total_deleted=total_deleted,
            cutoff_date=cutoff_date.isoformat(),
        )

        return total_deleted

    async def purge_soft_deleted_accounts(self, grace_period_days: int = 30) -> int:
        """
        Permanently delete accounts that were soft-deleted over 30 days ago.

        This gives a grace period for account recovery before permanent deletion.

        Args:
            grace_period_days: Days to wait before permanent deletion

        Returns:
            Number of accounts permanently deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=grace_period_days)

        logger.info(
            "purging_soft_deleted_accounts",
            cutoff_date=cutoff_date.isoformat(),
            grace_period_days=grace_period_days,
        )

        # Find soft-deleted accounts past grace period
        query = select(Account).where(
            Account.deleted_at.isnot(None),
            Account.deleted_at < cutoff_date.isoformat(),
        )

        result = await self.db.execute(query)
        accounts_to_delete = result.scalars().all()

        if not accounts_to_delete:
            logger.info("no_accounts_to_purge")
            return 0

        # Delete accounts (CASCADE will handle related records)
        delete_count = 0
        for account in accounts_to_delete:
            logger.info(
                "permanently_deleting_account",
                account_id=str(account.id),
                email=account.email,
                deleted_at=account.deleted_at,
            )

            # Hard delete
            await self.db.delete(account)
            delete_count += 1

        await self.db.commit()

        logger.info(
            "account_purge_complete",
            accounts_deleted=delete_count,
            cutoff_date=cutoff_date.isoformat(),
        )

        return delete_count

    async def run_retention_policy(
        self,
        audit_log_retention_days: int = 1095,
        account_grace_period_days: int = 30,
    ) -> dict:
        """
        Run all data retention policies.

        Args:
            audit_log_retention_days: Days to retain audit logs (default: 3 years)
            account_grace_period_days: Grace period before purging accounts (default: 30 days)

        Returns:
            Dictionary with deletion counts
        """
        logger.info("starting_data_retention_job")

        try:
            # Delete old audit logs
            audit_logs_deleted = await self.delete_old_audit_logs(audit_log_retention_days)

            # Purge soft-deleted accounts
            accounts_deleted = await self.purge_soft_deleted_accounts(account_grace_period_days)

            result = {
                "audit_logs_deleted": audit_logs_deleted,
                "accounts_purged": accounts_deleted,
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(
                "data_retention_job_complete",
                audit_logs_deleted=audit_logs_deleted,
                accounts_purged=accounts_deleted,
            )

            return result

        except Exception as e:
            logger.error(
                "data_retention_job_failed",
                error=str(e),
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }


async def run_data_retention_job(
    audit_log_retention_days: int = 1095,
    account_grace_period_days: int = 30,
) -> dict:
    """
    ARQ worker task for data retention.

    This function is called by the ARQ background worker scheduler.

    Args:
        audit_log_retention_days: Days to retain audit logs
        account_grace_period_days: Grace period for soft-deleted accounts

    Returns:
        Dictionary with job results
    """
    logger.info(
        "data_retention_worker_started",
        audit_log_retention_days=audit_log_retention_days,
        account_grace_period_days=account_grace_period_days,
    )

    async with get_async_session() as db:
        service = DataRetentionService(db)
        result = await service.run_retention_policy(
            audit_log_retention_days=audit_log_retention_days,
            account_grace_period_days=account_grace_period_days,
        )

    return result
