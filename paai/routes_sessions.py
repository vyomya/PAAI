"""
Session routes.

The sessions and messages tables have existed since Phase 1, but nothing read
them back — so the chat lived only in React state and vanished on navigation.
These endpoints make stored conversations real.

Everything here is scoped to the requesting user. The user_id filter is not
optional: without it, a guessed session_id reads someone else's inbox summary.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from paai.db import (
    delete_session,
    get_session_messages,
    list_sessions,
    rename_session,
)
from paai.deps import current_user

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def sessions_index(
    limit: int = 50, user_id: uuid.UUID = Depends(current_user)
):
    """Recent conversations, newest first, for the sidebar."""
    return {"sessions": list_sessions(user_id, limit=limit)}


@router.get("/{session_id}")
async def session_detail(
    session_id: str, user_id: uuid.UUID = Depends(current_user)
):
    messages = get_session_messages(user_id, session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": messages}


@router.patch("/{session_id}")
async def session_rename(
    session_id: str, title: str, user_id: uuid.UUID = Depends(current_user)
):
    rename_session(user_id, session_id, title)
    return {"status": "ok"}


@router.delete("/{session_id}")
async def session_delete(
    session_id: str, user_id: uuid.UUID = Depends(current_user)
):
    delete_session(user_id, session_id)
    return {"status": "deleted"}
