"""
Request dependencies.

This file is the Phase 2 replacement for the DEV_USER_ID lookup in api.py.
It is still the ONLY place a user identity is produced — nothing downstream
changed, because everything already reads from user_context.
"""
import uuid

from fastapi import HTTPException, Request

from paai.auth import decode_token, read_access_token


def current_user(request: Request) -> uuid.UUID:
    token = read_access_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_token(token, expected_type="access")
    return uuid.UUID(claims["sub"])


def optional_user(request: Request) -> uuid.UUID | None:
    """For endpoints that behave differently when signed in but do not require it."""
    try:
        return current_user(request)
    except HTTPException:
        return None


def require_mailbox(request: Request) -> uuid.UUID:
    """
    For agent endpoints that need mailbox access. Fails with a specific error so
    the frontend can show 'connect your mailbox' rather than a generic 500 from
    somewhere deep inside a tool call.
    """
    from paai.db import list_oauth_providers

    user_id = current_user(request)
    if not list_oauth_providers(user_id):
        raise HTTPException(
            status_code=428,          # Precondition Required
            detail="No mailbox connected. Visit /connect/google/start or /connect/microsoft/start.",
        )
    return user_id
