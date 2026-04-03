from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/truficultura"
    SECRET_KEY: str = "change-me-in-production-please"

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """Normalize DB URL schemes so Fly/local envs work with async SQLAlchemy.

        Fly often injects DATABASE_URL as postgres://... and may include
        sslmode query params which asyncpg does not accept.
        """
        raw_url = self.DATABASE_URL.strip().strip("'\"")
        normalized_lower = raw_url.lower()

        if normalized_lower.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif normalized_lower.startswith("postgresql://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        parts = urlsplit(raw_url)
        query_items = parse_qsl(parts.query, keep_blank_values=True)
        transformed_items = []
        sslmode_value = None

        for key, value in query_items:
            if key.lower() == "sslmode":
                sslmode_value = value.lower()
                continue
            transformed_items.append((key, value))

        if sslmode_value is not None and not any(
            key.lower() == "ssl" for key, _ in transformed_items
        ):
            ssl_value = "true"
            if sslmode_value in {"disable", "allow"}:
                ssl_value = "false"
            transformed_items.append(("ssl", ssl_value))

        rebuilt_query = urlencode(transformed_items, doseq=True)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, rebuilt_query, parts.fragment)
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
