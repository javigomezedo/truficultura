# Plan: Brulé (zona quemada) tracking feature

## TL;DR
New module to record the brulé diameter (cm, integer) per plant and date (free date, user chooses),
visualize temporal evolution per plant, and correlate with truffle production per campaign.
Entry point: both from the plant map and a dedicated /brule/ section.
Correlation: scatter plot + comparison table.

---

## Phase 1 — Data layer

**Step 1 — Model `BruleRecord`** (`app/models/brule.py`)
Fields (following PlantPresence pattern):
- `id` Integer PK
- `tenant_id` FK → tenants.id CASCADE (nullable for migration compat)
- `created_by_user_id` FK → users.id SET NULL
- `plot_id` FK → plots.id CASCADE (denormalized, like PlantPresence)
- `plant_id` FK → plants.id CASCADE
- `record_date` Date
- `diameter_cm` Integer
Unique constraint: `(plant_id, record_date)` — one measurement per plant per day
Indexes: `(tenant_id, plot_id)`, `(tenant_id, plot_id, record_date)`, `(plant_id, record_date)`

Export from `app/models/__init__.py`.

**Step 2 — Migration `0029_add_brule_records.py`**
`upgrade()`: create table + indexes
`downgrade()`: drop table (indexes auto-dropped)

**Step 3 — Schema (optional Pydantic DTO)**
No Pydantic schema needed — use form fields directly (like plants feature).

---

## Phase 2 — Service layer

**Step 4 — `app/services/brule_service.py`** (new file)
Functions:
- `list_brule_records(db, tenant_id, *, plot_id=None, plant_id=None, campaign=None)` → list[BruleRecord]
  - filter by tenant_id always; optionally by plot_id, plant_id, campaign_year(record_date)
- `get_brule_record(db, record_id, tenant_id)` → BruleRecord | None
- `create_brule_record(db, tenant_id, plant_id, plot_id, record_date, diameter_cm, user_id)` → BruleRecord
  - upsert or raise if (plant_id, record_date) already exists
- `update_brule_record(db, record_id, tenant_id, *, diameter_cm)` → BruleRecord
- `delete_brule_record(db, record_id, tenant_id)` → None
- `get_brule_evolution(db, tenant_id, plant_id)` → list[tuple[date, int]]
  - ordered by record_date ASC — for Chart.js line chart
- `get_last_brule_by_plant(db, tenant_id, plot_id)` → dict[int, int]
  - returns {plant_id: diameter_cm} for the most recent record per plant in a plot
  - used by the plant map to show last known brulé
- `get_brule_production_correlation(db, tenant_id, *, plot_id=None, campaign=None)`
  → list[dict] with keys: plant_id, plant_label, plot_label, last_diameter_cm, total_weight_kg
  - last brulé diameter (most recent record regardless of date)
  - total production: sum of TruffleEvent.estimated_weight_grams (non-undone) converted to kg
  - only include plants that have at least one brulé record AND at least one truffle event in campaign

---

## Phase 3 — Router

**Step 5 — `app/routers/brule.py`** (new file)
Routes:
- `GET /brule/` — list all brulé records for tenant, filterable by plot + campaign
  → template `brule/list.html`
- `GET /brule/correlacion` — correlation scatter + table
  → template `brule/correlacion.html`
- `GET /plots/{plot_id}/plants/{plant_id}/brule/` — temporal evolution per plant
  → template `brule/planta.html`
- `POST /plots/{plot_id}/plants/{plant_id}/brule/` — create record (form: record_date, diameter_cm)
  → redirect to same plant brulé page (303)
- `GET /brule/{record_id}/edit` — edit form
  → template `brule/edit.html`
- `POST /brule/{record_id}/edit` — update diameter
  → redirect to plant brulé page (303)
- `POST /brule/{record_id}/delete` — delete record
  → redirect to referrer or list (303)

Auth: `require_subscription` for reads, `require_write_access` for mutations.
All queries pass `current_user.active_tenant_id` as `tenant_id`.

Register router in `app/main.py` with `router.include_router(brule_router)`.

---

## Phase 4 — Plant Map Integration

