# Plan: Funcionalidad de Riego (Irrigation)

## TL;DR
Añadir gestión de riego al sistema de trufiq. Implica: (1) flag `has_irrigation` en parcelas, (2) nuevo modelo `IrrigationRecord`, (3) servicio + router + templates CRUD completos, (4) migración Alembic. Agua en m³ (se mostrará también en litros), solo parcelas con riego activado, gastos vinculados solo de categoría "Riego", campo de notas opcional.

---

## Fase 1 — Modelos y Migración

### Step 1 — Añadir `has_irrigation` a Plot
- Fichero: `app/models/plot.py`
- Añadir campo: `has_irrigation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)`
- Importar `Boolean` de `sqlalchemy`

### Step 2 — Nuevo modelo `IrrigationRecord`
- Fichero nuevo: `app/models/irrigation.py`
- Campos:
  - `id: Mapped[int]` — PK
  - `user_id: Mapped[Optional[int]]` — FK(users.id, CASCADE), nullable, index
  - `plot_id: Mapped[int]` — FK(plots.id, CASCADE), NOT NULL, index
  - `date: Mapped[datetime.date]` — Date, index
  - `water_m3: Mapped[float]` — Float, NOT NULL (metros cúbicos)
  - `expense_id: Mapped[Optional[int]]` — FK(expenses.id, SET NULL), nullable, index
  - `notes: Mapped[Optional[str]]` — String(500), nullable
- Relaciones: `user`, `plot` (lazy="joined"), `expense` (lazy="joined")
- Añadir `irrigation_records: Mapped[List["IrrigationRecord"]]` en Plot model
- Añadir `irrigation_records: Mapped[List["IrrigationRecord"]]` en User model (o al menos el back_populates)

### Step 3 — Actualizar `app/models/__init__.py`
- Importar el nuevo modelo `IrrigationRecord`

### Step 4 — Migración Alembic `0008_add_irrigation.py`
- `upgrade()`:
  - `op.add_column("plots", sa.Column("has_irrigation", sa.Boolean(), nullable=False, server_default="false"))`
  - `op.create_table("irrigation_records", ...)` con todos los campos y FKs
- `downgrade()`:
  - `op.drop_table("irrigation_records")`
  - `op.drop_column("plots", "has_irrigation")`

---

## Fase 2 — Schemas

### Step 5 — Actualizar `app/schemas/plot.py`
- Añadir `has_irrigation: bool = False` a `PlotBase`

### Step 6 — Nuevo `app/schemas/irrigation.py`
- `IrrigationBase`: `plot_id`, `date`, `water_m3`, `expense_id` (Optional), `notes` (Optional[str])
- `IrrigationCreate(IrrigationBase)`: sin cambios
- `IrrigationUpdate(IrrigationBase)`: todos Optional
- `IrrigationResponse(IrrigationBase)`: añade `id`, `user_id`, `water_liters` (computed: water_m3 * 1000), `plot_name` (str), `expense_description` (Optional[str]), `expense_amount` (Optional[float]); con `model_config = ConfigDict(from_attributes=True)`

---

## Fase 3 — Servicio

### Step 7 — Nuevo `app/services/irrigation_service.py`
Funciones (todas async, todas filtran por `user_id`):
- `get_irrigation_record(db, record_id, user_id) → IrrigationRecord | None`
- `list_irrigation_records(db, user_id, plot_id=None, year=None) → list[IrrigationRecord]`
  - join con Plot para verificar `user_id`; filtra por `campaign_year()` si `year` proporcionado
- `get_irrigation_list_context(db, user_id, year=None, plot_id=None) → dict`
  - Devuelve: `records`, `plots` (solo con `has_irrigation=True`), `years`, `selected_year`, `selected_plot`, `total_water_m3`, `total_water_liters`, `count`
- `create_irrigation_record(db, user_id, data: IrrigationCreate) → IrrigationRecord`
  - Valida que el plot pertenezca al user y tenga `has_irrigation=True`
  - Si `expense_id` proporcionado, valida que el gasto sea del user, del plot y tenga `category="Riego"`
- `update_irrigation_record(db, record, data: IrrigationUpdate) → IrrigationRecord`
- `delete_irrigation_record(db, record_id, user_id) → None`
- `get_riego_expenses_for_plot(db, user_id, plot_id) → list[Expense]`
  - Filtra expenses donde `user_id`, `plot_id`, y `category="Riego"`

---

## Fase 4 — Router

### Step 8 — Nuevo `app/routers/irrigation.py`
URLs bajo `/irrigation/`:
- `GET /irrigation/` → `list_view` → renderiza `riego/list.html`
- `GET /irrigation/new` → `new_form` → renderiza `riego/form.html`
- `POST /irrigation/` → `create_view` → redirect a `/irrigation/`
- `GET /irrigation/{id}/edit` → `edit_form` → renderiza `riego/form.html`
- `POST /irrigation/{id}/edit` → `update_view` → redirect a `/irrigation/`
- `POST /irrigation/{id}/delete` → `delete_view` → redirect a `/irrigation/`

