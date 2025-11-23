"""
Authentication endpoints for token management.

Provides endpoints for:
- Token refresh (exchange refresh token for new access token)
- Public key retrieval (for external JWT verification)
"""

from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, Field
import jwt
import structlog

from billing.auth.jwt import jwt_auth

logger = structlog.get_logger(__name__)

router = APIRouter()


class TokenRefreshRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str = Field(
        ...,
        description="Valid refresh token obtained during login"
    )


class TokenRefreshResponse(BaseModel):
    """Response schema for token refresh."""

    access_token: str = Field(
        ...,
        description="New access token valid for 15 minutes"
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')"
    )
    expires_in: int = Field(
        default=900,  # 15 minutes in seconds
        description="Access token expiration time in seconds"
    )


class PublicKeyResponse(BaseModel):
    """Response schema for public key retrieval."""

    public_key: str = Field(
        ...,
        description="RSA public key in PEM format for JWT verification"
    )
    algorithm: str = Field(
        default="RS256",
        description="JWT signing algorithm"
    )


@router.post(
    "/auth/refresh",
    response_model=TokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh Access Token",
    description="""
    Exchange a valid refresh token for a new access token.

    **Use Case**: When the 15-minute access token expires, clients can use the
    7-day refresh token to obtain a new access token without requiring the user
    to re-authenticate.

    **Security**: This endpoint validates the refresh token signature and expiration.
    Only valid, unexpired refresh tokens will be accepted.

    **SOC2 Compliance**: Short-lived access tokens (15min) with long-lived refresh
    tokens (7d) limit exposure window while maintaining good user experience.
    """,
    responses={
        200: {
            "description": "Access token refreshed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "expires_in": 900
                    }
                }
            }
        },
        401: {
            "description": "Invalid or expired refresh token",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid refresh token: Token has expired"
                    }
                }
            }
        }
    }
)
async def refresh_access_token(
    request: TokenRefreshRequest,
    x_request_id: str = Header(None, alias="X-Request-ID")
) -> TokenRefreshResponse:
    """
    Refresh access token using refresh token.

    Args:
        request: Token refresh request with refresh token
        x_request_id: Optional request ID for tracing

    Returns:
        New access token with 15-minute expiration

    Raises:
        HTTPException 401: If refresh token is invalid or expired
    """
    try:
        # Verify refresh token
        payload = jwt_auth.verify_refresh_token(request.refresh_token)

        # Extract user info from refresh token
        user_id = payload.get("sub")

        if not user_id:
            logger.warning(
                "refresh_token_missing_subject",
                request_id=x_request_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token: missing subject"
            )

        # In production, this would:
        # 1. Fetch user from database to get current role and email
        # 2. Verify user is still active (not disabled/deleted)
        # 3. Check if refresh token is revoked (token blacklist)
        # 4. Optionally rotate refresh token for added security

        # For now, we'll use placeholder values
        # TODO: Integrate with user database
        user_email = "user@example.com"  # Fetch from DB
        user_role = "Billing Admin"  # Fetch from DB

        # Create new access token
        access_token = jwt_auth.create_access_token(
            user_id=user_id,
            email=user_email,
            role=user_role
        )

        logger.info(
            "access_token_refreshed",
            user_id=user_id,
            request_id=x_request_id
        )

        return TokenRefreshResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=jwt_auth.access_token_expire_minutes * 60  # Convert to seconds
        )

    except jwt.ExpiredSignatureError:
        logger.warning(
            "refresh_token_expired",
            request_id=x_request_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again."
        )

    except jwt.InvalidTokenError as e:
        logger.warning(
            "refresh_token_invalid",
            error=str(e),
            request_id=x_request_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}"
        )

    except Exception as e:
        logger.exception(
            "token_refresh_error",
            error=str(e),
            request_id=x_request_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        )


@router.get(
    "/auth/public-key",
    response_model=PublicKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Public Key",
    description="""
    Retrieve the RSA public key for JWT verification.

    **Use Case**: External services can use this public key to verify JWT signatures
    without needing to call back to the auth service for every token validation.

    **Security**: Only the public key is exposed, never the private key. This allows
    distributed JWT verification while maintaining security.
    """,
    responses={
        200: {
            "description": "Public key retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBg...\n-----END PUBLIC KEY-----",
                        "algorithm": "RS256"
                    }
                }
            }
        }
    }
)
async def get_public_key() -> PublicKeyResponse:
    """
    Get RSA public key for JWT verification.

    Returns:
        Public key in PEM format and signing algorithm
    """
    public_key_pem = jwt_auth.get_public_key_pem().decode("utf-8")

    return PublicKeyResponse(
        public_key=public_key_pem,
        algorithm=jwt_auth.algorithm
    )
