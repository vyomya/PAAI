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
from paai.access import can_connect_google
from paai.config import settings
from paai.db import (
    delete_oauth_connection,
    get_or_create_user_from_oauth,
    list_oauth_providers,
    revoke_refresh_token,
    store_refresh_token,
    upsert_oauth_connection,is_refresh_token_valid,
    get_user_by_id
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
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from paai.oauth_state import consume_state, issue_state

router = APIRouter()

# Short-lived store for the PKCE verifier and state between redirect and
# callback. In-memory is fine for a single instance; move to Redis (or a signed
# cookie) as soon as you run more than one replica in Phase 3, or logins will
# fail whenever the callback lands on a different instance than the start.


def _redirect_uri(provider: str) -> str:
    return f"{settings.base_url}/auth/{provider}/callback"


# ── Login ─────────────────────────────────────────────────────────────────────
@router.get("/auth/{provider}/login")
async def login(provider: str):
    if provider not in LOGIN_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    verifier, challenge = generate_pkce()

    # The redirect carries the state cookie, so build the response first.
    response = RedirectResponse(url="about:blank")
    state = issue_state(response, provider, kind="auth", verifier=verifier)
    response.headers["location"] = build_authorize_url(
        provider, _redirect_uri(provider), LOGIN_SCOPES[provider], state, challenge
    )
    return response

@router.get("/auth/{provider}/callback")
async def auth_callback(
    provider: str,
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    if error:
        return RedirectResponse(f"{settings.frontend_url}/?error={error}")

    response = RedirectResponse(url="about:blank")
    pending = consume_state(request, response, state, provider)

    tokens = await exchange_code(
        provider, code, _redirect_uri(provider), pending.verifier
    )
    info = await fetch_userinfo(provider, tokens["access_token"])

    if pending.kind == "connect":
        if not pending.user_id:
            raise HTTPException(status_code=400, detail="No session for connect flow")
        if not tokens.get("refresh_token"):
            raise HTTPException(
                status_code=400,
                detail="Provider returned no refresh token — retry.",
            )
        upsert_oauth_connection(
            user_id=uuid.UUID(pending.user_id),
            provider=provider,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=expires_at_from(tokens),
            account_email=info["email"],
            scopes=tokens.get("scope", "").split(),
        )
        response.headers["location"] = (
            f"{settings.frontend_url}/settings?connected={provider}"
        )
        return response

    # login
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

    set_auth_cookies(response, access, refresh)
    response.headers["location"] = f"{settings.frontend_url}/chat"
    return response


# ── Session ───────────────────────────────────────────────────────────────────
@router.post("/auth/refresh")
async def refresh_session(request: Request):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    claims = decode_token(token, expected_type="refresh")
    if not is_refresh_token_valid(claims["jti"]):
        raise HTTPException(status_code=401, detail="Session ended")
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
    from paai.access import can_connect_google, is_owner
    from paai.db import get_user_by_id, list_oauth_providers

    user = get_user_by_id(user_id)
    return {
        "id": str(user_id),
        "email": user.email,
        "name": user.display_name,
        "connected_mailboxes": list_oauth_providers(user_id),
        "can_connect_google": can_connect_google(user.email),
        "is_owner": is_owner(user.email),
        "owner_email": settings.owner_email,
    }

@router.get("/connect/{provider}/start")
async def connect_start(provider: str, user_id: uuid.UUID = Depends(current_user)):
    if provider not in MAILBOX_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    if provider == "google":
        user = get_user_by_id(user_id)
        if not can_connect_google(user.email if user else None):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "google_tester_required",
                    "message": "Gmail access is limited to approved testers.",
                },
            )
        
    verifier, challenge = generate_pkce()
    response = RedirectResponse(url="about:blank")
    state = issue_state(
        response, provider, kind="connect", verifier=verifier, user_id=user_id
    )
    response.headers["location"] = build_authorize_url(
        provider,
        _redirect_uri(provider),
        LOGIN_SCOPES[provider] + MAILBOX_SCOPES[provider],
        state,
        challenge,
        prompt_consent=True,
    )
    return response


@router.delete("/connect/{provider}")
async def disconnect(provider: str, user_id: uuid.UUID = Depends(current_user)):
    delete_oauth_connection(user_id, provider)
    return {"status": "disconnected", "provider": provider}
