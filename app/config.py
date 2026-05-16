from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/trufiq"
    SECRET_KEY: str = "change-me-in-production-please"
    OPENAI_API_KEY: Optional[str] = None
    # Azure OpenAI Service — alternativa privada a OpenAI consumer API.
    # Si estas tres variables están configuradas, se usa Azure en lugar de OpenAI.
    # Los datos NO se usan para entrenamiento y permanecen en la UE (GDPR).
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None            # ej. https://mi-recurso.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = None          # nombre del deployment de chat, ej. trufiq-chat
    AZURE_OPENAI_WHISPER_DEPLOYMENT: Optional[str] = None  # nombre del deployment de Whisper, ej. trufiq-whisper
    AZURE_OPENAI_WHISPER_ENDPOINT: Optional[str] = None    # si Whisper está en un recurso distinto
    AZURE_OPENAI_WHISPER_KEY: Optional[str] = None         # si Whisper tiene una API key distinta
    AEMET_API_KEY: Optional[str] = None
    AEMET_BASE_URL: str = "https://opendata.aemet.es/opendata/api"
    AEMET_TIMEOUT_SECONDS: float = 30.0

    # Email — Postmark (proveedor principal)
    POSTMARK_API_KEY: Optional[str] = None
    POSTMARK_FROM: str = "noreply@trufiq.app"

    # Email — SMTP (legado / fallback durante la transición)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@trufiq.app"
    SMTP_TLS: bool = True   # STARTTLS (puerto 587)
    SMTP_SSL: bool = False  # SSL directo (puerto 465)
    # Dirección de destino para notificaciones de leads. Si no se define, usa POSTMARK_FROM / SMTP_FROM.
    CONTACT_EMAIL: Optional[str] = None

    # App base URL (used to build confirmation/reset links)
    APP_BASE_URL: str = "http://localhost:8000"

    # If set, the user who registers with this email gets role=admin immediately
    ADMIN_EMAIL: Optional[str] = None

    # Stripe billing
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_ID_BASIC: Optional[str] = None
    STRIPE_PRICE_ID_PREMIUM: Optional[str] = None
    STRIPE_PRICE_ID_ENTERPRISE: Optional[str] = None
    TRIAL_DAYS: int = 30

    # Set to True in production so session cookies are Secure (HTTPS-only).
    # Keep False locally to allow HTTP dev server.
    PRODUCTION: bool = False

    # Observability
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: Optional[str] = None
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_RELEASE: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    @property
    def postmark_configured(self) -> bool:
        return bool(self.POSTMARK_API_KEY)

    @property
    def smtp_configured(self) -> bool:
        """
        Indica si la configuración SMTP es suficiente para enviar emails.

        - En entorno local (PRODUCTION=False), basta con definir SMTP_HOST (ideal para Mailhog, que no requiere autenticación).
        - En producción (PRODUCTION=True), se exige SMTP_HOST, SMTP_USER y SMTP_PASSWORD para evitar configuraciones inseguras.
        """
        if not self.PRODUCTION:
            # En local (desarrollo), solo se requiere el host para Mailhog.
            return bool(self.SMTP_HOST)
        # En producción, se requiere autenticación completa.
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)

    @property
    def email_configured(self) -> bool:
        """True when at least one email backend is ready to send."""
        return self.postmark_configured or self.smtp_configured

    @property
    def effective_from(self) -> str:
        """Sender address used by the active email backend."""
        return self.POSTMARK_FROM if self.postmark_configured else self.SMTP_FROM

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

    @model_validator(mode="after")
    def _validate_secret_key_in_production(self) -> "Settings":
        _INSECURE_DEFAULTS = {
            "change-me-in-production-please",
            "secret",
            "changeme",
            "insecure",
        }
        if self.PRODUCTION and (
            self.SECRET_KEY in _INSECURE_DEFAULTS or len(self.SECRET_KEY) < 32
        ):
            raise ValueError(
                "SECRET_KEY insegura en modo producción (PRODUCTION=true). "
                "Genera una con: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self


settings = Settings()
