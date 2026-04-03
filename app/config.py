from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/truficultura"
    SECRET_KEY: str = "change-me-in-production-please"

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

        for key, value in query_items:
            if key.lower() == "sslmode":
                # asyncpg does not accept sslmode; convert to ssl=true/false
                lowered = value.lower()
                if lowered in {
                    "require",
                    "verify-ca",
                    "verify-full",
                    "true",
                    "1",
                    "yes",
                    "on",
                }:
                    normalized_items.append(("ssl", "true"))
                else:
                    # disable / allow / prefer / false / 0 / no / off → no SSL
                    normalized_items.append(("ssl", "false"))
                continue
            normalized_items.append((key, value))

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
    )


settings = Settings()
