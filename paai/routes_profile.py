"""
Profile routes.

Surfaces what PAAI has accumulated about a user: usage counts and the
preferences its extractor has learned.

The preferences endpoint is the interesting one. Your confidence system decides
which rules get injected into agent prompts, but until now that was invisible —
the user had no way to see what PAAI thought it knew about them, or to notice
when it had learned something wrong. Showing it is both a product feature and
the fastest way to debug the extractor.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from paai.db import (
    delete_preference,
    list_preferences_for_display,
    user_stats,
)
from paai.deps import current_user

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/stats")
async def stats(user_id: uuid.UUID = Depends(current_user)):
    """Counts for the profile header."""
    return user_stats(user_id)


@router.get("/preferences")
async def preferences(user_id: uuid.UUID = Depends(current_user)):
    """
    Active preferences with decayed confidence applied.

    Decayed rather than stored, because that is the value actually used when
    deciding whether to apply a rule — showing the stored number would tell the
    user something PAAI does not believe any more.
    """
    return {"preferences": list_preferences_for_display(user_id)}


@router.delete("/preferences/{category}")
async def forget_preference(
    category: str,
    scope: str = "global",
    user_id: uuid.UUID = Depends(current_user),
):
    """
    Let the user remove something PAAI learned about them.

    Worth having even though the UI does not use it yet: an assistant that
    learns from you silently and offers no way to correct the record is a
    product people stop trusting. The passive extractor will occasionally get
    something wrong, and this is the fix.
    """
    existing = {
        (p["category"], p["scope"]) for p in list_preferences_for_display(user_id)
    }
    if (category, scope) not in existing:
        raise HTTPException(status_code=404, detail="Preference not found")

    delete_preference(user_id, category, scope)
    return {"status": "forgotten", "category": category, "scope": scope}
