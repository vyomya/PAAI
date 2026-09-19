# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build deps for psycopg and sentence-transformers wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Where sentence-transformers caches the embedding model. Baking it into the
    # image means a cold start does not spend 30s downloading 90MB from
    # HuggingFace — and does not fail outright if HF is having a bad day.
    HF_HOME=/opt/models \
    SENTENCE_TRANSFORMERS_HOME=/opt/models

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

# Pre-download the embedding model at build time, not first request.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')" \
    && chmod -R a+rX /opt/models

COPY paai/ ./paai/
COPY migrations/ ./migrations/
COPY alembic.ini pyproject.toml ./

# Non-root: if the app is ever compromised, the blast radius is smaller.
RUN useradd --create-home --uid 10001 paai && chown -R paai:paai /app
USER paai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Workers: run_agent is synchronous and blocking, so concurrency comes from
# processes, not async. 2 is right for a small instance; raise with RAM, but
# note each worker loads its own copy of the embedding model (~90MB).
CMD ["sh", "-c", "alembic upgrade head && uvicorn paai.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
