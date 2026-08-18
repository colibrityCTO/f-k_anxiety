"""Configuration centrale, lue depuis l'environnement (12-factor / Railway)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
KNOWLEDGE_DIR = BACKEND_DIR / "knowledge"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Base de données -----------------------------------------------------
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/serenite",
        alias="DATABASE_URL",
    )
    db_pool_min: int = Field(default=1, alias="DB_POOL_MIN")
    db_pool_max: int = Field(default=10, alias="DB_POOL_MAX")

    # --- Auth ---------------------------------------------------------------
    jwt_secret: str = Field(default="dev-secret-a-changer", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60 * 24 * 30, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")

    # --- LLM ----------------------------------------------------------------
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-5", alias="ANTHROPIC_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    llm_max_tokens: int = Field(default=8000, alias="LLM_MAX_TOKENS")
    # Laissée vide par défaut : Claude Opus 5 et Sonnet 5 refusent `temperature`
    # (HTTP 400). Ne la renseigne que pour un modèle qui l'accepte encore.
    llm_temperature: float | None = Field(default=None, alias="LLM_TEMPERATURE")

    # --- Embeddings ---------------------------------------------------------
    embedding_model: str = Field(default="text-embedding-3-large", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=3072, alias="EMBEDDING_DIM")

    # --- Notifications push (Web Push / VAPID) ------------------------------
    # Générer une paire de clés : python -m app.vapid
    vapid_public_key: str | None = Field(default=None, alias="VAPID_PUBLIC_KEY")
    vapid_private_key: str | None = Field(default=None, alias="VAPID_PRIVATE_KEY")
    vapid_subject: str = Field(default="mailto:admin@example.org", alias="VAPID_SUBJECT")

    # --- Planificateur (rappels et bilan hebdomadaire) ----------------------
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    scheduler_interval_seconds: int = Field(default=60, alias="SCHEDULER_INTERVAL_SECONDS")

    # --- Divers -------------------------------------------------------------
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @field_validator("database_url")
    @classmethod
    def _normalise_scheme(cls, v: str) -> str:
        # Railway fournit parfois des URLs `postgres://`, que psycopg2 accepte,
        # mais on normalise pour rester cohérent avec SQLAlchemy/LangChain.
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.strip())

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @property
    def has_push(self) -> bool:
        """Sans paire VAPID, le push est impossible — et l'interface le dit."""
        return bool(
            self.vapid_public_key
            and self.vapid_public_key.strip()
            and self.vapid_private_key
            and self.vapid_private_key.strip()
        )

    @property
    def has_llm(self) -> bool:
        return self.has_anthropic or self.has_openai

    @property
    def has_embeddings(self) -> bool:
        """Les embeddings passent exclusivement par OpenAI text-embedding-3-large."""
        return self.has_openai


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
