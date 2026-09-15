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

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from paai.graph import run_agent
from paai.db import init_db, _engine
from paai.context import user_context


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


# ── User identity ─────────────────────────────────────────────────────────────
def current_user() -> uuid.UUID:
    """
    PHASE 2 REPLACES THIS FUNCTION AND NOTHING ELSE.

    It becomes roughly:

        async def current_user(
            creds: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
        ) -> uuid.UUID:
            claims = verify_jwt(creds.credentials)
            return get_or_create_user_from_claims(claims)
    """
    raw = os.environ.get("DEV_USER_ID")
    if not raw:
        raise HTTPException(
            status_code=500,
            detail=(
                "DEV_USER_ID is not set. Seed a user and add its UUID to .env:\n"
                "  python -c \"from db import get_or_create_user; "
                "from config import settings; "
                "print(get_or_create_user(settings.dev_user_email))\""
            ),
        )
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=500, detail="DEV_USER_ID is not a valid UUID")


# ── Schemas ───────────────────────────────────────────────────────────────────
class AgentRequest(BaseModel):
    query: str
    session_id: str | None = None


class AgentResponse(BaseModel):
    response: str
    session_id: str


# ── Routes ────────────────────────────────────────────────────────────────────
@app.post("/agent", response_model=AgentResponse)
async def call_agent(
    request: AgentRequest,
    user_id: uuid.UUID = Depends(current_user),
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent failed: {exc}")

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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)