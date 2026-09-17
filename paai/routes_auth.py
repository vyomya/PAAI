"""
Auth routes.

  GET  /auth/{provider}/login       start login (free scopes only)
  GET  /auth/{provider}/callback    finish login, set session cookies
  POST /auth/refresh                rotate access token
  POST /auth/logout                 revoke refresh token
  GET  /auth/me                     current user + connected mailboxes

  GET  /connect/{provider}/start    second consent — mailbox scopes
  GET  /connect/{provider}/callback store provider tokens
  DELETE /connect/{provider}        disconnect a mailbox
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from paai.auth import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    decode_token,
    mint_access_token,
    mint_refresh_token,
    set_auth_cookies,
)
from paai.config import settings
from paai.db import (
    delete_oauth_connection,
    get_or_create_user_from_oauth,
    list_oauth_providers,
    revoke_refresh_token,
    store_refresh_token,
    upsert_oauth_connection,
)
from paai.deps import current_user
from paai.oauth import (
    LOGIN_SCOPES,
    MAILBOX_SCOPES,
    build_authorize_url,
    exchange_code,
    expires_at_from,
    fetch_userinfo,
    generate_pkce,
)

router = APIRouter()

# Short-lived store for the PKCE verifier and state between redirect and
# callback. In-memory is fine for a single instance; move to Redis (or a signed
# cookie) as soon as you run more than one replica in Phase 3, or logins will
# fail whenever the callback lands on a different instance than the start.
_pending: dict[str, dict] = {}


def _redirect_uri(kind: str, provider: str) -> str:
    return f"{settings.base_url}/{kind}/{provider}/callback"


# ── Login ─────────────────────────────────────────────────────────────────────
@router.get("/auth/{provider}/login")
async def login(provider: str):
    if provider not in LOGIN_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    verifier, challenge = generate_pkce()
    state = uuid.uuid4().hex
    _pending[state] = {
        "verifier": verifier,
        "provider": provider,
        "kind": "auth",
        "created": datetime.now(timezone.utc),
    }

    return RedirectResponse(
        build_authorize_url(
            provider,
            _redirect_uri("auth", provider),
            LOGIN_SCOPES[provider],
            state,
            challenge,
        )
    )


@router.get("/auth/{provider}/callback")
async def auth_callback(provider: str, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"{settings.frontend_url}/login?error={error}")

    pending = _pending.pop(state, None)
    if not pending or pending["provider"] != provider or pending["kind"] != "auth":
        # Unknown state means CSRF, a replayed callback, or a restarted server.
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    tokens = await exchange_code(
        provider, code, _redirect_uri("auth", provider), pending["verifier"]
    )
    info = await fetch_userinfo(provider, tokens["access_token"])

    if not info["email"]:
        raise HTTPException(status_code=400, detail="Provider returned no email")

    user_id = get_or_create_user_from_oauth(
        provider=provider,
        subject=info["subject"],
        email=info["email"],
        email_verified=info["email_verified"],
        display_name=info.get("name"),
    )

    access = mint_access_token(user_id)
    refresh, jti, expires_at = mint_refresh_token(user_id)
    store_refresh_token(user_id, jti, expires_at)

    response = RedirectResponse(f"{settings.frontend_url}/chat")
    set_auth_cookies(response, access, refresh)
    return response


# ── Session ───────────────────────────────────────────────────────────────────
@router.post("/auth/refresh")
async def refresh_session(request: Request):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    claims = decode_token(token, expected_type="refresh")
    user_id = uuid.UUID(claims["sub"])

    # Rotation: the old jti dies as the new one is issued, so a stolen refresh
    # token is usable at most once, and its use invalidates the real user's
    # session — which is how you find out it was stolen.
    revoke_refresh_token(claims["jti"])

    access = mint_access_token(user_id)
    new_refresh, jti, expires_at = mint_refresh_token(user_id)
    store_refresh_token(user_id, jti, expires_at)

    response = JSONResponse({"status": "ok"})
    set_auth_cookies(response, access, new_refresh)
    return response


@router.post("/auth/logout")
async def logout(request: Request):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            revoke_refresh_token(decode_token(token, "refresh")["jti"])
        except HTTPException:
            pass   # already invalid; logging out anyway

    response = JSONResponse({"status": "ok"})
    clear_auth_cookies(response)
    return response


@router.get("/auth/me")
async def me(user_id: uuid.UUID = Depends(current_user)):
    from paai.db import get_user_by_id

    user = get_user_by_id(user_id)
    return {
        "id": str(user_id),
        "email": user.email,
        "name": user.display_name,
        "connected_mailboxes": list_oauth_providers(user_id),
    }


# ── Mailbox connection (second consent) ───────────────────────────────────────
@router.get("/connect/{provider}/start")
async def connect_start(provider: str, user_id: uuid.UUID = Depends(current_user)):
    """
    Requires an existing session — you must be logged in before granting
    mailbox access, so the tokens have a user to attach to.
    """
    if provider not in MAILBOX_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    verifier, challenge = generate_pkce()
    state = uuid.uuid4().hex
    _pending[state] = {
        "verifier": verifier,
        "provider": provider,
        "kind": "connect",
        "user_id": user_id,
        "created": datetime.now(timezone.utc),
    }

    return RedirectResponse(
        build_authorize_url(
            provider,
            _redirect_uri("connect", provider),
            LOGIN_SCOPES[provider] + MAILBOX_SCOPES[provider],
            state,
            challenge,
            prompt_consent=True,   # force a refresh_token even on repeat consent
        )
    )


@router.get("/connect/{provider}/callback")
async def connect_callback(
    provider: str, code: str = "", state: str = "", error: str = ""
):
    if error:
        return RedirectResponse(f"{settings.frontend_url}/settings?error={error}")

    pending = _pending.pop(state, None)
    if not pending or pending["kind"] != "connect":
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    tokens = await exchange_code(
        provider, code, _redirect_uri("connect", provider), pending["verifier"]
    )
    info = await fetch_userinfo(provider, tokens["access_token"])

    if not tokens.get("refresh_token"):
        # Without this, access dies in ~1 hour and the agents break silently.
        raise HTTPException(
            status_code=400,
            detail="Provider returned no refresh token — retry with consent prompt.",
        )

    upsert_oauth_connection(
        user_id=pending["user_id"],
        provider=provider,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=expires_at_from(tokens),
        account_email=info["email"],
        scopes=tokens.get("scope", "").split(),
    )

    return RedirectResponse(f"{settings.frontend_url}/settings?connected={provider}")


@router.delete("/connect/{provider}")
async def disconnect(provider: str, user_id: uuid.UUID = Depends(current_user)):
    delete_oauth_connection(user_id, provider)
    return {"status": "disconnected", "provider": provider}
