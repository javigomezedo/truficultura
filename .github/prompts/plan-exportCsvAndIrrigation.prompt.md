# Plan: CSV Export Feature (+ Riego import/export + has_irrigation in plots)

## TL;DR
Add a CSV export feature mirroring the existing import functionality. New "Exportar" menu item → page with 4 tabs (Parcelas, Gastos, Ingresos, Riego) → each tab has a download button that triggers a `GET` endpoint and streams a CSV file in the exact same format accepted by the importer. Also: extend the plots CSV (both import and export) to include `has_irrigation` as column 11, and add a new "Riego" tab to the existing import page.

---

## CSV Formats (must match import format exactly)
- Semicolon-delimited, no header row, UTF-8
- Dates: DD/MM/YYYY
- Numbers: European format (`,` as decimal separator)
- **Parcelas** (11 cols): `nombre;fecha_plantacion;poligono;parcela;ref_catastral;hidrante;sector;n_plantas;superficie_ha;inicio_produccion;tiene_riego`
  - `tiene_riego`: `1` or `0` (empty = `0`)
- **Gastos**: `fecha;concepto;persona;bancal;cantidad;categoria`
- **Ingresos**: `fecha;bancal;kg;categoria;euros_kg`
- **Riego** (4 cols): `fecha;bancal;agua_m3;notas`
  - `bancal`: plot name (required — irrigation always requires a plot)
  - `agua_m3`: float EU format
  - `notas`: optional free text
  - `expense_id` link NOT included (internal FK, not portable across imports)

---

## Steps

### Phase 0 — Extend plots CSV format (has_irrigation)

1. Edit `app/services/import_service.py` → `import_plots_csv()`:
   - Read optional column index 10 as `tiene_riego` → `bool(_parse_int(col(10)) != 0)`
   - Set `has_irrigation=tiene_riego` on the created `Plot` object
   - The existing parsing loop already uses `col(n)` helper which returns `""` for missing columns — no row breakage for old CSVs that lack column 11

2. Update unit test `tests/services/test_plots_service.py` (or `test_import_service.py` if it exists) — add:
   - `test_import_plots_csv_has_irrigation_true` — column 11 = "1" → `has_irrigation=True`
   - `test_import_plots_csv_has_irrigation_false` — column 11 = "0" → `has_irrigation=False`
   - `test_import_plots_csv_has_irrigation_missing` — no column 11 → `has_irrigation=False` (backward compatible)

### Phase 1 — Service layer (export + irrigation import)

3. Create `app/services/export_service.py` with:
   - `_format_date(d) -> str` helper: `d.strftime("%d/%m/%Y")`
   - `_format_num(val, decimals=2) -> str` helper: format to N decimals, replace `.` with `,`
   - `_load_plots_by_id(db, user_id) -> dict[int, str]` helper: `{plot.id: plot.name}` (inverse of `_load_plots` from import_service, keyed by id)
   - `export_plots_csv(db, user_id) -> bytes`: SELECT all user plots ordered by name → write 11-column rows (including `1`/`0` for `has_irrigation`)
   - `export_expenses_csv(db, user_id) -> bytes`: SELECT all user expenses ordered by date → resolve plot name → write 6-column rows
   - `export_incomes_csv(db, user_id) -> bytes`: SELECT all user incomes ordered by date → resolve plot name → write 5-column rows
   - `export_irrigation_csv(db, user_id) -> bytes`: SELECT all user irrigation records ordered by date → resolve plot name → write 4-column rows (`fecha;bancal;agua_m3;notas`)

4. Add `import_irrigation_csv(db, content, user_id)` to `app/services/import_service.py`:
   - Format: `fecha;bancal;agua_m3[;notas]` (4 columns, notas optional)
   - Resolves bancal → plot_id via `_load_plots(db, user_id)` (reuse existing helper)
   - If bancal not found → warning, row skipped (irrigation **requires** a plot)
   - If plot found but `has_irrigation=False` → warning, row skipped (validate the business rule)
   - Creates `IrrigationRecord(user_id=..., plot_id=..., date=..., water_m3=..., notes=...)` — `expense_id` always `None`
   - Returns `(rows, warnings)` tuple like other import functions

5. Create `tests/services/test_export_service.py` with unit tests using `FakeExecuteResult` pattern:
   - `test_export_plots_csv_returns_correct_rows` — verifies 11 columns, date format, EU numbers, has_irrigation as `1`/`0`
   - `test_export_plots_csv_empty`
   - `test_export_expenses_csv_with_plot`, `_general_expense`, `_empty`
   - `test_export_incomes_csv_with_plot`, `_no_plot`, `_empty`
   - `test_export_irrigation_csv_with_data` — verifies fecha, bancal name, agua_m3 EU format, notas
   - `test_export_irrigation_csv_no_notes` — notas column empty
   - `test_export_irrigation_csv_empty`

6. Add tests for `import_irrigation_csv` in `tests/services/` (new file or append to existing import service tests):
   - `test_import_irrigation_csv_success` — valid row with existing plot with `has_irrigation=True`
   - `test_import_irrigation_csv_plot_not_found` — warning, row skipped
   - `test_import_irrigation_csv_plot_no_irrigation` — `has_irrigation=False` → warning, row skipped
   - `test_import_irrigation_csv_missing_notas` — 3-column row, notas = None

