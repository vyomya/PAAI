"""
Per-request user context.

Why this exists
---------------
Most db.* calls can take user_id as an argument. Tools cannot: the History
Agent exposes tools to the LLM and the LLM decides the arguments, so any
user_id in a tool schema is a value the model controls. That is a data
isolation hole — a prompt injection inside an email body could ask for
another user's history and the tool would comply.

So user_id never enters the model's context. It is set once per request here
and read directly by tool.py.

Why contextvars and not a global
--------------------------------
FastAPI serves requests concurrently. A module-level global would be shared
across in-flight requests and two users could interleave. A ContextVar gives
each async task (and each thread, via copy_context) its own value.
"""
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_current_user_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_user_id", default=None
)

_current_timezone: ContextVar[str | None] = ContextVar(
    "current_timezone", default=None
)
DEFAULT_TIMEZONE = "UTC"


def safe_timezone(name: str | None) -> str | None:
    """Return the name if it is a valid IANA zone, else None."""
    if not name:
        return None
    try:
        ZoneInfo(name)
        return name
    except (ZoneInfoNotFoundError, ValueError):
        return None


def get_user_timezone() -> ZoneInfo:
    """The requesting user's zone, or UTC when none was supplied."""
    return ZoneInfo(_current_timezone.get() or DEFAULT_TIMEZONE)


class NoUserContextError(RuntimeError):
    """Raised when user-scoped data is requested outside a user context."""


def set_current_user(user_id: uuid.UUID):
    """Low-level setter. Prefer the user_context() context manager."""
    return _current_user_id.set(user_id)


def get_current_user() -> uuid.UUID:
    """
    Read the active user id.

    Deliberately raises rather than returning a default. A silent fallback to
    some 'default user' is how cross-user data leaks happen — better to fail
    loudly at the call site than to quietly serve the wrong person's mailbox.
    """
    user_id = _current_user_id.get()
    if user_id is None:
        raise NoUserContextError(
            "No user in context. Wrap the call in user_context(user_id) — "
            "this usually means a tool ran outside a request."
        )
    return user_id


@contextmanager
def user_context(user_id: uuid.UUID, timezone: str | None = None):
    """
    Scope a block of work to one user (and, optionally, their timezone).

        with user_context(user_id, timezone="America/New_York"):
            run_agent(query)

    The token-based reset matters: nested contexts restore the outer value
    instead of clearing it.
    """
    token = _current_user_id.set(user_id)
    tz_token = _current_timezone.set(safe_timezone(timezone))
    try:
        yield user_id
    finally:
        _current_timezone.reset(tz_token)
        _current_user_id.reset(token)