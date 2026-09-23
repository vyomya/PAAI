"""
Per-user token accounting and hard limits.

Recording happens per LLM call so you can see which part of the graph spends
what. Enforcement happens once per user turn, before the run starts — checking
mid-run would abandon work already paid for and hand the user a half-answer.

The consequence: a user can exceed their limit by at most one turn. That is the
right trade at this scale. If a single turn could cost enough to matter, the
fix is a per-turn ceiling, not per-call enforcement.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from paai.config import settings
from paai.context import get_current_user
from paai.db import db_session
from paai.models import TokenUsage, User


class QuotaExceeded(Exception):
    """Raised before a run starts when the user is out of tokens."""

    def __init__(self, used: int, limit: int):
        self.used = used
        self.limit = limit
        super().__init__(
            f"Token limit reached ({used:,} of {limit:,} used)."
        )


# Set by run_agent so usage rows can be grouped by turn. A ContextVar rather
# than a parameter because llm.invoke() is called from a dozen places in the
# graph and threading session_id through all of them adds noise for no gain.
from contextvars import ContextVar

_session_id: ContextVar[str | None] = ContextVar("usage_session_id", default=None)


def set_session(session_id: str):
    _session_id.set(session_id)


def record_usage(
    model: str,
    purpose: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float,
    user_id: uuid.UUID | None = None,
):
    if user_id is None:
        try:
            user_id = get_current_user()
        except Exception:
            # Calls outside a request (scripts, tests) are not billed to anyone.
            return

    with db_session() as s:
        s.add(
            TokenUsage(
                user_id=user_id,
                session_id=_session_id.get(),
                model=model,
                purpose=purpose,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=cost,
            )
        )


# ── Limits ────────────────────────────────────────────────────────────────────
def user_limit(user_id: uuid.UUID) -> int:
    """Per-user override, else the global default."""
    with db_session() as s:
        user = s.get(User, user_id)
        if user and user.token_limit is not None:
            return user.token_limit
    return settings.default_token_limit


def tokens_used(user_id: uuid.UUID, since: datetime | None = None) -> int:
    with db_session() as s:
        stmt = select(func.coalesce(func.sum(TokenUsage.total_tokens), 0)).where(
            TokenUsage.user_id == user_id
        )
        if since:
            stmt = stmt.where(TokenUsage.created_at >= since)
        return int(s.scalar(stmt) or 0)


def check_quota(user_id: uuid.UUID):
    """
    Call once at the start of a user turn. Raises QuotaExceeded.

    The owner is exempt — you should not be able to lock yourself out of your
    own app while testing it.
    """
    from paai.access import is_owner
    from paai.db import get_user_by_id

    user = get_user_by_id(user_id)
    if user and is_owner(user.email):
        return

    limit = user_limit(user_id)
    if limit <= 0:          # 0 or negative means unlimited
        return

    used = tokens_used(user_id)
    if used >= limit:
        raise QuotaExceeded(used, limit)


def summary(user_id: uuid.UUID) -> dict:
    """For the profile page and the /usage endpoint."""
    limit = user_limit(user_id)
    used = tokens_used(user_id)
    week = tokens_used(user_id, since=datetime.now(timezone.utc) - timedelta(days=7))

    with db_session() as s:
        cost = float(
            s.scalar(
                select(func.coalesce(func.sum(TokenUsage.cost_usd), 0.0)).where(
                    TokenUsage.user_id == user_id
                )
            )
            or 0.0
        )

        by_purpose = s.execute(
            select(
                TokenUsage.purpose,
                func.sum(TokenUsage.total_tokens),
                func.count(TokenUsage.id),
            )
            .where(TokenUsage.user_id == user_id)
            .group_by(TokenUsage.purpose)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
        ).all()

        by_model = s.execute(
            select(
                TokenUsage.model,
                func.sum(TokenUsage.total_tokens),
                func.sum(TokenUsage.cost_usd),
            )
            .where(TokenUsage.user_id == user_id)
            .group_by(TokenUsage.model)
        ).all()

    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used) if limit > 0 else None,
        "unlimited": limit <= 0,
        "used_last_7_days": week,
        "cost_usd": round(cost, 4),
        "by_purpose": [
            {"purpose": p, "tokens": int(t), "calls": int(c)} for p, t, c in by_purpose
        ],
        "by_model": [
            {"model": m, "tokens": int(t), "cost_usd": round(float(c or 0), 4)}
            for m, t, c in by_model
        ],
    }


def set_limit(user_id: uuid.UUID, limit: int | None):
    """Owner tool. None reverts to the global default; 0 means unlimited."""
    with db_session() as s:
        user = s.get(User, user_id)
        if user:
            user.token_limit = limit
