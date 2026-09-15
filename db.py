"""
Data access layer — Postgres + pgvector.

Public function names are unchanged from the SQLite/Chroma version so the diff
in agentic_framework.py is mechanical: add user_id as the first argument at
each call site, change nothing else.

The one rule that matters: every query filters on user_id. A missing filter
here means one user's history agent retrieves another user's emails.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from config import settings
from embeddings import embed
from models import Base, Message, OAuthConnection, Preference, Session, User

# ── Engine / session factory ──────────────────────────────────────────────────
# One pooled engine for the process. The old code opened a fresh sqlite3
# connection per call, which would exhaust a managed Postgres instantly.
_engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,   # survives the connection drops managed PG does on idle
    echo=settings.db_echo,
)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def db_session() -> OrmSession:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """
    Creates the pgvector extension. Table creation is Alembic's job —
    see scripts/alembic_setup.md. This stays callable at startup so a fresh
    local container works without manual psql.
    """
    with _engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def create_all_dev():
    """Local-only shortcut. Never call this in production — use Alembic."""
    init_db()
    Base.metadata.create_all(_engine)


# ── Users ─────────────────────────────────────────────────────────────────────
def get_or_create_user(email: str, display_name: str | None = None) -> uuid.UUID:
    with db_session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=display_name)
            s.add(user)
            s.flush()
        return user.id


def get_user_by_id(user_id: uuid.UUID) -> User | None:
    with db_session() as s:
        return s.get(User, user_id)


# ── Sessions ──────────────────────────────────────────────────────────────────
def save_session(
    user_id: uuid.UUID,
    user_input: str,
    final_output: str,
    plan_summary: list,
    session_id: str,
):
    with db_session() as s:
        s.add(
            Session(
                user_id=user_id,
                session_id=session_id,
                user_input=user_input,
                final_output=final_output,
                plan_summary=plan_summary,   # JSONB — no json.dumps needed
            )
        )


# ── Messages (was ChromaDB) ───────────────────────────────────────────────────
def save_message(user_id: uuid.UUID, session_id: str, role: str, content: str):
    with db_session() as s:
        s.add(
            Message(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                embedding=embed(content),
            )
        )


def get_recent_messages(user_id: uuid.UUID, limit: int = 10) -> list[dict]:
    """Most recent messages, returned oldest-first (matches old behaviour)."""
    with db_session() as s:
        rows = s.scalars(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).all()
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def search_messages(user_id: uuid.UUID, query: str, limit: int = 10) -> list[dict]:
    """
    Semantic search via cosine distance, scoped to one user.
    `<=>` is pgvector's cosine distance operator (0 = identical).
    """
    qvec = embed(query)
    with db_session() as s:
        rows = s.scalars(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.embedding.cosine_distance(qvec))
            .limit(limit)
        ).all()
    # Old code sorted results chronologically before returning — preserved.
    return [
        {"role": m.role, "content": m.content}
        for m in sorted(rows, key=lambda m: m.created_at)
    ]


def search_messages_scored(
    user_id: uuid.UUID, query: str, limit: int = 10, max_distance: float = 0.35
) -> list[dict]:
    """
    New: returns similarity scores and filters out weak matches.

    Your History Agent currently accepts whatever comes back from a top-k
    search, which always returns k results even when nothing is actually
    similar. A distance threshold is what turns 'nearest neighbours' into
    'genuine cache hit' — tune max_distance against real queries.
    """
    qvec = embed(query)
    distance = Message.embedding.cosine_distance(qvec).label("distance")
    with db_session() as s:
        rows = s.execute(
            select(Message, distance)
            .where(Message.user_id == user_id)
            .where(distance < max_distance)
            .order_by(distance)
            .limit(limit)
        ).all()
    return [
        {
            "role": m.role,
            "content": m.content,
            "similarity": 1.0 - float(d),
            "created_at": m.created_at.isoformat(),
        }
        for m, d in rows
    ]


def load_messages(
    user_id: uuid.UUID, query: str | None = None, limit: int = 20
) -> list[dict]:
    if query:
        return search_messages(user_id, query, limit)
    return get_recent_messages(user_id, limit)


# ── Preferences ───────────────────────────────────────────────────────────────
_REINFORCEMENT_DELTA = {
    "explicit": 0.20,
    "correction": 0.15,
    "implicit": 0.08,
}

_DECAY_FLOORS = {
    "explicit": 0.70,
    "correction": 0.60,
    "implicit": 0.30,
}

_BASE_CONFIDENCE = {
    "explicit": 0.90,
    "correction": 0.85,
    "implicit": 0.55,
}

DECAY_RATE = 0.02
CONFIDENCE_THRESHOLD = 0.50


def upsert_preference(
    user_id: uuid.UUID,
    category: str,
    rule: str,
    scope: str = "global",
    source: str = "explicit",
    contradiction: bool = False,
    contradiction_strength: str | None = None,
):
    """
    Same semantics as the SQLite version, with two fixes:
      * soft delete on absolute contradiction (was hard delete in one path,
        soft in another)
      * a real UPSERT instead of SELECT-then-branch, so two concurrent
        requests can't both insert the same (user, category, scope)
    """
    with db_session() as s:
        existing = s.scalar(
            select(Preference).where(
                Preference.user_id == user_id,
                Preference.category == category,
                Preference.scope == scope,
            )
        )

        if contradiction and existing:
            old_conf, old_source = existing.confidence, existing.source

            if contradiction_strength == "absolute":
                existing.status = "deleted"
                print(f"[PREF DB] Deleted (absolute contradiction): {category}/{scope}")

            elif contradiction_strength == "partial":
                new_conf = max(_DECAY_FLOORS.get(old_source, 0.3), old_conf - 0.30)
                existing.rule = rule
                existing.confidence = new_conf
                existing.status = "active"
                print(f"[PREF DB] Partial contradiction — conf={new_conf:.2f}")

            else:  # weak
                new_conf = old_conf - 0.30
                existing.confidence = new_conf
                if new_conf < 0.30:
                    existing.status = "conflicted"
                    print(f"[PREF DB] Weak contradiction — conflicted: {category}/{scope}")
                else:
                    print(f"[PREF DB] Weak contradiction — decayed to {new_conf:.2f}")
            return

        if existing is None:
            base = _BASE_CONFIDENCE.get(source, 0.70)
            stmt = (
                pg_insert(Preference)
                .values(
                    user_id=user_id,
                    category=category,
                    rule=rule,
                    scope=scope,
                    confidence=base,
                    source=source,
                    reinforcement_count=1,
                    interactions_since_seen=0,
                    status="active",
                )
                .on_conflict_do_nothing(constraint="uq_pref_user_category_scope")
            )
            s.execute(stmt)
            print(f"[PREF DB] New preference: {category}/{scope} conf={base:.2f} src={source}")
        else:
            delta = _REINFORCEMENT_DELTA.get(source, 0.08)
            new_conf = min(1.0, existing.confidence + delta)
            if rule != existing.rule:
                new_conf = max(0.50, new_conf - 0.10)
            existing.rule = rule
            existing.confidence = new_conf
            existing.reinforcement_count += 1
            existing.interactions_since_seen = 0
            existing.status = "active"
            print(
                f"[PREF DB] Reinforced: {category}/{scope} "
                f"conf={new_conf:.2f} count={existing.reinforcement_count}"
            )


def increment_interactions_since_seen(
    user_id: uuid.UUID, reinforced_keys: set[tuple[str, str]] | None = None
):
    """
    BUGFIX vs the SQLite version.

    The old function aged every active preference, including ones reinforced
    during the same run — so whether a fresh preference showed age 0 or 1
    depended purely on call order relative to upsert_preference().

    Pass the (category, scope) pairs touched this run and they're skipped.
    Falls back to a timestamp guard if the caller doesn't track them.
    """
    with db_session() as s:
        stmt = (
            update(Preference)
            .where(Preference.user_id == user_id, Preference.status == "active")
            .values(interactions_since_seen=Preference.interactions_since_seen + 1)
        )

        if reinforced_keys:
            for category, scope in reinforced_keys:
                stmt = stmt.where(
                    ~((Preference.category == category) & (Preference.scope == scope))
                )
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)
            stmt = stmt.where(Preference.updated_at < cutoff)

        s.execute(stmt)


def load_preferences(
    user_id: uuid.UUID,
    agent_scope: str | None = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> dict:
    """
    Active preferences with decay applied, filtered by scope and confidence.
    Returns {category: {rule, scope, confidence, source, reinforcement_count}}.
    """
    with db_session() as s:
        stmt = select(Preference).where(
            Preference.user_id == user_id, Preference.status == "active"
        )
        if agent_scope:
            stmt = stmt.where(Preference.scope.in_(["global", agent_scope]))
        rows = s.scalars(stmt).all()

    result = {}
    for p in rows:
        floor = _DECAY_FLOORS.get(p.source, 0.30)
        decayed = max(floor, p.confidence - (DECAY_RATE * p.interactions_since_seen))
        if decayed < confidence_threshold:
            continue
        result[p.category] = {
            "rule": p.rule,
            "scope": p.scope,
            "confidence": decayed,
            "source": p.source,
            "reinforcement_count": p.reinforcement_count,
        }
    return result


def persist_decay(user_id: uuid.UUID):
    """
    Apply decay to all active preferences and reset interactions_since_seen.
    If a preference decays to its floor and is implicit, mark it stale.
    """
    with db_session() as s:
        rows = s.scalars(
            select(Preference).where(
                Preference.user_id == user_id, Preference.status == "active"
            )
        ).all()
        for p in rows:
            floor = _DECAY_FLOORS.get(p.source, 0.30)
            decayed = max(floor, p.confidence - (DECAY_RATE * p.interactions_since_seen))
            p.confidence = decayed
            p.interactions_since_seen = 0
            if decayed <= floor and p.source == "implicit":
                p.status = "stale"


def delete_preference(user_id: uuid.UUID, category: str, scope: str = "global"):
    """Soft delete — consistent with the absolute-contradiction path."""
    with db_session() as s:
        s.execute(
            update(Preference)
            .where(
                Preference.user_id == user_id,
                Preference.category == category,
                Preference.scope == scope,
            )
            .values(status="deleted")
        )


def save_preference(user_id: uuid.UUID, category: str, rule: str):
    """Legacy shim — kept so old call sites keep working."""
    upsert_preference(user_id, category, rule, scope="global", source="explicit")


# ── OAuth connections ─────────────────────────────────────────────────────────
def upsert_oauth_connection(
    user_id: uuid.UUID,
    provider: str,
    access_token: str | None,
    refresh_token: str | None,
    expires_at: datetime | None = None,
    account_email: str | None = None,
    scopes: list[str] | None = None,
):
    from crypto import get_cipher

    cipher = get_cipher()
    with db_session() as s:
        conn = s.scalar(
            select(OAuthConnection).where(
                OAuthConnection.user_id == user_id,
                OAuthConnection.provider == provider,
            )
        )
        if conn is None:
            conn = OAuthConnection(user_id=user_id, provider=provider)
            s.add(conn)

        conn.access_token_enc = cipher.encrypt(access_token)
        if refresh_token:  # providers omit this on refresh — don't clobber
            conn.refresh_token_enc = cipher.encrypt(refresh_token)
        conn.token_expires_at = expires_at
        conn.provider_account_email = account_email
        conn.scopes = scopes
        conn.is_active = True


def get_oauth_connection(user_id: uuid.UUID, provider: str) -> dict | None:
    from crypto import get_cipher

    cipher = get_cipher()
    with db_session() as s:
        conn = s.scalar(
            select(OAuthConnection).where(
                OAuthConnection.user_id == user_id,
                OAuthConnection.provider == provider,
                OAuthConnection.is_active.is_(True),
            )
        )
        if conn is None:
            return None
        return {
            "provider": conn.provider,
            "account_email": conn.provider_account_email,
            "access_token": cipher.decrypt(conn.access_token_enc),
            "refresh_token": cipher.decrypt(conn.refresh_token_enc),
            "expires_at": conn.token_expires_at,
            "scopes": conn.scopes,
        }


def list_oauth_providers(user_id: uuid.UUID) -> list[str]:
    with db_session() as s:
        return list(
            s.scalars(
                select(OAuthConnection.provider).where(
                    OAuthConnection.user_id == user_id,
                    OAuthConnection.is_active.is_(True),
                )
            ).all()
        )