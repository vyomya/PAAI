"""
Who may connect a Google mailbox.

Gmail scopes are restricted, so until PAAI clears Google verification only
accounts on the console's test-user list can consent. This module mirrors that
list in the database so approving someone is one UPDATE rather than an env var
change plus a redeploy.

It is a mirror, not a security boundary — Google enforces the real thing. Its
job is to produce a good error early, and to give the owner a queue of who is
waiting.

Two-step by design: a row here does NOT grant access on its own. You still add
the address in the Google console. This table tracks who asked and who you have
already added, so the two stay in sync.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from paai.config import settings
from paai.db import db_session
from paai.models import GoogleTester, User

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"


def is_owner(email: str | None) -> bool:
    if not email or not settings.owner_email:
        return False
    return email.lower() == settings.owner_email.lower()


def can_connect_google(email: str | None) -> bool:
    """
    True when this address has been approved.

    The owner is always allowed: locking yourself out of your own app because
    you forgot to add yourself is a silly failure mode.
    """
    if not email:
        return False
    if is_owner(email):
        return True

    with db_session() as s:
        row = s.scalar(
            select(GoogleTester).where(GoogleTester.email == email.lower())
        )
        return bool(row and row.status == APPROVED)


def request_access(user_id: uuid.UUID, email: str, note: str | None = None) -> dict:
    """
    Record that someone wants Gmail access.

    Idempotent: clicking twice does not create a second row or reset an
    existing approval.
    """
    email = email.lower()

    with db_session() as s:
        row = s.scalar(select(GoogleTester).where(GoogleTester.email == email))

        if row:
            if row.status == DENIED:
                # Let a denied user ask again rather than silently ignoring them.
                row.status = PENDING
                row.requested_at = datetime.now(timezone.utc)
                row.note = note
                return {"status": PENDING, "resubmitted": True}
            return {"status": row.status, "resubmitted": False}

        s.add(
            GoogleTester(
                email=email,
                user_id=user_id,
                status=PENDING,
                note=note,
            )
        )
        return {"status": PENDING, "resubmitted": False}


def list_requests(status: str | None = None) -> list[dict]:
    """For the owner: who is waiting, who is approved."""
    with db_session() as s:
        stmt = select(GoogleTester).order_by(GoogleTester.requested_at.desc())
        if status:
            stmt = stmt.where(GoogleTester.status == status)
        rows = s.scalars(stmt).all()

        out = []
        for r in rows:
            user = s.get(User, r.user_id) if r.user_id else None
            out.append(
                {
                    "email": r.email,
                    "status": r.status,
                    "name": user.display_name if user else None,
                    "note": r.note,
                    "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                    "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                }
            )
        return out


def set_status(email: str, status: str) -> bool:
    """
    Approve or deny. Creating the row if absent lets the owner pre-approve
    someone before they have ever signed in.
    """
    if status not in (PENDING, APPROVED, DENIED):
        raise ValueError(f"Unknown status: {status}")

    email = email.lower()
    now = datetime.now(timezone.utc)

    with db_session() as s:
        row = s.scalar(select(GoogleTester).where(GoogleTester.email == email))
        if row is None:
            s.add(
                GoogleTester(
                    email=email,
                    status=status,
                    approved_at=now if status == APPROVED else None,
                )
            )
            return True

        row.status = status
        row.approved_at = now if status == APPROVED else None
        return True


def remove(email: str) -> bool:
    from sqlalchemy import delete as sa_delete

    with db_session() as s:
        result = s.execute(
            sa_delete(GoogleTester).where(GoogleTester.email == email.lower())
        )
        return result.rowcount > 0