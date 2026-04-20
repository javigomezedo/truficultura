## Plan: Gastos Recurrentes

Añadir una entidad `RecurringExpense` para configurar gastos automáticos mensuales, con un **APScheduler AsyncIOScheduler** integrado en FastAPI que corre cada día a las 07:00 y genera registros reales en la tabla `expenses`.

---

**Fases**

### Fase 1 — Capa de datos
1. Crear `app/models/recurring_expense.py` — campos: `id`, `user_id` (FK→users CASCADE), `description`, `amount`, `category`, `plot_id` (FK→plots SET NULL, opcional), `person` (opcional), `day_of_month` (Integer 1–28), `is_active` (Boolean, default True), `last_run_date` (Date, nullable para prevenir duplicados)
2. Actualizar `app/models/__init__.py` — importar el nuevo modelo
3. Crear `alembic/versions/0009_add_recurring_expenses.py` — `create_table` + `downgrade` con `drop_table`

### Fase 2 — Capa de servicio
4. Crear `app/services/recurring_expenses_service.py` con:
   - CRUD: `list_recurring_expenses`, `get_recurring_expense`, `create_recurring_expense`, `update_recurring_expense`, `delete_recurring_expense`
   - **`process_recurring_expenses(db)`** — lógica del cron: carga todos los `RecurringExpense` activos; para cada uno calcula `target_date = (hoy.year, hoy.month, min(day_of_month, días_del_mes))`; si `hoy >= target_date` y `last_run_date` no es de este mes → crea un `Expense`, actualiza `last_run_date = hoy`

### Fase 3 — Router + Templates *(paralelo con Fase 2)*
5. Crear `app/routers/recurring_expenses.py` — prefix `/recurring-expenses`, endpoints: GET/POST `/`, GET/POST `/{id}/edit`, POST `/{id}/delete`, POST `/{id}/toggle`
6. Crear `app/templates/gastos/recurrentes/list.html` — tabla con descripción, importe, categoría, parcela, persona, día, estado; botones editar/eliminar/toggle
7. Crear `app/templates/gastos/recurrentes/form.html` — campos del formulario con select de categorías y parcelas

### Fase 4 — Scheduler + Integración *(depende de Fase 2)*
8. Añadir `apscheduler>=3.10` a `pyproject.toml`
9. Actualizar `app/main.py`:
   - Importar `AsyncIOScheduler`, `CronTrigger`, `process_recurring_expenses`, `AsyncSessionLocal`
   - En el lifespan: `scheduler.add_job(...)` con `CronTrigger(hour=7, minute=0)`, `scheduler.start()` → yield → `scheduler.shutdown()`
   - Registrar el nuevo router y compartir templates

### Fase 5 — Navegación *(paralela)*
10. Actualizar `app/templates/base.html` — añadir "Gastos Recurrentes" (`bi bi-arrow-repeat`) en el dropdown "Finanzas"; ampliar condición `active` del dropdown

### Fase 6 — Tests *(depende de Fases 2 y 3)*
11. Crear `tests/services/test_recurring_expenses_service.py` — tests del servicio incluyendo los 5 escenarios de `process_recurring_expenses` (sin activos, día alcanzado por primera vez, ya ejecutado este mes, día no alcanzado aún, retroactividad)
12. Crear `tests/test_recurring_expenses_router.py` — todos los endpoints con patrón `monkeypatch` + `dependency_overrides`

---

**Archivos relevantes**
- `app/models/expense.py` — patrón a replicar para el nuevo modelo
- `app/services/expenses_service.py` — patrón de funciones CRUD y `create_expense` a reusar
- `app/routers/expenses.py` — patrón de router a replicar
- `app/database.py` — `AsyncSessionLocal` para el scheduler, `Base` para el modelo
- `app/main.py` — lifespan a ampliar, routers a registrar
- `app/templates/base.html` — dropdown "Finanzas" (línea 118)

---

**Verificación**
1. `uv add apscheduler` — sin conflictos de dependencias
2. `alembic upgrade head` — migración 0009 aplicada correctamente
3. `uv run pytest tests/services/test_recurring_expenses_service.py -v`
4. `uv run pytest tests/test_recurring_expenses_router.py -v`
5. Suite completa verde: `uv run pytest -q tests/`
6. Manual: crear un gasto recurrente con día = hoy → aparece en `/expenses/` tras la ejecución del job
7. Manual: ejecutar el job dos veces → no se duplica (protegido por `last_run_date`)

---

**Decisiones**
- `day_of_month` limitado a 1–28 para evitar conflictos con febrero
- Fecha del gasto creado: `(hoy.year, hoy.month, day_of_month)`, no la fecha real de ejecución (así aparece como el día 1 si está configurado así)
- El servicio `process_recurring_expenses` no gestiona sesión: el scheduler wrapper crea/commitea/cierra su propia sesión con `AsyncSessionLocal`
