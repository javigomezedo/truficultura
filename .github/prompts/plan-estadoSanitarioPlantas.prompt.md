# Plan: Estado sanitario individual por planta

## TL;DR
Añadir `status` (viva/estresada/muerta/reemplazada) y `baja_date` al modelo `Plant`. Mostrar estado visualmente en el mapa (overlay sutil en todos los modos + nuevo modo "Estado") con edición via modal. Solo excluir `muerta` del límite de plantas del plan. Bloquear registro de cosecha SOLO en plantas muertas. Advertir si `num_plants` del plot no coincide con las plantas no-muertas.

---

## Semántica de estados
| Status | Planta real | Producción | Cuenta en límite del plan |
|---|---|---|---|
| viva | Activa | SI | SI |
| estresada | Activa, débil | SI | SI |
| reemplazada | Nueva planta en esa posición | SI | SI |
| muerta | Vacía, hueco virtual | NO (bloqueada) | NO (excluida) |

`reemplazada` = la planta original murió y se plantó una nueva en su lugar. La nueva puede producir eventualmente. NO es un hueco.
`muerta` = sin planta, hueco virtual. Sin producción posible.

---

## Decisiones confirmadas
- Overlay visual en TODOS los modos de vista:
  - `muerta` → celda gris rayada diagonal (hueco virtual)
  - `reemplazada` → planta activa con indicador sutil: borde azul discontinuo o icono pequeño de plántula
  - `estresada` → borde naranja
  - `viva` → sin cambios visuales adicionales
- Nuevo modo "Estado" dedicado con colores por estado + modal de edición
- Edición via modal al hacer click en la celda
- `_get_effective_plant_total` excluirá SOLO `muerta`; el resto cuenta
- **Bloquear cosecha**: endpoint de registro y flujo QR/scan rechazan si `plant.status == 'muerta'`; todos los demás estados permiten cosecha
- Advertencia en el mapa si `num_plants` del plot no coincide con el conteo de plantas no-muertas
- `baja_date` se auto-rellena con la fecha de hoy (editable)
- No se toca `_recalculate_percentages` (usa `plot.num_plants` que es manual)

---

## Fases

### Fase 1: Modelo + Migración
1. `app/models/plant.py`: Añadir `PlantStatus(str, enum.Enum)` con valores `viva/estresada/muerta/reemplazada`. Añadir `status: Mapped[PlantStatus]` (default `viva`, server_default `'viva'`, nullable=False) y `baja_date: Mapped[Optional[datetime.date]]` (nullable=True).
2. `alembic/versions/0030_add_plant_status.py`: CREATE TYPE plant_status_enum, ALTER TABLE ADD COLUMN status (NOT NULL default 'viva') y baja_date (nullable DATE). Con downgrade() inverso.

### Fase 2: Conteo efectivo de plantas
3. `app/services/plots_service.py` → `_get_effective_plant_total`: Añadir `.where(Plant.status != 'muerta')` a la query de Plant. Importar PlantStatus o usar el string literal.

### Fase 3: Servicio de actualización + bloqueo de cosecha
4. `app/services/plants_service.py`: Añadir `update_plant_status(db, plant_id, tenant_id, *, status, baja_date)`. Busca planta, actualiza campos, flush(). Devuelve planta o None.
5. `app/services/plants_service.py` (o router): En el flujo de registro de cosecha, verificar `plant.status == PlantStatus.muerta` y lanzar ValueError con mensaje claro.

### Fase 4: Endpoints de router
6. `app/routers/plants.py` → `POST /plots/{plot_id}/plants/{plant_id}/status`: require_write_access, form fields status + baja_date (opcional). Validar planta existe en plot/tenant. Llamar update_plant_status. Commit + redirect a `?view=estado`.
7. `app/routers/plants.py` → `POST /plots/{plot_id}/plants/{plant_id}/add`: Antes de crear TruffleEvent, verificar `plant.status != 'muerta'`. Si muerta → redirect con mensaje de error.
8. `app/routers/scan.py`: Igual — bloquear creación de TruffleEvent si planta muerta.
9. `map_view` GET: Añadir 'estado' a modos válidos. Calcular `active_plant_count` (status != muerta). Pasar `show_plants_warning` si difiere de `plot.num_plants`. Añadir `status` y `baja_date` a los dicts de `summary_rows`.

### Fase 5: Plantilla mapa.html
10. CSS: Añadir `tf-map-cell-dead` (fondo gris con diagonal), `tf-map-cell-stressed` (borde naranja 2px), `tf-map-cell-replaced` (borde azul discontinuo).
11. Overlay universal: En `{% if cell.plant %}`, añadir clases extra según `cell.plant.status.value` en todos los modos de vista.
12. Modo "Estado": Botón toggle + celdas coloreadas (verde=viva, naranja=estresada, rojo=muerta, azul=reemplazada). Click abre modal con data-status-mode="true".
13. Modal de estado: Select de status + input date baja (show/hide con JS cuando status es muerta/reemplazada). Acción POST al endpoint de status.
14. Columna Estado en tabla resumen: Badge coloreado + baja_date si aplica.
15. Advertencia num_plants: Alert si `show_plants_warning`.
16. Leyenda de estados: Bloque estático bajo el mapa de celdas, visible en todos los modos de vista. Muestra los 4 estados con su muestra de color/icono y descripción breve: Viva (verde), Estresada (naranja), Reemplazada (azul), Muerta (gris). Implementado como HTML puro en la plantilla, sin lógica de servidor.

### Fase 6: Tests
17. `tests/services/test_plants_service.py`: Tests de `update_plant_status` (encontrada/no encontrada). Test que cosecha con planta muerta lanza error.
18. `tests/test_plants_router.py`: Test POST status (303). Test POST add con planta muerta → redirect con error.
19. `tests/test_scan_router.py`: Test scan con planta muerta → error apropiado.

### Fase 7: Instrucciones del asistente
20. Actualizar `.github/instructions/assistant.instructions.md`.

---

## Archivos afectados
- `app/models/plant.py`
- `alembic/versions/0030_add_plant_status.py` (crear)
- `app/services/plots_service.py` — _get_effective_plant_total
- `app/services/plants_service.py` — update_plant_status + bloqueo cosecha
- `app/routers/plants.py` — endpoint status, bloqueo add, modo estado, advertencia
- `app/routers/scan.py` — bloqueo en flujo QR
- `app/templates/parcelas/mapa.html` — CSS, overlay, modo estado, modal, columna, advertencia, leyenda
- `tests/services/test_plants_service.py`
- `tests/test_plants_router.py`
- `tests/test_scan_router.py` (si aplica)

## Verificación
1. `uv run pytest tests/ -x` — todos los tests verdes
2. `alembic upgrade head` — sin errores
3. Verificar: planta muerta → cosecha bloqueada (web y QR)
4. Verificar: planta reemplazada → cosecha permitida, cuenta en límite del plan
5. Verificar overlay visible en los 4 modos de vista con estilos diferenciados
6. Verificar leyenda visible en todos los modos de vista
7. Verificar advertencia si num_plants != plantas no-muertas
