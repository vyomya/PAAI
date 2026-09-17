"""
OAuth for Google and Microsoft.

Two deliberately separate flows:

  LOGIN    — openid/email/profile only. Free forever on both providers. No
             Google verification, no CASA assessment, no cost.

  CONNECT  — mailbox and calendar scopes, requested later as a second consent.
             These are Google *restricted* scopes: fine under the personal-use
             exception today, subject to an annual paid security assessment
             once you have real outside users.

Keeping them apart means a multi-user PAAI can ship at zero cost, with mailbox
connection gated behind whatever you decide about CASA. It is also better UX —
nobody's first impression of your app should be a scary full-mailbox consent
screen.
"""
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException

from paai.config import settings

# ── Scope sets ────────────────────────────────────────────────────────────────
LOGIN_SCOPES = {
    "google": ["openid", "email", "profile"],
    "microsoft": ["openid", "email", "profile", "offline_access"],
}

# Requested only at /connect time. Audit these against what the agents actually
# call — every extra scope raises your CASA tier and therefore your bill.
MAILBOX_SCOPES = {
    "google": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",   # drafts, not send
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
    "microsoft": [
        "offline_access",
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.ReadWrite",      # drafts
        "https://graph.microsoft.com/Calendars.Read",
    ],
}


@dataclass
class ProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    client_id: str
    client_secret: str


def get_provider_config(provider: str) -> ProviderConfig:
    if provider == "google":
        return ProviderConfig(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
    if provider == "microsoft":
        # /common = multi-tenant: personal Microsoft accounts and work accounts.
        return ProviderConfig(
            name="microsoft",
            authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
            userinfo_url="https://graph.microsoft.com/v1.0/me",
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
        )
    raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")


# ── PKCE + state ──────────────────────────────────────────────────────────────
def generate_pkce() -> tuple[str, str]:
    """
    PKCE binds the authorization code to this specific client. Without it, an
    intercepted code can be redeemed by anyone holding your client_id.
    """
    import base64
    import hashlib

    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


def build_authorize_url(
    provider: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    code_challenge: str,
    prompt_consent: bool = False,
) -> str:
    from urllib.parse import urlencode

    cfg = get_provider_config(provider)
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    if provider == "google":
        params["access_type"] = "offline"
        if prompt_consent:
            # Google only returns a refresh_token on the FIRST consent unless
            # you force it. Skip this and returning users silently get no
            # refresh token, and their mailbox access dies in an hour.
            params["prompt"] = "consent"
        params["include_granted_scopes"] = "true"   # incremental consent

    return f"{cfg.authorize_url}?{urlencode(params)}"


async def exchange_code(
    provider: str, code: str, redirect_uri: str, code_verifier: str
) -> dict:
    cfg = get_provider_config(provider)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            cfg.token_url,
            data={
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")
    return resp.json()


async def refresh_access_token(provider: str, refresh_token: str) -> dict:
    cfg = get_provider_config(provider)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            cfg.token_url,
            data={
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail="Provider refresh failed — the user must reconnect.",
        )
    return resp.json()

def refresh_access_token_sync(provider: str, refresh_token: str) -> dict:
    cfg = get_provider_config(provider)
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            cfg.token_url,
            data={
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(f"{provider} token refresh failed — user must reconnect.")
    return resp.json()

# ── Identity ──────────────────────────────────────────────────────────────────
async def fetch_userinfo(provider: str, access_token: str) -> dict:
    """
    Normalised identity: {subject, email, email_verified, name}.

    email_verified matters: account linking keys on email, so an unverified
    address would let someone claim another user's account by registering the
    same address with a provider that does not check.
    """
    cfg = get_provider_config(provider)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            cfg.userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not fetch user info")
    data = resp.json()

    if provider == "google":
        return {
            "subject": data["sub"],
            "email": data.get("email", "").lower(),
            "email_verified": bool(data.get("email_verified")),
            "name": data.get("name"),
        }

    # Microsoft Graph /me. Personal accounts put the address in userPrincipalName.
    email = (data.get("mail") or data.get("userPrincipalName") or "").lower()
    return {
        "subject": data["id"],
        "email": email,
        # Graph does not expose a verification flag; a tenant-issued address is
        # verified by definition, so treat it as such.
        "email_verified": True,
        "name": data.get("displayName"),
    }


def expires_at_from(token_response: dict) -> datetime | None:
    seconds = token_response.get("expires_in")
    if not seconds:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(seconds))
