# Plan: Gastos prorrateados en varios años (v2)

**TL;DR:** Prorratear un gasto en N años genera N registros `Expense` individuales vinculados por un grupo (`ExpenseProrationGroup`). El borrado siempre advierte. El export/import preserva la relación de grupo mediante una columna opcional en `gastos.csv`.

---

## Decisiones confirmadas

- **Año de inicio configurable**: campo `start_year` en el formulario (default = año de la fecha)
- **Borrado individual con aviso**: si un expense pertenece a un grupo, el modal de borrado **siempre** muestra dos opciones — "eliminar solo este gasto" o "eliminar todo el prorrateo (N entradas)"
- **Export/import**: columna 7 opcional `grupo_prorrateo` en `gastos.csv` (valor `"P-{group_id}"`, vacío para no prorrateados). El import reconstruye el grupo agrupando por ese identificador

---

## Phase 1 — Modelo de datos y migración

1. Crear `app/models/expense_proration_group.py` con tabla `expense_proration_groups`:
   - `id`, `user_id` (FK → users, CASCADE), `description`, `total_amount` (Float), `years` (Integer), `start_year` (Integer)

2. Modificar `app/models/expense.py`: añadir `proration_group_id` (FK nullable → expense_proration_groups, **CASCADE DELETE**) + relationship `proration_group` con `lazy="joined"`

3. Actualizar `app/models/__init__.py` si exporta modelos

4. Crear `alembic/versions/0015_add_expense_proration_groups.py` con `upgrade()` y `downgrade()`

---

## Phase 2 — Capa de servicio *(depende de Phase 1)*

5. `expenses_service.py`: añadir `create_prorated_expense(db, user_id, date, description, person, plot_id, amount, category, years, start_year)`:
   - Crea `ExpenseProrationGroup`
   - Genera N `Expense` con `date = 1 ene de start_year+i`, `amount = round(total/N, 2)`, último absorbe diferencia de redondeo

6. `expenses_service.py`: añadir `get_proration_group(db, group_id, user_id) → Optional[...]` (con filtro `user_id`)

7. `expenses_service.py`: añadir `delete_proration_group(db, group)` — CASCADE borra los N expenses

8. `export_service.py`: modificar `export_expenses_csv()` → añadir columna 7 `grupo_prorrateo` (`"P-{group_id}"` o `""`)

9. `import_service.py`: modificar `import_expenses_csv()` → si columna 7 presente y no vacía, agrupar por ese identificador, crear `ExpenseProrationGroup` (deduplicado), linkear los expenses

---

## Phase 3 — Router *(depende de Phase 2)*

10. `POST /expenses/`: leer `prorate_years: Optional[int]` y `start_year: Optional[int]` del `Form`. Si `prorate_years >= 2`, llamar `create_prorated_expense()`

11. Añadir `POST /expenses/proration-group/{group_id}/delete`: get_proration_group (con user_id), delete_proration_group, redirect con flash

---

## Phase 4 — Templates *(paralela con Phase 3)*

12. `app/templates/gastos/form.html`: sección colapsable **solo en CREATE** — checkbox "Prorratear en varios años" + campo `años` (min 2) + campo `año de inicio` (number, default=año del campo fecha). JS sincroniza el default del año de inicio al cambiar la fecha

13. `app/templates/gastos/list.html`:
    - Badge `Prorrateo` en filas con `expense.proration_group_id`
    - Modal de borrado: si `expense.proration_group_id`, mostrar dos forms → "Solo este gasto" (`/expenses/{id}/delete`) y "Todo el prorrateo — N entradas de X€/año" (`/expenses/proration-group/{group_id}/delete`)

---

## Phase 5 — Tests *(depende de Phases 2 y 3)*

14. `tests/services/test_expenses_incomes_service.py`:
    - `test_create_prorated_expense_creates_group_and_entries` — db.add llamado N+1 veces, fechas y amounts correctos
    - `test_create_prorated_expense_rounding_absorbed_by_last`
    - `test_delete_proration_group_calls_db_delete`

15. Tests export/import (en archivos de test existentes):
    - `test_export_expenses_csv_includes_proration_column` — verifica que columna 7 = `"P-{id}"` para prorrateados
    - `test_import_expenses_csv_reconstructs_proration_group` — verifica que se crea el grupo y los expenses quedan linkeados

---

## Archivos a modificar

| Acción | Archivo |
|--------|---------|
| NEW | `app/models/expense_proration_group.py` |
| NEW | `alembic/versions/0015_add_expense_proration_groups.py` |
| MODIFY | `app/models/expense.py` — FK + relationship |
| MODIFY | `app/models/__init__.py` — exportar nuevo modelo |
| MODIFY | `app/services/expenses_service.py` — 3 funciones nuevas |
| MODIFY | `app/services/export_service.py` — columna 7 en `export_expenses_csv()` |
| MODIFY | `app/services/import_service.py` — reconstrucción de grupos en `import_expenses_csv()` |
| MODIFY | `app/routers/expenses.py` — lógica prorrateo + endpoint delete grupo |
| MODIFY | `app/templates/gastos/form.html` — campos prorrateo |
| MODIFY | `app/templates/gastos/list.html` — badge + modal mejorado |
| MODIFY | `tests/services/test_expenses_incomes_service.py` — tests nuevos |

---

## Verificación

1. `alembic upgrade head` sin errores
2. Crear 1.000€ prorrateado 3 años desde 2024 → 3 registros: 333,33€ + 333,33€ + 333,34€
3. Listado muestra badge en las 3 filas
4. Borrar un registro individual → modal con dos opciones (solo este / todo el grupo)
5. Borrar el grupo → los 3 desaparecen
6. Exportar `gastos.csv` → las 3 filas tienen columna 7 = `"P-42"` (o el id que sea)
7. Importar ese CSV → recrea el grupo y las 3 entradas vinculadas; exportar de nuevo confirma que siguen agrupadas
8. `pytest -q tests/` → todos los tests en verde

---

## Scope excluido

- Edición del grupo (las entradas individuales se editan como expenses normales)
- Importación vía ZIP no requiere cambios adicionales (el ZIP usa el mismo `gastos.csv` actualizado)
- Sin cambios en `charts_service.py` (las entradas proratadas ya son expenses normales)
