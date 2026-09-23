"""
Central configuration. Replaces reading qwenkey.txt / credentials.json from disk.

Everything comes from environment variables so the app can be containerised
without baking secrets into the image. See .env.example for the full list.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://paai:paai_local@localhost:5432/paai"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # ── LLM ──────────────────────────────
    dashscope_api_key: str = ""
    # dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "gpt-4o-mini"

    # ── Embeddings ────────────────────────────────────────────────────────
    # Must stay in sync with the vector(N) column in models.py.
    # all-MiniLM-L6-v2 produces 384-dimensional vectors.
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ── Token encryption ──────────────────────────────────────────────────
    # Fernet key used to encrypt OAuth refresh tokens at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # ── Google OAuth (Phase 2 will use these; defined now so config is stable) ──
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    google_test_users: str = ""
    owner_email: str = ""

    # ── Dev convenience ───────────────────────────────────────────────────
    # Email of the single seeded user, used until Phase 2 adds real auth.
    dev_user_email: str = "dev@paai.local"
    jwt_secret: str = ""
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:8501"
    dev_mode: bool = True

    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    default_token_limit: int = 200_000
    llm_cheap: str = "gpt-4o-mini"
    llm_standard: str = "gpt-4o-mini"

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
