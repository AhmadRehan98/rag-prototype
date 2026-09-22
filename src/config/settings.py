"""App settings"""

from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for local Enterprise Knowledge RAG platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base paths
    PROJECT_ROOT: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent
    )

    # Database settings
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_prototype"
    )
    SYNC_DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/rag_prototype"
    )

    # Data paths relative to PROJECT_ROOT
    CORPUS_JSONL_PATH: Path = Field(
        default_factory=lambda: Path("data/normalized/corpus.jsonl")
    )
    IDENTITIES_JSON_PATH: Path = Field(
        default_factory=lambda: Path("data/access/identities.json")
    )
    ENTITLEMENTS_JSON_PATH: Path = Field(
        default_factory=lambda: Path("data/access/entitlements.json")
    )

    # Security & Logging
    ENABLE_SAFE_LOGGING: bool = True
    LOG_LEVEL: str = "INFO"

    @property
    def sync_database_url(self) -> str:
        """Return synchronous database URL suitable for Alembic or sync engines."""
        if self.SYNC_DATABASE_URL:
            return self.SYNC_DATABASE_URL
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    def resolve_path(self, path: Path | str) -> Path:
        """Resolve path against project root if relative."""
        p = Path(path)
        if not p.is_absolute():
            return self.PROJECT_ROOT / p
        return p


# Global settings singleton
settings = Settings()
