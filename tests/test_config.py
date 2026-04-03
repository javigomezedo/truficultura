from app.config import Settings


def test_sqlalchemy_database_url_normalizes_postgres_scheme():
    settings = Settings(
        DATABASE_URL="postgres://user:pass@db.internal:5432/appdb?sslmode=require",
        SECRET_KEY="secret",
    )

    # sslmode=require → ssl=require; scheme normalized
    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?ssl=require"
    )


def test_sqlalchemy_database_url_trims_wrapping_quotes():
    settings = Settings(
        DATABASE_URL="'postgresql://user:pass@db.internal:5432/appdb?sslmode=require'",
        SECRET_KEY="secret",
    )

    # sslmode=require → ssl=require; quotes stripped; scheme normalized
    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?ssl=require"
    )


def test_sqlalchemy_database_url_normalizes_boolean_sslmode_true():
    settings = Settings(
        DATABASE_URL="postgres://user:pass@db.internal:5432/appdb?sslmode=true",
        SECRET_KEY="secret",
    )

    # boolean sslmode=true → ssl=require
    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?ssl=require"
    )


def test_sqlalchemy_database_url_normalizes_boolean_sslmode_false():
    settings = Settings(
        DATABASE_URL="postgres://user:pass@db.internal:5432/appdb?sslmode=false",
        SECRET_KEY="secret",
    )

    # boolean sslmode=false → ssl=disable
    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?ssl=disable"
    )


def test_sqlalchemy_database_url_sslmode_disable():
    settings = Settings(
        DATABASE_URL="postgres://user:pass@db.internal:5432/appdb?sslmode=disable",
        SECRET_KEY="secret",
    )

    assert (
        settings.SQLALCHEMY_DATABASE_URL
        == "postgresql+asyncpg://user:pass@db.internal:5432/appdb?ssl=disable"
    )


def test_sqlalchemy_database_url_removes_sslmode_key():
    settings = Settings(
        DATABASE_URL="postgres://user:pass@db.internal:5432/appdb?sslmode=require&connect_timeout=10",
        SECRET_KEY="secret",
    )

    assert "sslmode=" not in settings.SQLALCHEMY_DATABASE_URL
    assert settings.SQLALCHEMY_DATABASE_URL.endswith("connect_timeout=10&ssl=require")
