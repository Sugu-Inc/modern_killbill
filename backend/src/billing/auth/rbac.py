"""Role-Based Access Control (RBAC) decorator and utilities.

Implements 4-tier role hierarchy:
- Super Admin: Full system access
- Billing Admin: Manage billing, plans, subscriptions
- Support Rep: View accounts, process refunds, manage credits
- Finance Viewer: Read-only access to financial data
"""
from enum import Enum
from functools import wraps
from typing import List, Callable, Any

from fastapi import HTTPException, status
import structlog

logger = structlog.get_logger(__name__)


class Role(str, Enum):
    """User roles with hierarchical permissions."""

    SUPER_ADMIN = "Super Admin"
    BILLING_ADMIN = "Billing Admin"
    SUPPORT_REP = "Support Rep"
    FINANCE_VIEWER = "Finance Viewer"


# Role hierarchy: higher roles inherit permissions from lower roles
ROLE_HIERARCHY = {
    Role.SUPER_ADMIN: [Role.SUPER_ADMIN, Role.BILLING_ADMIN, Role.SUPPORT_REP, Role.FINANCE_VIEWER],
    Role.BILLING_ADMIN: [Role.BILLING_ADMIN, Role.SUPPORT_REP, Role.FINANCE_VIEWER],
    Role.SUPPORT_REP: [Role.SUPPORT_REP, Role.FINANCE_VIEWER],
    Role.FINANCE_VIEWER: [Role.FINANCE_VIEWER],
}


# Permission mappings for each role
PERMISSIONS = {
    Role.SUPER_ADMIN: {
        "accounts": ["create", "read", "update", "delete"],
        "plans": ["create", "read", "update", "delete"],
        "subscriptions": ["create", "read", "update", "delete", "pause", "resume", "cancel"],
        "invoices": ["create", "read", "update", "delete", "void"],
        "payments": ["create", "read", "retry"],
        "credits": ["create", "read", "update", "delete"],
        "usage": ["create", "read"],
        "webhooks": ["create", "read", "update", "delete"],
        "analytics": ["read"],
        "system": ["configure", "manage_users"],
    },
    Role.BILLING_ADMIN: {
        "accounts": ["create", "read", "update"],
        "plans": ["create", "read", "update"],
        "subscriptions": ["create", "read", "update", "pause", "resume", "cancel"],
        "invoices": ["create", "read", "void"],
        "payments": ["read", "retry"],
        "credits": ["create", "read"],
        "usage": ["create", "read"],
        "webhooks": ["read"],
        "analytics": ["read"],
    },
    Role.SUPPORT_REP: {
        "accounts": ["read", "update"],
        "plans": ["read"],
        "subscriptions": ["read", "pause", "resume"],
        "invoices": ["read"],
        "payments": ["read"],
        "credits": ["create", "read"],
        "usage": ["read"],
        "webhooks": ["read"],
    },
    Role.FINANCE_VIEWER: {
        "accounts": ["read"],
        "plans": ["read"],
        "subscriptions": ["read"],
        "invoices": ["read"],
        "payments": ["read"],
        "credits": ["read"],
        "usage": ["read"],
        "analytics": ["read"],
    },
}


def has_permission(role: str, resource: str, action: str) -> bool:
    """
    Check if role has permission for resource action.

    Args:
        role: User role
        resource: Resource type (e.g., "accounts", "subscriptions")
        action: Action to perform (e.g., "create", "read", "update", "delete")

    Returns:
        True if role has permission, False otherwise
    """
    try:
        role_enum = Role(role)
    except ValueError:
        logger.warning("invalid_role_check", role=role)
        return False

    # Check if role has explicit permission
    role_perms = PERMISSIONS.get(role_enum, {})
    resource_perms = role_perms.get(resource, [])

    return action in resource_perms


def check_role_hierarchy(user_role: str, required_roles: List[Role]) -> bool:
    """
    Check if user role satisfies any of the required roles (considering hierarchy).

    Args:
        user_role: User's role
        required_roles: List of acceptable roles

    Returns:
        True if user role satisfies requirement
    """
    try:
        user_role_enum = Role(user_role)
    except ValueError:
        return False

    # Get roles this user has access to (including inherited)
    user_allowed_roles = ROLE_HIERARCHY.get(user_role_enum, [])

    # Check if any required role is in user's allowed roles
    return any(req_role in user_allowed_roles for req_role in required_roles)


def require_roles(*required_roles: Role):
    """
    Decorator to require specific roles for endpoint access.

    Usage:
        @require_roles(Role.SUPER_ADMIN, Role.BILLING_ADMIN)
        async def create_plan(...):
            ...

    Args:
        required_roles: One or more roles that can access this endpoint

    Raises:
        HTTPException: 403 if user doesn't have required role
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs (injected by get_current_user dependency)
            current_user = kwargs.get("current_user")

            if not current_user:
                logger.error("rbac_missing_current_user", endpoint=func.__name__)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            user_role = current_user.get("role")

            if not check_role_hierarchy(user_role, list(required_roles)):
                logger.warning(
                    "rbac_permission_denied",
                    user_id=current_user.get("sub"),
                    user_role=user_role,
                    required_roles=[r.value for r in required_roles],
                    endpoint=func.__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required roles: {', '.join(r.value for r in required_roles)}",
                )

            logger.info(
                "rbac_access_granted",
                user_id=current_user.get("sub"),
                user_role=user_role,
                endpoint=func.__name__,
            )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_permission(resource: str, action: str):
    """
    Decorator to require specific permission for endpoint access.

    Usage:
        @require_permission("subscriptions", "cancel")
        async def cancel_subscription(...):
            ...

    Args:
        resource: Resource type
        action: Action type

    Raises:
        HTTPException: 403 if user doesn't have required permission
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            user_role = current_user.get("role")

            if not has_permission(user_role, resource, action):
                logger.warning(
                    "rbac_permission_denied",
                    user_id=current_user.get("sub"),
                    user_role=user_role,
                    required_permission=f"{resource}:{action}",
                    endpoint=func.__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {resource}:{action}",
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator
