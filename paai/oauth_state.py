"""
OAuth state, carried in a signed cookie instead of server memory.

Why this replaces `_pending`
----------------------------
`_pending` was a module-level dict holding the PKCE verifier between the
redirect to Google and the callback. That works on exactly one process. In
production you run multiple uvicorn workers, and Render may run multiple
instances — so the callback frequently lands on a different process than the
one that started the flow, and the login fails with "invalid or expired state".

Intermittent, roughly half the time, and impossible to reproduce locally. This
removes the failure mode entirely rather than making it rarer.

Why a cookie rather than Redis
------------------------------
The state only needs to survive one redirect round-trip, and it only needs to
be readable by the same browser that started the flow. A short-lived signed
cookie does that with no extra infrastructure. Redis would work too, and is
the right answer if you later need server-side revocation of in-flight flows.

The cookie is signed, not encrypted: the browser can read the verifier, but the
browser is the party that generated the flow anyway. What signing prevents is
an attacker *forging* a state — swapping in their own verifier, or flipping
`kind` from "auth" to "connect" to attach their mailbox to your account.
"""
import json
import time
import uuid
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request, Response

from paai.config import settings

STATE_COOKIE = "paai_oauth"
STATE_TTL = 600  # 10 minutes — long enough to read a consent screen


@dataclass
class OAuthState:
    state: str
    verifier: str
    provider: str
    kind: str                      # "auth" | "connect"
    user_id: str | None = None     # set for "connect", which requires a session


def issue_state(
    response: Response,
    provider: str,
    kind: str,
    verifier: str,
    user_id: uuid.UUID | None = None,
) -> str:
    state = uuid.uuid4().hex
    now = int(time.time())

    token = jwt.encode(
        {
            "state": state,
            "verifier": verifier,
            "provider": provider,
            "kind": kind,
            "user_id": str(user_id) if user_id else None,
            "iat": now,
            "exp": now + STATE_TTL,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    response.set_cookie(
        STATE_COOKIE,
        token,
        max_age=STATE_TTL,
        httponly=True,
        secure=not settings.dev_mode,
        # Lax, not Strict: the provider redirects back via a top-level
        # navigation from accounts.google.com, and Strict would drop the cookie
        # on exactly that request.
        samesite="lax",
        path="/",
    )
    return state


def consume_state(request: Request, response: Response, state: str, provider: str) -> OAuthState:
    """
    Validate and immediately clear. Single use: replaying a callback with the
    same code should fail.
    """
    token = request.cookies.get(STATE_COOKIE)
    response.delete_cookie(STATE_COOKIE, path="/")

    if not token:
        raise HTTPException(
            status_code=400,
            detail="Login session expired. Start again.",
        )

    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Login took too long. Start again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid login state.")

    # The state in the URL must match the one in the signed cookie. This is the
    # CSRF check: an attacker can put anything in the query string, but cannot
    # produce a cookie signed with our secret.
    if claims.get("state") != state:
        raise HTTPException(status_code=400, detail="State mismatch.")

    if claims.get("provider") != provider:
        raise HTTPException(status_code=400, detail="Provider mismatch.")

    return OAuthState(
        state=claims["state"],
        verifier=claims["verifier"],
        provider=claims["provider"],
        kind=claims["kind"],
        user_id=claims.get("user_id"),
    )
