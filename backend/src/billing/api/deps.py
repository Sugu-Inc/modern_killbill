"""FastAPI dependencies for database sessions and authentication."""
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from billing.database import AsyncSessionLocal

# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency.

    Yields:
        AsyncSession: Database session for the request lifecycle
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict[str, str]:
    """
    Get current authenticated user from JWT token.

    This is a skeleton implementation. Full JWT verification will be added
    in Phase 19 (Authentication & Authorization).

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        dict: User information from decoded JWT

    Raises:
        HTTPException: If token is invalid or missing
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Placeholder for JWT verification
    # TODO: Implement JWT decoding and verification in T151-T153
    return {
        "user_id": "placeholder",
        "email": "user@example.com",
        "role": "admin",
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict[str, str]]:
    """
    Get current user if authenticated, otherwise None.

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        Optional[dict]: User information if authenticated, None otherwise
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
