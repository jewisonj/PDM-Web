"""Shop Companion authentication: shared PIN -> long-lived device token.

Shop-floor workers use their own phones. They enter the shared shop PIN once;
the phone then stores a signed token so they never have to log in again.
"""

import hmac
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import get_settings

ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 365


def _get_secret_key() -> str:
    settings = get_settings()
    return f"shop_{settings.supabase_service_key[:32]}"


def verify_pin(pin: str) -> bool:
    """Constant-time compare against the configured shop PIN."""
    expected = get_settings().shop_pin.strip()
    return hmac.compare_digest((pin or "").strip(), expected)


def create_shop_token() -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": "shop", "type": "shop", "iat": now, "exp": exp}
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM), exp


def decode_shop_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "shop":
        return None
    return payload
