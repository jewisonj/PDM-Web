"""Supplier authentication service using PyJWT and bcrypt."""

import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from ..config import get_settings

# JWT settings - use a dedicated secret for supplier tokens
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def _get_secret_key() -> str:
    """Get the JWT secret key from settings."""
    # Use the Supabase service key as the base for our supplier JWT secret
    # This ensures it's unique per deployment
    settings = get_settings()
    return f"supplier_{settings.supabase_service_key[:32]}"


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


def create_supplier_token(supplier_id: UUID, email: str) -> str:
    """Create a JWT token for a supplier."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(supplier_id),
        "email": email,
        "type": "supplier",
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_supplier_token(token: str) -> Optional[dict]:
    """Decode and validate a supplier JWT token.

    Returns the payload dict if valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        # Verify this is a supplier token
        if payload.get("type") != "supplier":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