Dependencias: `get_current_user` de `app/auth.py`, `get_db` de `app/database.py`

### Step 9 — Registrar router en `app/main.py`
- `app.include_router(irrigation.router)`

---

## Fase 5 — Templates

### Step 10 — `app/templates/riego/list.html`
- Extiende `base.html`
- Filtros: año de campaña, parcela (solo con riego)
- Tabla: fecha, parcela, m³, litros, gasto asociado (descripción + importe), notas, acciones (editar/borrar)
- Totales: total m³, total litros, número de riegos
- Botón "Nuevo registro de riego"
- Bootstrap 5 + Bootstrap Icons (`bi-droplet-fill` para icono de riego)

### Step 11 — `app/templates/riego/form.html`
- Extiende `base.html`
- Campos: parcela (select, solo `has_irrigation=True`), fecha (date picker), m³ de agua (number input con step=0.001), gasto asociado (select dinámico filtrado por parcela — categoría "Riego"), notas (textarea)
- JS: al cambiar la parcela, hacer fetch `/irrigation/expenses-for-plot/{plot_id}` para cargar el select de gastos dinámicamente
- Mostrar litros calculados en tiempo real (m³ × 1000)

### Step 12 — Endpoint API para dropdown dinámico
- `GET /irrigation/expenses-for-plot/{plot_id}` → devuelve JSON con lista de gastos (para el JS del formulario)
- Añadir al router de irrigation

### Step 13 — Actualizar `app/templates/parcelas/form.html`
- Añadir checkbox "Tiene sistema de riego" para el campo `has_irrigation`

### Step 14 — Actualizar `app/templates/base.html`
- Añadir enlace "Riego" en la navbar entre "Gastos" e "Ingresos" (o al final de la sección principal)
- Icono: `bi-droplet-fill`

---

## Fase 6 — Tests

### Step 15 — Nuevo `tests/services/test_irrigation_service.py`
Tests usando patrón `FakeExecuteResult` de `tests/conftest.py` (NO AsyncMock para sesión):
- `test_list_irrigation_records_filters_by_user_id`
- `test_create_validates_plot_has_irrigation`
- `test_create_validates_expense_category_riego`
- `test_delete_enforces_user_id`
- `test_get_riego_expenses_filters_by_category`

### Step 16 — Actualizar tests de Plot
- `tests/services/test_plots_service.py`: añadir `has_irrigation=False` a los Plot fixtures

---

## Ficheros relevantes

- `app/models/plot.py` — añadir `has_irrigation`, relación `irrigation_records`
- `app/models/irrigation.py` — crear modelo `IrrigationRecord`
- `app/models/__init__.py` — importar nuevo modelo
- `app/schemas/plot.py` — añadir campo `has_irrigation`
- `app/schemas/irrigation.py` — crear schemas (crear fichero)
- `app/services/irrigation_service.py` — crear servicio (crear fichero)
- `app/routers/irrigation.py` — crear router (crear fichero)
- `app/main.py` — registrar router
- `app/templates/riego/list.html` — crear template lista
- `app/templates/riego/form.html` — crear template formulario
- `app/templates/parcelas/form.html` — añadir checkbox has_irrigation
- `app/templates/base.html` — añadir enlace navbar
- `alembic/versions/0008_add_irrigation.py` — crear migración
- `tests/services/test_irrigation_service.py` — crear tests unitarios

---

## Verificación

1. Ejecutar `pytest` — todos los tests deben pasar (incluyendo los 58+ existentes)
2. Ejecutar `alembic upgrade head` en entorno de dev
3. Crear una parcela y activar el flag "tiene riego"
4. Crear un gasto con categoría "Riego" para esa parcela
5. Crear un registro de riego vinculando la parcela y el gasto → verificar que aparece en la lista con m³ y litros
6. Filtrar por campaña y por parcela en la lista
7. Editar y borrar un registro
8. Verificar que un registro de riego NO puede crearse para una parcela sin `has_irrigation=True`
9. Verificar que solo el usuario propietario ve sus registros

---

## Decisiones

- Agua: input en m³, se muestra también en litros (× 1000) — calculado en template/schema, no almacenado
- Solo parcelas con `has_irrigation=True` pueden tener registros de riego
- Gastos vinculables: solo categoría "Riego"
- `expense_id` es opcional (puede no haber gasto asociado a un riego)
- `plot_id` NOT NULL en irrigation_records (riego siempre asociado a parcela concreta)
- Informes cruzados con otras tablas: FUERA DEL ALCANCE (se diseña el modelo para soportarlos en el futuro)
- URL inglesa `/irrigation/` pero templates/carpeta en español `riego/` (consistente con el resto del proyecto)
