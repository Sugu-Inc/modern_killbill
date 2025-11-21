"""Audit logging decorator for tracking all changes.

Provides decorators to automatically log create/update/delete operations
with user context and change tracking for compliance.
"""
from functools import wraps
from typing import Any, Callable, Optional
from uuid import UUID, uuid4
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.audit_log import AuditLog

logger = structlog.get_logger(__name__)


async def log_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: UUID,
    action: str,
    user_id: Optional[str] = None,
    changes: Optional[dict] = None,
    request_id: Optional[str] = None,
) -> None:
    """
    Log an audit entry.

    Args:
        db: Database session
        entity_type: Type of entity (account, subscription, invoice, etc.)
        entity_id: Entity UUID
        action: Action performed (create, update, delete)
        user_id: User who performed the action
        changes: Dictionary of changes {field: {old: X, new: Y}}
        request_id: Request correlation ID
    """
    audit_log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        changes=changes or {},
        request_id=request_id or str(uuid4()),
    )

    db.add(audit_log)
    await db.flush()

    logger.info(
        "audit_log_created",
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        user_id=user_id,
        change_count=len(changes) if changes else 0,
    )


def audit_create(entity_type: str):
    """
    Decorator to audit create operations.

    Usage:
        @audit_create("account")
        async def create_account(self, account_data: AccountCreate, current_user: dict):
            account = Account(...)
            self.db.add(account)
            await self.db.flush()
            return account

    Args:
        entity_type: Type of entity being created
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Call the original function
            result = await func(self, *args, **kwargs)

            # Extract current_user from kwargs if available
            current_user = kwargs.get("current_user", {})
            user_id = current_user.get("sub") if current_user else None
            request_id = kwargs.get("request_id")

            # Log the create operation
            if hasattr(result, "id"):
                try:
                    await log_audit(
                        db=self.db,
                        entity_type=entity_type,
                        entity_id=result.id,
                        action="create",
                        user_id=user_id,
                        changes={},  # No changes for create, just new entity
                        request_id=request_id,
                    )
                except Exception as e:
                    logger.warning(
                        "audit_log_failed",
                        entity_type=entity_type,
                        action="create",
                        error=str(e),
                    )

            return result

        return wrapper
    return decorator


def audit_update(entity_type: str):
    """
    Decorator to audit update operations.

    Usage:
        @audit_update("subscription")
        async def update_subscription(self, subscription_id: UUID, updates: dict, current_user: dict):
            subscription = await self.get_subscription(subscription_id)
            old_values = {k: getattr(subscription, k) for k in updates.keys()}
            for k, v in updates.items():
                setattr(subscription, k, v)
            return subscription, old_values

    Args:
        entity_type: Type of entity being updated
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Call the original function
            result = await func(self, *args, **kwargs)

            # Extract result and old values
            if isinstance(result, tuple) and len(result) == 2:
                entity, old_values = result
            else:
                entity = result
                old_values = {}

            # Extract current_user from kwargs
            current_user = kwargs.get("current_user", {})
            user_id = current_user.get("sub") if current_user else None
            request_id = kwargs.get("request_id")

            # Build changes dict
            changes = {}
            if old_values and hasattr(entity, "__dict__"):
                for field, old_value in old_values.items():
                    new_value = getattr(entity, field, None)
                    if old_value != new_value:
                        changes[field] = {
                            "old": str(old_value) if old_value is not None else None,
                            "new": str(new_value) if new_value is not None else None,
                        }

            # Log the update operation
            if hasattr(entity, "id") and changes:
                try:
                    await log_audit(
                        db=self.db,
                        entity_type=entity_type,
                        entity_id=entity.id,
                        action="update",
                        user_id=user_id,
                        changes=changes,
                        request_id=request_id,
                    )
                except Exception as e:
                    logger.warning(
                        "audit_log_failed",
                        entity_type=entity_type,
                        action="update",
                        error=str(e),
                    )

            return entity if isinstance(result, tuple) else result

        return wrapper
    return decorator


def audit_delete(entity_type: str):
    """
    Decorator to audit delete operations.

    Usage:
        @audit_delete("credit")
        async def delete_credit(self, credit_id: UUID, current_user: dict):
            credit = await self.get_credit(credit_id)
            await self.db.delete(credit)
            return credit

    Args:
        entity_type: Type of entity being deleted
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Call the original function
            result = await func(self, *args, **kwargs)

            # Extract current_user from kwargs
            current_user = kwargs.get("current_user", {})
            user_id = current_user.get("sub") if current_user else None
            request_id = kwargs.get("request_id")

            # Log the delete operation
            if hasattr(result, "id"):
                try:
                    await log_audit(
                        db=self.db,
                        entity_type=entity_type,
                        entity_id=result.id,
                        action="delete",
                        user_id=user_id,
                        changes={},  # No changes for delete, entity is gone
                        request_id=request_id,
                    )
                except Exception as e:
                    logger.warning(
                        "audit_log_failed",
                        entity_type=entity_type,
                        action="delete",
                        error=str(e),
                    )

            return result

        return wrapper
    return decorator
