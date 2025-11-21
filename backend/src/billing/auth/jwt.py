"""JWT authentication with RS256 signing.

This module provides secure JWT token creation and verification using RS256 algorithm.
RS256 uses asymmetric encryption (public/private key pair) which is more secure than
HS256 for distributed systems.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from billing.config import settings


class JWTAuth:
    """JWT authentication handler with RS256 signing."""

    def __init__(self):
        """Initialize JWT auth with RSA key pair."""
        self.algorithm = "RS256"
        self.access_token_expire_minutes = 60  # 1 hour
        self.refresh_token_expire_days = 7  # 7 days

        # In production, load these from secure storage (e.g., AWS Secrets Manager, HashiCorp Vault)
        # For now, generate ephemeral keys (they will be regenerated on restart)
        self._private_key = self._generate_private_key()
        self._public_key = self._private_key.public_key()

    def _generate_private_key(self) -> rsa.RSAPrivateKey:
        """
        Generate RSA private key.

        In production, this should be loaded from secure storage, not generated.

        Returns:
            RSA private key
        """
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

    def create_access_token(
        self,
        user_id: UUID,
        email: str,
        role: str,
        additional_claims: Optional[Dict] = None,
    ) -> str:
        """
        Create JWT access token.

        Args:
            user_id: User UUID
            email: User email
            role: User role (Super Admin, Billing Admin, Support Rep, Finance Viewer)
            additional_claims: Additional JWT claims

        Returns:
            Encoded JWT token
        """
        now = datetime.utcnow()
        expire = now + timedelta(minutes=self.access_token_expire_minutes)

        claims = {
            "sub": str(user_id),  # Subject (user ID)
            "email": email,
            "role": role,
            "iat": now,  # Issued at
            "exp": expire,  # Expiration
            "type": "access",
        }

        if additional_claims:
            claims.update(additional_claims)

        # Sign with private key
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        token = jwt.encode(claims, private_pem, algorithm=self.algorithm)
        return token

    def create_refresh_token(self, user_id: UUID) -> str:
        """
        Create JWT refresh token.

        Args:
            user_id: User UUID

        Returns:
            Encoded JWT refresh token
        """
        now = datetime.utcnow()
        expire = now + timedelta(days=self.refresh_token_expire_days)

        claims = {
            "sub": str(user_id),
            "iat": now,
            "exp": expire,
            "type": "refresh",
        }

        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        token = jwt.encode(claims, private_pem, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> Dict:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token claims

        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidTokenError: If token is invalid
        """
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        try:
            payload = jwt.decode(
                token,
                public_pem,
                algorithms=[self.algorithm],
                options={"verify_signature": True}
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise jwt.ExpiredSignatureError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise jwt.InvalidTokenError(f"Invalid token: {e}")

    def verify_access_token(self, token: str) -> Dict:
        """
        Verify access token specifically.

        Args:
            token: JWT access token

        Returns:
            Decoded token claims

        Raises:
            jwt.InvalidTokenError: If not an access token
        """
        payload = self.verify_token(token)

        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Not an access token")

        return payload

    def verify_refresh_token(self, token: str) -> Dict:
        """
        Verify refresh token specifically.

        Args:
            token: JWT refresh token

        Returns:
            Decoded token claims

        Raises:
            jwt.InvalidTokenError: If not a refresh token
        """
        payload = self.verify_token(token)

        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError("Not a refresh token")

        return payload

    def get_public_key_pem(self) -> bytes:
        """
        Get public key in PEM format for external verification.

        Returns:
            Public key in PEM format
        """
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )


# Global JWT auth instance
jwt_auth = JWTAuth()
