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

_current_user_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_user_id", default=None
)


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
def user_context(user_id: uuid.UUID):
    """
    Scope a block of work to one user.

        with user_context(user_id):
            run_agent(query)

    The token-based reset matters: nested contexts restore the outer value
    instead of clearing it.
    """
    token = _current_user_id.set(user_id)
    try:
        yield user_id
    finally:
        _current_user_id.reset(token)