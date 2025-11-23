"""FastAPI dependencies for database sessions and authentication."""
from typing import AsyncGenerator, Optional
import structlog

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from billing.database import AsyncSessionLocal
from billing.auth.jwt import jwt_auth

logger = structlog.get_logger(__name__)

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

    Verifies JWT token using RS256 algorithm and returns user information.

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        dict: User information from decoded JWT (sub, email, role)

    Raises:
        HTTPException: If token is invalid, expired, or missing
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Verify and decode JWT token
        payload = jwt_auth.verify_access_token(token)

        logger.info(
            "user_authenticated",
            user_id=payload.get("sub"),
            email=payload.get("email"),
            role=payload.get("role"),
        )

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("token_expired", token_preview=token[:20] + "...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("invalid_token", error=str(e), token_preview=token[:20] + "...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
