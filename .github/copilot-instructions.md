# Truficultura — Copilot Instructions

Web application for managing a truffle farm: plots, expenses, incomes, profitability by agricultural campaign, and charts.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| ORM | SQLAlchemy 2.x (async) |
| DB driver | asyncpg |
| Database | PostgreSQL |
| Migrations | Alembic |
| Config | Pydantic Settings (`app/config.py`) |
| Templates | Jinja2 + Bootstrap 5 |
| Charts | Chart.js |
| Auth | Sessions via `itsdangerous`, passwords via `passlib[argon2]` |
| Package manager | **uv** (preferred) |

---

## Architecture

Strict three-layer separation — never skip layers:

```
routers/  →  services/  →  models/
```

- **Routers** (`app/routers/`): HTTP orchestration only — read params, call service, render template or redirect. No business logic.
- **Services** (`app/services/`): all business logic, DB queries, aggregations, and CRUD.
- **Models** (`app/models/`): SQLAlchemy ORM definitions.
- **Schemas** (`app/schemas/`): Pydantic DTOs for input validation.

When adding a feature: create/extend the service first, then wire up the router.

---

## Key Business Rules

### Agricultural campaign (May-April)
- `campaign_year(date)` → `app/utils.py`: returns the campaign start year.
  - May 2025 → 2025; April 2026 → **2025** (not 2026).
- `campaign_label(year)` formats as `"2025/26"`.
- Always use these helpers; never inline the logic.

### Unassigned-expense distribution
- Expenses with `plot_id = None` are general expenses distributed among all plots proportionally via `plot.percentage`.
- `percentage` is auto-recalculated whenever a plot is created, updated, or deleted: `(num_plants / total_user_plants) * 100`.
- Use `distribute_unassigned_expenses()` from `app/utils.py` for this.

### Income totals
- `total = amount_kg * euros_per_kg` (never stored redundantly; compute on read or in the model).

### Multi-tenancy
- Every query **must** filter by `user_id`. Users see only their own data.
- Roles: `admin` (full access + user management at `/admin/users`) and `user` (own data only).
- First registered user becomes admin automatically.

---

## Testing Conventions

- **Unit tests** (`tests/services/`): mock the async DB session with `FakeExecuteResult` from `tests/conftest.py`. No real DB required.
- **Integration tests** (`tests/integration/`): use SQLite via `aiosqlite`; real async engine created by pytest fixture.
- Do **not** use `AsyncMock` for sessions — use the project's `FakeExecuteResult` / `result()` pattern from `conftest.py`.
- Target: keep all 58+ tests green. Run the full suite after any change.

---

## Migrations

- Files in `alembic/versions/`, named `NNNN_description.py`.
- Always write both `upgrade()` and `downgrade()`.
- After changing a model, run `alembic revision --autogenerate`, review the generated file, then `alembic upgrade head`.

---

## Templates & Frontend

- All templates extend `app/templates/base.html`.
- Use Bootstrap 5 classes and Bootstrap Icons for UI consistency.
- Spanish is the UI language. Template folder names are in Spanish (`gastos/`, `ingresos/`, `parcelas/`).
- Pass data to charts as JSON-serialised Python dicts; Chart.js reads them client-side.
- Jinja filters: `campaign_label` is registered in `app/jinja.py`.

---

## Environment & Config

- Copy `.env.example` → `.env` and set `DATABASE_URL` and `SECRET_KEY`.
- `app/config.py` exposes a singleton `settings` via `pydantic_settings`.
- Never hardcode credentials or secrets; always read from `settings`.

---

## Pitfalls to Avoid

- **Forgetting `user_id` filters**: every DB query for plots/expenses/incomes must include `where(Model.user_id == current_user.id)`.
- **Inline campaign logic**: always use `campaign_year()` and `campaign_label()` from `app/utils.py`.
- **Sync SQLAlchemy in async context**: all DB operations must use `await session.execute(...)`. Never mix sync and async sessions.
- **Percentage drift**: after any plot mutation, call the recalculate-percentages helper in `plots_service.py` — don't skip it.
- **CSV import format**: semicolon-delimited, European number format (`1.250,50`), dates as `dd/mm/yyyy`.
