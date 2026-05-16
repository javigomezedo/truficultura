# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Trufiq — server-rendered FastAPI app for managing a truffle farm (parcelas/bancales, expenses, incomes, irrigation, wells, weather, rainfall, plants and per-plant truffle events, multi-campaign profitability and KPIs). Stripe-based billing with `basic` / `premium` / `enterprise` plans, multi-tenant organisations, and i18n (es/en/fr).

## Commands

The project uses `uv` for dependency and command management. Most commands assume you've run `uv sync` once.

```bash
# Full test suite (services + routers + integration + Stripe). Coverage threshold is enforced.
uv run pytest -q

# Subsets
uv run pytest -q tests/services/        # unit tests against a fake session
uv run pytest -q tests/integration/     # SQLite-backed integration tests
uv run pytest -q tests/test_<name>.py   # single file
uv run pytest -q tests/test_x.py::test_specific  # single test

# Local app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Local Postgres (docker compose) — exposes on :5433 with user/pass trufi/trufi, db trufiq
docker compose up -d db
# Matching DATABASE_URL: postgresql+asyncpg://trufi:trufi@localhost:5433/trufiq

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "<description>"
alembic downgrade -1

# Translations (Babel + gettext, locales/{es,en,fr}/LC_MESSAGES/messages.po)
pybabel extract -F babel.cfg -o locales/messages.pot .
pybabel update -i locales/messages.pot -d locales
pybabel compile -d locales

# Recurring / scheduled work (run by cron in prod; safe to invoke ad-hoc)
uv run scripts/process_recurring_expenses_cron.py [--dry-run]
uv run scripts/import_rainfall_cron.py [--dry-run]
uv run scripts/process_notifications_cron.py

# Seed data
uv run scripts/seed_full_demo.py
```

Test coverage is enforced via `pyproject.toml`: `--cov=app --cov-report=term-missing --cov-fail-under=82`. The full suite must pass before merging — CI also runs `alembic upgrade head` against an empty Postgres and builds the Docker image.

## Architecture

### Three-layer separation (do not skip layers)

```
app/routers/   →   app/services/   →   app/models/
```

- **Routers** (`app/routers/*.py`): HTTP only — read form/query params, call a service, return template or redirect. No SQL, no business rules.
- **Services** (`app/services/*.py`): all DB queries, aggregations, CRUD and business logic. Functions take an `AsyncSession` plus IDs and return plain Python data.
- **Models** (`app/models/*.py`): SQLAlchemy 2.0 declarative ORM. `Base` lives in `app/database.py`.
- **Schemas** (`app/schemas/*.py`): Pydantic v2 DTOs (used selectively — many forms map directly to model fields).

When adding a feature: write/extend the service first with tests, then wire the router. New router must be added to the imports and the `app.include_router(...)` list in `app/main.py`, and the `templates` attribute on the router module must be set in `app/main.py` (templates are constructed once in `app/jinja.py` and shared so all custom filters/globals are available).

### Multi-tenant data isolation (critical)

Every data table has a `tenant_id` column (added in migrations 0020–0022). **All queries for plots, expenses, incomes, irrigation, wells, plants, truffle events, rainfall, etc. must filter by `tenant_id`, not by `user_id`.**

- `user.active_tenant_id` is resolved on every request from the user's `TenantMembership` row (see `app/auth.py::get_current_user`). It is never stored on the session as authoritative state.
- A user belongs to exactly one tenant at any time; on register a personal "solo tenant" is created. Accepting an invitation deletes the solo tenant (if it has no Stripe customer) and adds the user to the inviting tenant. Being expelled recreates a fresh solo tenant.
- The Stripe subscription lives on `Tenant`, not `User`.
- App roles (`User.role`): `admin` | `user` — admins are never blocked by subscription/plan.
- Tenant roles (`TenantMembership.role`): `owner` | `admin` | `member`. The owner cannot be removed or downgraded.

The older `.github/copilot-instructions.md` still references filtering by `user_id` — that guidance is outdated. Trust the current schema and `tenant_id`.

### Plan-based feature gating

`app/plan_access.py` resolves the active plan mode and gates writes/features:

