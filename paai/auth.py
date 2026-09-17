"""
PAAI session tokens.

Identity comes from Google or Microsoft — we never see or store a password, so
the whole category of password-reset / credential-stuffing / enumeration bugs
does not exist here. This module only mints and validates our own short-lived
session token after a provider has vouched for the user.

Two tokens:
  * access  — 15 minutes, sent on every request, not revocable (too short to matter)
  * refresh — 30 days, stored server-side by jti so it CAN be revoked

Without the server-side refresh record, a stolen token is valid until expiry and
you have no way to kill it. That is the part people skip.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, Response

from paai.config import settings

ALGORITHM = "HS256"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)

ACCESS_COOKIE = "paai_access"
REFRESH_COOKIE = "paai_refresh"


def _secret() -> str:
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET missing or too short (need >=32 chars). Generate one:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return settings.jwt_secret


def mint_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + ACCESS_TTL,
        },
        _secret(),
        algorithm=ALGORITHM,
    )


def mint_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). Caller persists the jti for revocation."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    expires_at = now + REFRESH_TTL
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "jti": jti,
            "iat": now,
            "exp": expires_at,
        },
        _secret(),
        algorithm=ALGORITHM,
    )
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if claims.get("type") != expected_type:
        # A refresh token presented as an access token is either a bug or an
        # attack; either way it does not get through.
        raise HTTPException(status_code=401, detail="Wrong token type")
    return claims


# ── Cookies ───────────────────────────────────────────────────────────────────
def set_auth_cookies(response: Response, access: str, refresh: str):
    """
    httpOnly so XSS on the frontend cannot read them — this is why we do not
    hand tokens to localStorage. secure=True in production means HTTPS only.
    """
    secure = not settings.dev_mode
    common = {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
    }
    response.set_cookie(
        ACCESS_COOKIE, access, max_age=int(ACCESS_TTL.total_seconds()), **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=int(REFRESH_TTL.total_seconds()),
        path="/auth",          # only sent to refresh/logout endpoints
        **common,
    )


def clear_auth_cookies(response: Response):
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE, path="/auth")


def read_access_token(request: Request) -> str | None:
    """Cookie first (browser), Authorization header second (CLI, mobile)."""
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None
