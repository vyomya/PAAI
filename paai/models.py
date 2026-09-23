"""
SQLAlchemy models — the multi-tenant schema.

Design rules baked in here:
  * Every table except `users` carries user_id and is indexed on it.
  * OAuth tokens are stored encrypted (see crypto.py); the columns are bytes.
  * Message embeddings live in Postgres via pgvector, replacing ChromaDB.
  * Preferences keep the exact semantics of the SQLite version
    (category/scope composite key, confidence, source, reinforcement tracking)
    with user_id promoted into the key.
"""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from paai.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Users ─────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))

    # Populated in Phase 2 by the auth provider (Supabase/Clerk subject claim).
    auth_provider: Mapped[str | None] = mapped_column(String(50))
    auth_subject: Mapped[str | None] = mapped_column(String(255), index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    oauth_connections: Mapped[list["OAuthConnection"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    token_limit: Mapped[int | None] = mapped_column(Integer)


# ── OAuth connections (Gmail today, Outlook in Phase 6) ───────────────────────
class OAuthConnection(Base):
    """
    One row per (user, provider). This table is what makes Outlook a config
    change rather than a rewrite: the agents ask for 'the user's email
    provider' and get whichever row exists.
    """

    __tablename__ = "oauth_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False)  # gmail | outlook
    provider_account_email: Mapped[str | None] = mapped_column(String(320))

    # Encrypted with Fernet — never store these in plaintext.
    access_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scopes: Mapped[list | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="oauth_connections")


# ── Messages (replaces ChromaDB) ──────────────────────────────────────────────
class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Composite index: every semantic search filters by user_id first.
        Index("ix_messages_user_created", "user_id", "created_at"),
        Index("ix_messages_user_session", "user_id", "session_id"),
        # HNSW index for cosine similarity. Good default up to ~1M rows.
        Index(
            "ix_messages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


# ── Preferences (ports the SQLite table) ──────────────────────────────────────
class Preference(Base):
    __tablename__ = "preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category", "scope", name="uq_pref_user_category_scope"
        ),
        Index("ix_preferences_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    category: Mapped[str] = mapped_column(String(200), nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False, default="global")

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="explicit")
    reinforcement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interactions_since_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ── Sessions ──────────────────────────────────────────────────────────────────
class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_created", "user_id", "created_at"),)
    title: Mapped[str | None] = mapped_column(String(200))

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    final_output: Mapped[str | None] = mapped_column(Text)
    # JSONB instead of a json.dumps'd TEXT blob — queryable, typed.
    plan_summary: Mapped[list | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

class RefreshToken(Base):
    """
    Server-side record of issued refresh tokens, keyed by jti.

    A JWT cannot be revoked — it is valid until it expires. Without this table,
    a stolen 30-day refresh token is a 30-day compromise with no way to end it,
    and "log out" would be a lie told to the browser.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_user_active", "user_id", "revoked"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
class GoogleTester(Base):
    """
    Mirror of the Google console's test-user list, plus the requests queue.

    Gmail scopes are restricted, so Google refuses consent for anyone not on
    its own list. Keeping a copy here means the app can show a useful message
    before sending the user to a 403, and the owner can approve without a
    redeploy.
    """

    __tablename__ = "google_testers"
    __table_args__ = (Index("ix_google_testers_status", "status"),)

    email: Mapped[str] = mapped_column(String(320), primary_key=True)

    # Nullable so the owner can pre-approve an address before that person has
    # ever signed in.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    note: Mapped[str | None] = mapped_column(Text)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class TokenUsage(Base):
    """
    One row per LLM call.

    Per-call rather than per-turn so you can answer "what is actually
    spending the money" — the answer is usually the agent nodes, not the
    number of turns.
    """

    __tablename__ = "token_usage"
    __table_args__ = (
        Index("ix_token_usage_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(100), index=True)

    model: Mapped[str] = mapped_column(String(60), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )