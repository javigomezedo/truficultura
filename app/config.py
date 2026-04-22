from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/truficultura"
    SECRET_KEY: str = "change-me-in-production-please"
    OPENAI_API_KEY: Optional[str] = None
    AEMET_API_KEY: Optional[str] = None
    AEMET_BASE_URL: str = "https://opendata.aemet.es/opendata/api"
    AEMET_TIMEOUT_SECONDS: float = 30.0

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """Normalize DB URL schemes so Fly/local envs work with async SQLAlchemy.

        Fly often injects DATABASE_URL as postgres://... while this app uses
        SQLAlchemy async engine with asyncpg.
        """
        raw_url = self.DATABASE_URL.strip().strip("'\"")
        normalized_lower = raw_url.lower()

        if normalized_lower.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif normalized_lower.startswith("postgresql://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        parts = urlsplit(raw_url)
        query_items = parse_qsl(parts.query, keep_blank_values=True)
        normalized_items = []
        normalized_ssl = None

        for key, value in query_items:
            lowered_key = key.lower()
            lowered_value = value.lower()

            if lowered_key in {"sslmode", "ssl"}:
                if lowered_value in {
                    "require",
                    "verify-ca",
                    "verify-full",
                    "true",
                    "1",
                    "yes",
                    "on",
                }:
                    normalized_ssl = "require"
                else:
                    normalized_ssl = "disable"
                continue

            normalized_items.append((key, value))

        if normalized_ssl is not None:
            normalized_items.append(("ssl", normalized_ssl))

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(normalized_items, doseq=True),
                parts.fragment,
            )
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
