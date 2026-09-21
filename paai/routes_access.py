"""
Google tester access — request and approve.

The request endpoint is for any signed-in user. The admin endpoints are owner
only, checked against settings.owner_email rather than a role column, because
one owner is the whole access model right now and a roles table would be
ceremony without benefit.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from paai.access import (
    APPROVED,
    DENIED,
    PENDING,
    is_owner,
    list_requests,
    remove,
    request_access,
    set_status,
)
from paai.config import settings
from paai.db import get_user_by_id
from paai.deps import current_user

router = APIRouter(prefix="/access", tags=["access"])


def _require_owner(user_id: uuid.UUID) -> str:
    user = get_user_by_id(user_id)
    if not user or not is_owner(user.email):
        # 404 rather than 403: no reason to confirm these endpoints exist to
        # anyone who is not the owner.
        raise HTTPException(status_code=404, detail="Not found")
    return user.email


class AccessRequest(BaseModel):
    note: str | None = None


class StatusChange(BaseModel):
    email: str
    status: str


# ── For any signed-in user ────────────────────────────────────────────────────
@router.post("/google/request")
async def request_google_access(
    body: AccessRequest, user_id: uuid.UUID = Depends(current_user)
):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = request_access(user_id, user.email, note=body.note)
    return {
        **result,
        "email": user.email,
        "owner_email": settings.owner_email,
        "message": (
            "Request recorded. Gmail access opens once the owner adds this "
            "address in Google Cloud Console."
        ),
    }


# ── Owner only ────────────────────────────────────────────────────────────────
@router.get("/google/requests")
async def google_requests(
    status: str | None = None, user_id: uuid.UUID = Depends(current_user)
):
    _require_owner(user_id)
    return {"requests": list_requests(status)}


@router.post("/google/status")
async def change_status(
    body: StatusChange, user_id: uuid.UUID = Depends(current_user)
):
    _require_owner(user_id)

    if body.status not in (PENDING, APPROVED, DENIED):
        raise HTTPException(status_code=400, detail="Invalid status")

    set_status(body.email, body.status)
    return {
        "email": body.email.lower(),
        "status": body.status,
        "reminder": (
            "Also add this address under Google Auth Platform -> Audience -> "
            "Test users, or Google will still refuse the consent."
            if body.status == APPROVED
            else None
        ),
    }


@router.delete("/google/{email}")
async def delete_request(email: str, user_id: uuid.UUID = Depends(current_user)):
    _require_owner(user_id)
    if not remove(email):
        raise HTTPException(status_code=404, detail="No such request")
    return {"status": "removed", "email": email.lower()}