### Phase 2 — Router (export + add irrigation to import)

7. Edit `app/routers/imports.py` — add new endpoint:
   - `POST /import/irrigation` → reads file, calls `import_irrigation_csv`, commits, renders `imports/index.html` with `result` dict and `active_tab="irrigation"`

8. Create `app/routers/exports.py` with prefix `/export`:
   - `GET /export/` → renders `exports/index.html`
   - `GET /export/plots.csv` → `StreamingResponse`, `filename=parcelas.csv`
   - `GET /export/expenses.csv` → `filename=gastos.csv`
   - `GET /export/incomes.csv` → `filename=ingresos.csv`
   - `GET /export/irrigation.csv` → `filename=riego.csv`
   - All use `require_user` + `get_db`; pattern from `app/routers/expenses.py` lines 219–237

9. Register new router in `app/main.py` after `imports.router`

### Phase 3 — Templates & Navigation

10. Edit `app/templates/imports/index.html` — add 4th tab "Riego":
    - Tab button: `bi-droplet-fill text-primary`, label "Riego"
    - Left card: CSV format doc (4 columns: fecha, bancal, agua_m3, notas)
    - Right card: file upload form `POST /import/irrigation`
    - Active logic: `{% if not active_tab or active_tab == 'plots' %}` unchanged; new tab `active_tab == 'irrigation'`

11. Create `app/templates/exports/index.html` extending `base.html`:
    - 4 Bootstrap nav-tabs: Parcelas, Gastos, Ingresos, Riego
    - Each tab: description card + `<a href="/export/xxx.csv" class="btn btn-success"><i class="bi bi-download"> Descargar CSV</a>`
    - Note on Parcelas tab: "Incluye columna `tiene_riego` (1/0)"
    - Note on Riego tab: "No incluye enlace a gasto asociado"

12. Edit `app/templates/base.html` — add nav item after "Importar":
    - Href `/export/`, icon `bi-download`, label `{{ _("Exportar") }}`
    - Active: `{% if '/export' in request.url.path %}active{% endif %}`

---

## Relevant Files
- `app/services/import_service.py` — extend `import_plots_csv()` + add `import_irrigation_csv()`; reference `_load_plots`, `_parse_num`, `_parse_date`
- `app/routers/imports.py` — add `POST /import/irrigation` endpoint
- `app/routers/expenses.py` (lines 219–237) — existing `StreamingResponse` / `BytesIO` download pattern
- `app/templates/imports/index.html` — add 4th Riego tab
- `app/templates/base.html` — nav menu, add item after "Importar"
- `app/main.py` (lines 59–67) — register `exports.router`
- `tests/conftest.py` — `FakeExecuteResult` / `result()` pattern required for all unit tests
- `tests/services/test_irrigation_service.py` — reference for irrigation test patterns (`_make_plot`, `_make_record`)

**New files to create:**
- `app/services/export_service.py`
- `app/routers/exports.py`
- `app/templates/exports/index.html`
- `tests/services/test_export_service.py`

**Existing files to modify:**
- `app/services/import_service.py` — extend plots import + new irrigation import function
- `app/routers/imports.py` — new irrigation import endpoint
- `app/templates/imports/index.html` — add Riego tab
- `app/templates/base.html` — add Exportar nav item

---

## Verification
1. Run `.venv/bin/python -m pytest -q tests/` — all 58+ existing tests must stay green + all new tests pass
2. Manual: import an old-format plots CSV (10 columns, no `tiene_riego`) — must import cleanly with `has_irrigation=False`
3. Manual: import a new-format plots CSV (11 columns) — `has_irrigation` set correctly
4. Manual: export parcelas → re-import via `/import/plots` → same data (round-trip)
5. Manual: export/import gastos and ingresos round-trip without errors
6. Manual: import a riego CSV → records created only for plots with `has_irrigation=True`; rows for missing/non-irrigable plots produce warnings
7. Manual: export riego → re-import → same records (except `expense_id` link which is not exported)
8. Manual: "Exportar" nav link active on `/export/*`; "Importar" nav link active on `/import/*`

---

## Decisions & Scope
- **`has_irrigation` in plots CSV**: column 11, value `1` or `0`; missing = `0` (backward compatible with old 10-column CSVs)
- **Irrigation CSV `expense_id` NOT exported/imported** — it's an internal FK not meaningful across import sessions; can be linked manually via UI
- **Irrigation import validates `has_irrigation=True`** — rows for plots without irrigation enabled are warned and skipped (enforces the business rule from `create_irrigation_record`)
- **No year/campaign filter on export** — exports all user records (filter can be added later)
- **Number precision**: `area_ha` 4 decimals, `agua_m3` 3 decimals, amounts/kg/euros 2 decimals
- **No i18n for new strings** — consistent with existing import template
- `percentage` field NOT exported for plots (auto-calculated on import)
- Receipt data fields on expenses NOT exported (binary/internal)
