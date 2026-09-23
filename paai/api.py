"""
FastAPI entrypoint.

The only place in the codebase where a user identity is produced.

Today it reads DEV_USER_ID from the environment. In Phase 2, `current_user`
becomes a dependency that validates a bearer token and returns a user id —
and nothing downstream changes, because everything already reads from context.
"""
import os
import uuid
from contextlib import asynccontextmanager

from fastapi.concurrency import run_in_threadpool
from starlette.concurrency import run_in_threadpool
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from paai.usage import QuotaExceeded, summary

from paai.graph import run_agent
from paai.db import init_db, _engine
from paai.context import user_context
from paai.routes_auth import router as auth_router
from paai.routes_sessions import router as sessions_router
from paai.routes_profile import router as profile_router
from paai.deps import current_user, require_mailbox
from fastapi.middleware.cors import CORSMiddleware
from paai.config import settings
from paai.routes_access import router as access_router


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Was a module-level init_db() call in agentic_framework.py, which meant
    # importing the module opened a database connection as a side effect —
    # so the import failed outright if Postgres wasn't up. Startup is where
    # this belongs.
    init_db()
    yield


app = FastAPI(title="PAAI", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(profile_router)
app.include_router(access_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],   # exact origin, never "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Schemas ───────────────────────────────────────────────────────────────────
class AgentRequest(BaseModel):
    query: str
    session_id: str | None = None


class AgentResponse(BaseModel):
    response: str
    session_id: str
    plan: list[dict] = []

# ── Routes ────────────────────────────────────────────────────────────────────
@app.post("/agent", response_model=AgentResponse)
async def call_agent(
    request: AgentRequest,
    user_id: uuid.UUID = Depends(current_user),
    mailbox_id: str = Depends(require_mailbox),
) -> AgentResponse:
    """
    run_agent is synchronous and does blocking LLM calls, so it must not run
    on the event loop — that would stall every other in-flight request.
    run_in_threadpool offloads it, and copy_context() carries the ContextVar
    across the thread boundary (a plain thread would not see it).
    """
    from starlette.concurrency import run_in_threadpool

    def _run():
        with user_context(user_id):
            return run_agent(request.query, session_id=request.session_id)

    try:
        result, session_id = await run_in_threadpool(_run)
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exceeded",
                "message": str(exc),
                "used": exc.used,
                "limit": exc.limit,
            },
        )

    return AgentResponse(response=result, session_id=session_id)


@app.get("/health")
async def health_check():
    """Liveness probe. Kept dependency-free so it stays up even if auth breaks."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness_check():
    """
    Readiness probe — checks the database too. This is the one your hosting
    platform should poll in Phase 3; /health alone would report healthy while
    every request 500s on a dead database.
    """
    from sqlalchemy import text

    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")


@app.get("/usage")
async def usage(user_id: uuid.UUID = Depends(current_user)):
    return summary(user_id)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)