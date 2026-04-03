from app.config import Settings


def test_sqlalchemy_database_url_normalizes_postgres_scheme():
    settings = Settings(
        DATABASE_URL="postgres://user:pass@db.internal:5432/appdb?sslmode=require",
        SECRET_KEY="secret",
    )

    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?sslmode=require"
    )


def test_sqlalchemy_database_url_trims_wrapping_quotes():
    settings = Settings(
        DATABASE_URL="'postgresql://user:pass@db.internal:5432/appdb?sslmode=require'",
        SECRET_KEY="secret",
    )

    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?sslmode=require"
    )