- Plan modes: `trial` | `basic` | `premium` | `enterprise` | `read_only`.
- `get_plan_mode(user)`: admin → `enterprise`; `trialing` with days left → `trial`; `active` + plan → that plan (or `basic` if missing); expired/`past_due`/`canceled` → `read_only`.
- Custom exceptions (`WriteAccessDeniedException`, `PlanUpgradeRequiredException`, `PlantLimitExceededException`, `OnboardingQuotaExceededException`) are raised from services/routers and translated to redirects in `app/main.py` exception handlers.
- Templates can call `session_plan_mode(session)` and `session_has_feature(session, "<feature>")` (registered in `app/jinja.py`) to hide/show UI based on the plan.

When adding a new gated feature, register it in `_FEATURE_PLANS` inside `app/plan_access.py`.

### Campaign year (May → April)

The whole business model pivots on a non-calendar agricultural year:

- `campaign_year(date)` in `app/utils.py` returns the start year (April 2026 → 2025; May 2025 → 2025).
- `campaign_label(year)` formats as `2025/26`; both are registered as Jinja filters.
- `distribute_unassigned_expenses()` in `app/utils.py` is the canonical way to spread `plot_id=None` expenses across plots using `plot.percentage`.
- `plot.percentage` is auto-recomputed by `plots_service` whenever a plot is created/updated/deleted — do not bypass it.

Never inline this logic; always use the helpers.

### Async DB + middleware

- `app/database.py` builds a single async engine with `NullPool` (Fly.io's proxy aggressively kills idle TCP connections, so pooled connections are unreliable). Each request gets its own session via `get_db()` and gets `commit()`/`rollback()` automatically in the dependency.
- `app/config.py::SQLALCHEMY_DATABASE_URL` normalizes URL schemes (`postgres://` and `postgresql://` → `postgresql+asyncpg://`) and translates `sslmode=require` → `ssl=require` so the same env var works on Fly and locally.
- Middlewares in `app/main.py` (executed inside-out): observability/metrics, recover-invalid-session-cookie (rewrites stale cookies to a `/login` redirect instead of 500), locale (sets a `ContextVar` from session/cookie/Accept-Language), security headers, and a CSRF Origin/Referer check that exempts `/billing/webhook` and `/health`.

### i18n / Jinja2 quirk

Templates use `jinja2.ext.i18n` with gettext callables installed in `app/jinja.py`. Because Jinja runs `%` formatting against the translated string, **any literal `%` in a translation string must be doubled to `%%`** — otherwise rendering raises `ValueError: unsupported format character`. Example: `{{ _("Porcentaje (%%)") }}`, not `{{ _("Porcentaje (%)") }}`.

The backend `_(...)` helper in `app/i18n.py` also supports `_("Texto con {var}", var=valor)` for safer interpolation.

When adding a new model/router/service/feature, also update `app/services/assistant_service.py` so the in-app AI assistant can answer questions about it (see `.github/instructions/assistant.instructions.md` for which structures — `_APP_KNOWLEDGE`, `_DATA_KEYWORDS`, `_DATA_PATTERNS`, `_SOURCES_DATA`, `_build_user_context` — to extend).

## Testing patterns

- **Unit tests** under `tests/services/` mock the async session using `tests/conftest.py::result()` returning a `FakeExecuteResult`. Do **not** use `AsyncMock` directly for the session — the fake implements `.scalars().all()`, `.scalar_one_or_none()` and `.scalar()` to match SQLAlchemy 2.0 result shapes:

  ```python
  from unittest.mock import AsyncMock, MagicMock
  from tests.conftest import result

  db = MagicMock()
  db.execute = AsyncMock(return_value=result([obj1, obj2]))
  db.flush = AsyncMock()
  db.delete = AsyncMock()
  ```

- **Integration tests** under `tests/integration/` spin up a real async engine against `sqlite+aiosqlite:///:memory:`, create the schema with `Base.metadata.create_all`, and exercise services end-to-end (multi-tenant flows, dashboard aggregation, charts context).
- Every async test must be decorated with `@pytest.mark.asyncio`.
- New service functions need tests before they merge — see `.github/instructions/services.instructions.md` for the minimum-cases table.

## Environment

- Copy `.env.example` → `.env` and fill at minimum `DATABASE_URL` and `SECRET_KEY`. In production (`PRODUCTION=true`) the config validator rejects the default/short `SECRET_KEY` at startup.
- Optional integrations that the app boots without: Stripe, Postmark/SMTP, Sentry, AEMET, Azure/OpenAI, Prometheus token. Each has a `*_configured` property on `settings`.
- `METRICS_ENABLED=1` requires `METRICS_TOKEN` to be set; the lifespan hook fails fast otherwise to avoid exposing `/metrics` publicly.