**Step 6 — Enrich map with last brulé data**
In `app/routers/plants.py`, in the `GET /plots/{plot_id}/map` handler:
- After calling `plants_service.get_plot_map_context(...)`, call
  `brule_service.get_last_brule_by_plant(db, tenant_id, plot_id)`
- Pass `last_brule_by_plant` dict to the template context

In `app/templates/parcelas/mapa.html`:
- In the per-plant cell, show last brulé diameter badge: "⌀ {N} cm" if present
- In the per-plant summary table (below the grid), add a "Último brulé" column
- Add a small button/link "Ver brulé" → `/plots/{plot_id}/plants/{plant_id}/brule/`

---

## Phase 5 — Templates

**Step 7 — `app/templates/brule/`** (new directory with 4 templates)

`brule/list.html`:
- Extends `base.html`
- Filter bar: plot selector (dropdown), campaign selector
- Table: fecha, parcela, planta, diámetro (cm)
- Quick-add form inline or button → plant brulé page

`brule/planta.html`:
- Extends `base.html`
- Breadcrumb: Parcela → Mapa → Planta → Brulé
- Chart.js line chart: x=date, y=diameter_cm (pattern from `graficas/index.html`)
- Table of records with delete button
- Form to add new record (record_date + diameter_cm)

`brule/correlacion.html`:
- Extends `base.html`
- Filter: plot selector, campaign selector
- Chart.js scatter plot: x=diameter_cm, y=total_weight_kg, one point per plant (labeled)
- Table: plant_label, plot_label, último brulé (cm), producción campaña (kg)

`brule/edit.html`:
- Simple edit form for diameter_cm (+ display record_date read-only)

---

## Phase 6 — Navigation

**Step 8 — `app/templates/base.html`**
Add "Brulé" to the "Campo" dropdown:
```
<a class="dropdown-item {% if '/brule' in request.url.path %}active{% endif %}" href="/brule/">
    <i class="bi bi-circle text-warning me-1"></i> {{ _("Brulé") }}
</a>
```
Update the "Campo" parent active condition to include `'/brule' in request.url.path`.

---

## Phase 7 — Tests

**Step 9 — `tests/test_brule_service.py`** (new, unit tests)
Use FakeExecuteResult pattern from `tests/conftest.py`.
Cover: create, list with filters, get_evolution, get_last_brule_by_plant, correlation.

**Step 10 — `tests/test_brule_router.py`** (new, router tests)
Use monkeypatch + SimpleNamespace + AsyncMock pattern.
Cover: list view, plant brulé view, create record (POST), correlation view.

---

## Files to create/modify

New files:
- `app/models/brule.py`
- `alembic/versions/0029_add_brule_records.py`
- `app/services/brule_service.py`
- `app/routers/brule.py`
- `app/templates/brule/list.html`
- `app/templates/brule/planta.html`
- `app/templates/brule/correlacion.html`
- `app/templates/brule/edit.html`
- `tests/test_brule_service.py`
- `tests/test_brule_router.py`

Modified files:
- `app/models/__init__.py` — export BruleRecord
- `app/main.py` — register brule router
- `app/routers/plants.py` — enrich map context with last_brule_by_plant
- `app/templates/parcelas/mapa.html` — show brulé badge + link in plant cells/table
- `app/templates/base.html` — add Brulé to Campo nav dropdown

---

## Verification
1. Run `pytest tests/test_brule_service.py tests/test_brule_router.py -v` — all new tests green
2. Run `pytest` (full suite, 58+ tests) — no regressions
3. Run `alembic upgrade head` — migration applies cleanly
4. Manual: register a brulé record from the map, verify it appears in the plant evolution chart
5. Manual: add multiple records per plant over dates, verify the line chart shows correct evolution
6. Manual: check correlation view with plants that have both brulé records and truffle events

---

## Decisions
- `diameter_cm` stored as Integer (cm, no decimals)
- Unique constraint per (plant_id, record_date) — one measurement per plant per day
- Correlation uses "last recorded diameter ever" (not campaign-scoped) vs production in selected campaign
- Multi-tenancy via `tenant_id` (not `user_id`) — consistent with migration 0020+
- No Pydantic schema (form fields directly, like plants feature)
- No QR/scan integration for brulé (out of scope)
- No i18n translation strings added (out of scope for this plan, but key UI strings should use `_()`)
