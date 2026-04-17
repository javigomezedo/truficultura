# Plan: Timeline de eventos por parcela – Eventos recurrentes, únicos e integración automática

## Visión General
Crear un sistema unificado de **historial de eventos por parcela** que:
- Registre eventos recurrentes (labrado, picado, poda) + únicos (vallado, instalación riego)
- Integre automáticamente riego y pozos sin duplicación de datos
- Ofrezca dos vistas: **calendario** (visual) + **listado** (tabular)
- Siga el patrón de 3 capas (routers → services → models)

---

## Phase 1: Modelo de Datos & Migraciones

### 1.1 Crear modelo `PlotEvent`
Archivo: `app/models/plot_event.py`

**Campos**:
- `id`: Integer (PK)
- `user_id`: Integer (FK → users, CASCADE) — multi-tenancy
- `plot_id`: Integer (FK → plots, CASCADE) — qué parcela
- `event_type`: String/Enum (`LABRADO`, `PICADO`, `PODA`, `VALLADO`, `INSTALLED_DRIP`, `RIEGO`, `POZO`)
- `date`: Date — cuándo sucedió
- `notes`: String(500) — anotaciones opcionales
- `is_recurring`: Boolean — diferencia entre recurrentes (labrado, poda) y únicos (vallado)
- `related_irrigation_id`: Integer (FK → irrigation_records, SET NULL) — si es auto-linked
- `related_well_id`: Integer (FK → wells, SET NULL) — si es auto-linked
- `created_at`: DateTime (auto timestamp)
- `updated_at`: DateTime (auto timestamp)

**Índices**:
- `(user_id, plot_id, date)` — queries frecuentes por usuario + parcela + rango de fechas
- `(user_id, plot_id, event_type)` — filtrado por tipo de evento

**Relaciones**:
- `plot`: Many-to-one con Plot
- `related_irrigation`: One-to-one optional con IrrigationRecord
- `related_well`: One-to-one optional con Well

### 1.2 Modificar modelo `Plot`
Archivo: `app/models/plot.py`

Añadir relación:
```python
plot_events = relationship("PlotEvent", back_populates="plot", cascade="all, delete-orphan", lazy="select")
```

### 1.3 Migración Alembic
Archivo: `alembic/versions/0007_add_plot_events_table.py`

```
CREATE TABLE plot_events (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  plot_id INTEGER NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  date DATE NOT NULL,
  notes VARCHAR(500),
  is_recurring BOOLEAN NOT NULL DEFAULT false,
  related_irrigation_id INTEGER,
  related_well_id INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (plot_id) REFERENCES plots(id) ON DELETE CASCADE,
  FOREIGN KEY (related_irrigation_id) REFERENCES irrigation_records(id) ON DELETE SET NULL,
  FOREIGN KEY (related_well_id) REFERENCES wells(id) ON DELETE SET NULL,
  CONSTRAINT unique_one_time_event UNIQUE (plot_id, event_type) WHERE is_recurring = false
)
```

---

## Phase 2: Schemas & Services

### 2.1 Crear Schema `PlotEventSchema`
Archivo: `app/schemas/plot_event.py`

**Enums**:
```python
class EventType(str, Enum):
    LABRADO = "labrado"
    PICADO = "picado"
    PODA = "poda"
    VALLADO = "vallado"
    INSTALLED_DRIP = "installed_drip"
    RIEGO = "riego"
    POZO = "pozo"
```

**Schemas**:
- `PlotEventCreate`: plot_id, event_type, date, notes (opcional), is_recurring (opcional)
- `PlotEventUpdate`: event_type (opcional), date (opcional), notes (opcional)
- `PlotEventResponse`: id, plot_id, event_type, date, notes, is_recurring, related_irrigation_id, related_well_id, created_at, updated_at
- `PlotEventListResponse`: extender Response con info de parcela (plot_name, plot_sector)

### 2.2 Crear Service `PlotEventsService`
Archivo: `app/services/plot_events_service.py`

**Métodos principales**:

#### CRUD Base
- `async create_plot_event()`: crear evento, validar unique constraint para one-time, retornar PlotEvent
- `async get_plot_event(event_id, user_id)`: leer evento (filtrado por user_id)
- `async update_plot_event(event_id, user_id, data)`: actualizar campos
- `async delete_plot_event(event_id, user_id)`: borrar evento
- `async get_plot_events(user_id, plot_id=None, start_date=None, end_date=None, event_types=None)`: listar con filtros

#### Lógica de agrupación
- `async get_events_by_month(user_id, plot_id, year, month)`: retornar events agrupados por mes para calendario
- `async get_events_grouped(user_id, plot_id, year=None)`: retornar (month, [events]) para vista de calendario anual

#### Auto-linking (hooks)
- `async create_plot_event_for_irrigation(irrigation_record)`: crear PlotEvent con `event_type="riego"` + FK, check si ya exists
- `async create_plot_event_for_well(well_record)`: crear PlotEvent con `event_type="pozo"` + FK, check si ya exists
- `async update_plot_event_from_irrigation(irrigation_record)`: actualizar fecha/notas del PlotEvent linkedado
- `async delete_plot_event_for_irrigation(irrigation_id, user_id)`: borrar PlotEvent linkedado
- `async delete_plot_event_for_well(well_id, user_id)`: borrar PlotEvent linkedado

#### Validaciones
- `validate_one_time_event(plot_id, event_type, user_id)`: retornar error si ya existe evento único para esa parcela/tipo
- `validate_plot_ownership(plot_id, user_id)`: asegurar que el usuario es propietario de la parcela

### 2.3 Modificar Service de Riego
Archivo: `app/services/irrigation_service.py`

En `create_irrigation_record()`:
```python
# Crear IrrigationRecord
irrigation = await session.execute(...)
await session.flush()  # necesario para tener ID

# Auto-crear PlotEvent linkedado
await plot_events_service.create_plot_event_for_irrigation(irrigation)
```

En `update_irrigation_record()`:
```python
# Actualizar IrrigationRecord
await session.execute(...)
# Mirror cambios a PlotEvent linkedado
await plot_events_service.update_plot_event_from_irrigation(irrigation)
```

En `delete_irrigation_record()`:
```python
# Borrar PlotEvent linkedado
await plot_events_service.delete_plot_event_for_irrigation(irrigation_id, user_id)
# Borrar IrrigationRecord
await session.execute(...)
```

### 2.4 Modificar Service de Pozos
Archivo: `app/services/wells_service.py`

Mismo patrón que irrigation_service:
- `create_well_record()` → `create_plot_event_for_well()`
- `update_well_record()` → `update_plot_event_from_well()`
- `delete_well_record()` → `delete_plot_event_for_well()`

---

## Phase 3: Routers & Endpoints

### 3.1 Crear Router
Archivo: `app/routers/plot_events.py`

**Endpoints**:

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/plot-events/` | Listar eventos con filtros (plot_id, date_from, date_to, event_type) — render HTML o JSON |
| GET | `/plot-events/json/` | JSON puro para AJAX (para vistas duales) |
| GET | `/plot-events/calendar/` | Datos agrupados por mes para calendario (JSON) |
| GET | `/plot-events/new` | Formulario crear evento |
| POST | `/plot-events/` | Guardar evento nuevo |
| GET | `/plot-events/{id}/edit` | Formulario editar evento |
| POST | `/plot-events/{id}/update` | Guardar actualización |
| POST | `/plot-events/{id}/delete` | Borrar evento |

**Validaciones en router**:
- Asegurar que current_user existe (con auth)
- Validar que plot_id pertenece a current_user
- Validar event_type es válido (Enum)
- Para one-time events, rechazar si ya existe otra entrada

### 3.2 Registrar en main.py
```python
from app.routers import plot_events
app.include_router(plot_events.router, prefix="/plot-events", tags=["plot_events"])
```

---

## Phase 4: Frontend – Templates & Views

### 4.1 Estructura de carpeta
```
app/templates/
└── eventos_parcela/
    ├── list.html        # Vista listado
    ├── calendar.html    # Vista calendario
    ├── form.html        # Formulario crear/editar
    └── components/
        ├── event_row.html      # Fila de tabla reutilizable
        └── calendar_grid.html  # Grid mensual reutilizable
```

### 4.2 Vista Listado (list.html)

**Características**:
- Extiende `base.html`
- **Filtros**: 
  - Dropdown parcela (populate vía JS o pre-render)
  - Checkboxes event_type (LABRADO, PICADO, PODA, etc.) — seleccionar múltiples
  - Date range picker (date_from, date_to)
  - Botón "Aplicar filtros"
- **Tabla**:
  - Columnas: Fecha | Tipo evento | Notas | Acciones
  - Filas: cada evento, color-coded por tipo
  - Filas linkedadas (riego/pozo): fondo gris, icono "enlazado", sin botón editar directo (read-only)
  - Acciones: Editar (solo for manual), Borrar (solo if manual o no linkedado), Ver detalles
- **Botón crear evento nuevo**: link to `/plot-events/new`
- **Toggle button**: "📊 Ver Calendario" → redirige a `/plot-events/calendar/` con mismos filtros

### 4.3 Vista Calendario (calendar.html)

**Características**:
- Extiende `base.html`
- **Selector**: Mes/Año dropdowns or left/right navigation arrows
- **Grid mensual**: 7 columnas (L-D), días en celdas
  - Cada día muestra eventos stacleados verticalmente
  - Color-code: labrado=naranja, picado=marrón, poda=verde, riego=azul, etc.
  - Evento clickable → abre modal con detalles + acciones
- **Legend**: simbología (color = tipo evento)
- **Toggle button**: "📋 Ver Listado" → redirige a `/plot-events/` con mismos filtros
- **Modal (on click event)**:
  - Mostrar: Fecha | Tipo | Notas | linked_irrigation/well (si aplica, link a esa vista)
  - Botones: Editar, Borrar, Cerrar
  - Si linkedado: mostrar "Este evento fue importado automáticamente desde [Riego/Pozo]" + link read-only

### 4.4 Formulario (form.html)

**Para crear/editar evento manual**:
- Extiende `base.html`
- **Campos**:
  - Parcela (dropdown, required, pre-filled si from=/plot-events/new?plot_id=X)
  - Tipo evento (select Enum, required)
  - Fecha (date input, required)
  - Notas (textarea, optional)
  - `is_recurring` (checkbox, default=false) — visible pero deshabilitada para one-time types
- **Validación frontend**: 
  - One-time event → JS check: si event_type ∈ {VALLADO, INSTALLED_DRIP}, mostrar warning "só se puede registrar 1 vez" + deshabilitar submit si ya existe
- **Botones**: Guardar, Cancelar (vuelve a listado/calendario)
- **Error messages**: mostrar si validación backend falla

---

## Phase 5: Testing & Validación

### 5.1 Unit Tests
Archivo: `tests/services/test_plot_events_service.py`

**Test cases**:
- `test_create_plot_event` — crear evento manual, verificar campos
- `test_create_plot_event_one_time_duplicate` — crear 2 eventos VALLADO en misma parcela → error
- `test_create_plot_event_for_irrigation` — crear riego → auto-crear PlotEvent linkedado
- `test_create_plot_event_for_irrigation_no_duplicate` — crear 2 veces riego mismo día → no duplicar PlotEvent
- `test_update_plot_event_from_irrigation` — cambiar fecha de riego → fecha de PlotEvent se actualiza
- `test_delete_plot_event_for_irrigation` — borrar riego → borrar PlotEvent linkedado
- `test_get_events_by_month` — agrupar eventos por mes
- `test_get_plot_events_with_filters` — listar con date_from, date_to, event_type filters
- `test_validate_one_time_event` — validación de eventos únicos
- `test_user_isolation` — usuario A no ve eventos de usuario B

### 5.2 Integration Tests
Archivo: `tests/integration/test_plot_events_integration.py`

**Test cases**:
- `test_create_irrigation_creates_plot_event_automatically` — flujo completo: crear riego → verificar PlotEvent en DB
- `test_edit_irrigation_updates_linked_plot_event` — editar riego → PlotEvent actualizado
- `test_delete_irrigation_deletes_linked_plot_event` — borrar riego → PlotEvent borrado
- `test_create_well_creates_plot_event_automatically` — crear pozo → auto-crear PlotEvent
- `test_router_get_plot_events_returns_json` — endpoint GET retorna JSON valid
- `test_router_create_plot_event_manual` — POST crear evento manual, validar respuesta
- `test_router_one_time_event_constraint` — POST 2 veces VALLADO → 2nd falla

### 5.3 Validación Manual

**Smoke tests**:
1. Crear parcela, crear evento manual (labrado) → aparece en lista y calendario ✓
2. Crear riego de parcela → aparece en lista de eventos como "riego" (linkedado) ✓
3. Editar fecha de riego → fecha de evento actualizada ✓
4. Borrar riego → evento desaparece de lista ✓
5. Intentar crear 2 eventos VALLADO en misma parcela → error ✓
6. Toggle lista ↔ calendario sin pérdida de datos ✓
7. Filtrar por event_type (solo PODA) → solo podas visibles ✓
8. Filtrar por rango de fechas → eventos fuera de rango ocultados ✓

### 5.4 Regresión
- Ejecutar full test suite: `pytest tests/` → todos 58+ tests deben pasar
- Verificar que endpoints de riego/pozos siguen funcionando igual
- Validar que migración se ejecuta sin errores: `alembic upgrade head`

---

## Phase 6: Analítica histórica e impacto en producción

### 6.1 Objetivo de negocio
Además de registrar eventos, usar el histórico acumulado (muchos años y muchos bancales) para responder:
- Si un bancal necesita más o menos riego para subir o bajar producción.
- Si poda, picado o labrado impactan en producción y rendimiento.
- Si existe un umbral de riego anual (m3/litros) a partir del cual ya no mejora la productividad.

### 6.2 Dataset analítico por campaña
Crear una capa de agregación por:
- `user_id`
- `plot_id`
- `campaign_year`

Métricas mínimas:
- Producción:
  - `total_production_kg`
  - `production_kg_per_plant`
- Riego:
  - `total_water_m3`
  - `total_water_liters`
  - `irrigation_events_count`
  - `water_m3_per_plant`
- Manejo:
  - `pruning_events_count`
  - `tilling_events_count` (labrado)
  - `digging_events_count` (picado)
  - `days_since_last_pruning`
  - `days_since_last_tilling`
  - `days_since_last_digging`
- Contexto:
  - `num_plants`
  - `has_irrigation`
  - `well_events_count`
  - `wells_per_plant_total`

Reglas clave:
- Reutilizar siempre `campaign_year()` y `campaign_label()`.
- Mantener aislamiento estricto por `user_id` en todas las consultas.

### 6.3 Servicios de análisis
Crear `app/services/plot_analytics_service.py` con funciones tipo:
- `get_campaign_dataset(...)`
- `get_irrigation_vs_production_analysis(...)`
- `get_pruning_vs_production_analysis(...)`
- `get_tilling_digging_vs_production_analysis(...)`
- `detect_irrigation_thresholds(...)`

Métodos analíticos iniciales (explicables):
- Correlación (Pearson/Spearman).
- Comparación por tramos de riego (bajo/medio/alto).
- Retorno marginal del riego.
- Detección de meseta (punto donde más riego no mejora de forma significativa).

### 6.4 Recomendaciones explicables
Generar insights con lenguaje de negocio, por ejemplo:
- "En este bancal, aumentar de X a Y m3/campaña se asocia con +N% de producción media."
- "Por encima de Z m3/campaña no se observa mejora significativa."
- "Las campañas con poda en ventana objetivo muestran +N% kg/planta frente a campañas sin poda."

### 6.5 UI de analítica
Añadir sección "Análisis de rendimiento":
- Vista por bancal:
  - Serie temporal producción vs riego por campaña.
  - Marcadores de poda/picado/labrado.
- Vista comparativa:
  - Scatter plot agua/campaña vs producción/campaña.
  - Ranking de eficiencia hídrica (`kg/m3`).
- Panel de insights:
  - Hallazgo.
  - Tamaño de muestra.
  - Campañas usadas.
  - Nivel de confianza.

### 6.6 Calidad de datos y gobernanza
- No mostrar conclusiones si hay muestra insuficiente (ej. `< 3` campañas por bancal).
- Mostrar trazabilidad de cada insight (qué campañas y cuántos registros lo sostienen).
- Permitir excluir outliers opcionalmente en análisis exploratorio.

### 6.7 Tests de analítica
Crear tests:
- `tests/services/test_plot_analytics_service.py`
- `tests/integration/test_plot_analytics_integration.py`

Cobertura mínima:
- Agregados por campaña correctos.
- Correlaciones reproducibles con datasets sintéticos.
- Detección de umbral de riego en casos controlados.
- Bloqueo de insights cuando no hay muestra suficiente.
- Aislamiento por `user_id`.

---

## Phase 7: IA/ML para patrones, umbrales y recomendaciones

### 7.1 Objetivo
Evolucionar desde analítica descriptiva a recomendaciones predictivas, manteniendo trazabilidad y explicabilidad.

### 7.2 Estrategia por etapas

#### Etapa A: ML interpretable (primera iteración)
- Objetivo: predecir `total_production_kg` y `production_kg_per_plant` por campaña.
- Modelos candidatos:
  - Gradient Boosting Regressor
  - Random Forest Regressor
- Explicabilidad:
  - Feature importance global
  - Importancia local por predicción (opcional: SHAP)

#### Etapa B: Detección robusta de umbrales
- Identificar puntos de saturación de riego (meseta) con:
  - Piecewise regression
  - Binning adaptativo por cuantiles
- Resultado esperado:
  - Rango de riego recomendado por bancal o segmento de bancales

#### Etapa C: Recomendador operativo
- Recomendaciones accionables del tipo:
  - “Para objetivo de producción X, rango sugerido de riego Y-Z m3/campaña”.
  - “Con histórico actual, aumentar por encima de Z no mejora significativamente”.
- Guardrails:
  - No emitir recomendaciones si la confianza es baja o la muestra insuficiente.

### 7.3 Pipeline de datos ML
1. Construcción de features por `user_id`, `plot_id`, `campaign_year`.
2. Split temporal (train con campañas antiguas, test con campañas más recientes).
3. Entrenamiento offline (no en request web).
4. Registro de métricas y versión de modelo.
5. Publicación de resultados al panel analítico.

Features mínimas recomendadas:
- Riego total por campaña, frecuencia de riego, m3/planta
- Conteo de labores (poda, picado, labrado)
- Tiempo desde última labor
- Señales de contexto disponibles en el sistema (plantas, has_irrigation, pozos)

### 7.4 Métricas de calidad del modelo
- Regresión:
  - MAE
  - RMSE
  - R2
- Negocio:
  - Estabilidad del umbral detectado entre campañas
  - Porcentaje de recomendaciones con confianza suficiente

### 7.5 Criterios de activación de ML
- Mínimo recomendado para activar modelos por usuario:
  - >= 3-5 campañas con datos consistentes por un conjunto relevante de bancales.
- Si no se cumple:
  - Mantener modo “analítica estadística” sin predicción ML.

### 7.6 UX de resultados IA/ML
- En cada insight mostrar:
  - Nivel de confianza
  - Tamaño de muestra
  - Modelo/versión usado
  - Variables que más influyen
- Etiquetas de estado:
  - “Estimación robusta”
  - “Estimación exploratoria”
  - “Datos insuficientes”

### 7.7 Testing y validación ML
Crear tests:
- `tests/services/test_plot_ml_service.py`
- `tests/integration/test_plot_ml_integration.py`

Cobertura mínima:
- Pipeline de features reproducible
- Split temporal correcto (sin leakage)
- Entrenamiento con métricas calculadas
- Reglas de guardrail activas con baja muestra/confianza

---

## Relevant Files To Create/Modify

### Create
- `app/models/plot_event.py`
- `app/schemas/plot_event.py`
- `app/services/plot_events_service.py`
- `app/routers/plot_events.py`
- `app/templates/eventos_parcela/list.html`
- `app/templates/eventos_parcela/calendar.html`
- `app/templates/eventos_parcela/form.html`
- `app/templates/eventos_parcela/components/event_row.html`
- `app/templates/eventos_parcela/components/calendar_grid.html`
- `alembic/versions/0007_add_plot_events_table.py`
- `tests/services/test_plot_events_service.py`
- `tests/integration/test_plot_events_integration.py`
- `app/services/plot_analytics_service.py`
- `app/routers/plot_analytics.py`
- `app/templates/analitica_parcelas/overview.html`
- `app/templates/analitica_parcelas/plot_detail.html`
- `tests/services/test_plot_analytics_service.py`
- `tests/integration/test_plot_analytics_integration.py`
- `app/services/plot_ml_service.py`
- `app/services/ml_training_service.py`
- `app/routers/plot_ml.py`
- `app/templates/analitica_parcelas/ml_insights.html`
- `tests/services/test_plot_ml_service.py`
- `tests/integration/test_plot_ml_integration.py`

### Modify
- `app/models/plot.py` — añadir relación plot_events
- `app/services/irrigation_service.py` — hooks para auto-linking
- `app/services/wells_service.py` — hooks para auto-linking
- `app/main.py` — registrar router plot_events
- `app/main.py` — registrar router plot_analytics
- `app/main.py` — registrar router plot_ml

---

## Key Architectural Decisions

### 1. Modelo unificado `PlotEvent`
- **Por qué**: Simplifica queries (una tabla en lugar de 3 separadas). UI única para todos los eventos. Extensible para futuros tipos.
- **Alternativa descartada**: Múltiples tablas (one per event type) → queries complejas, UI duplicada.

### 2. Auto-linking en capa service (no triggers DB)
- **Por qué**: Lógica en Python es más fácil de testear, debuggear, y mantener que en SQL.
- **Alternativa descartada**: Triggers PostgreSQL → difícil de versionar, menos portable, menos debuggable.

### 3. FK nullable para linked events
- **Por qué**: Permite que PlotEvent exista sin riego/pozo linkedado (eventos manuales). Evita obligar que todo sea linkedado.
- **Alternativa descartada**: Discriminador (SINGLE_TABLE inheritance) → más complicado, menos flexible.

### 4. Unique constraint one-time events a nivel DB
- **Por qué**: Garantiza data consistency incluso si hay concurrency o lógica bypassed.
- **Cómo**: `UNIQUE (plot_id, event_type) WHERE is_recurring = false` — constraint parcial que solo aplica a one-time.

### 5. Dual views sin estado sincronizado en DB
- **Por qué**: Vistas son solo presentación. Mismo backend JSON alimenta ambas.
- **Cómo**: Endpoint `/plot-events/json/` retorna array plano. Frontend JS renderiza como lista o calendario.
- **Ventaja**: Toggle views sin refresh, sin perder scroll/filtros.

### 6. Event types como Enum (no table de lookup)
- **Por qué**: Event types son constantes de negocio, no datos que cambien en runtime.
- **Alternativa descartada**: Tabla de lookup → overhead, query joins innecesarios.

---

## Scope

### Included
- CRUD eventos manuales (labrado, picado, poda, vallado, installed_drip)
- Auto-linking riego y pozos sin duplicación
- Validación de eventos únicos (solo 1 por parcela)
- Dual views (listado + calendario)
- Filtros: date range, event_type, plot
- Sincronización: editar/borrar riego/pozo → PlotEvent actualizado/borrado
- Tests unitarios + integración
- Templates Bootstrap 5 con Spanish i18n
- Analítica histórica por campaña para relación manejo/producción
- Detección de posibles umbrales de riego con evidencia estadística
- Insights explicables por bancal y comparativa entre bancales
- IA/ML gradual para predicción de rendimiento y umbrales robustos

### Not Included (Future Enhancements)
- Notificaciones/reminders ("podar en 2 semanas")
- Reportes ("parcelas no podadas en 6 meses")
- Undo/redo de eventos
- Bulk edit (editar múltiples eventos)
- Export a iCal/CSV
- Mobile-first calendar (usaremos Bootstrap grid, responsive pero no optimizado mobile)
- Recurring tasks automation (crear automáticamente "each 6 months" labrado)
- Recomendación automática totalmente autónoma sin supervisión humana

---

## Discussion Points

### ¿Debería haber restricciones entre tipos de evento?
**Opción A**: Labrado y picado en mismo día → permitido (operaciones diferentes)
**Opción B**: Labrado y picado → mutuamente excluyentes en mismo día
**Recomendación**: Opción A. Son operaciones distintas, pueden ocurrir en secuencia. Sin restricciones.

### ¿Filtrar eventos por campaign_year?
**Opción A**: Always show all events, filter by campaign in UI
**Opción B**: Show only current campaign by default
**Recomendación**: Opción A. Allows viewing historical campaigns. Add campaign filter in UI.

### ¿Qué librería para calendario?
**Opción A**: Bootstrap grid (simple, self-contained)
**Opción B**: Fullcalendar.io (completo pero 40KB, licencia)
**Opción C**: Chart.js (para timelines horizontales)
**Recomendación**: Opción A por ahora. Bootstrap grid es suficiente, 100% control, sin dependencias.

### ¿Editar LinkedEvents (riego/pozo) desde PlotEvent?
**Opción A**: Read-only en PlotEvent, editar always desde riego/pozo
**Opción B**: Permitir editar fecha/notas en PlotEvent, mirror al riego/pozo
**Recomendación**: Opción A. Evita confusión—cada entity tiene su interfaz. Riego tiene "litros", pozo tiene "pozos_por_planta"—esos solo existen en su propia vista.

### ¿Cuándo activar recomendaciones ML para un usuario?
**Opción A**: Activarlas siempre
**Opción B**: Activarlas solo con histórico mínimo y calidad suficiente
**Recomendación**: Opción B. Evita recomendaciones inestables cuando aún hay pocos datos.

---

## Implementation Order (if needed to break into sprints)

1. **Sprint 1 (Datos)**: Model + migration + basic service CRUD
2. **Sprint 2 (Integración)**: Auto-linking hooks en irrigation/wells services
3. **Sprint 3 (Backend)**: Router + endpoints + filtering logic
4. **Sprint 4 (Frontend)**: Templates listado + formulario
5. **Sprint 5 (Calendario)**: Template calendario + toggle views
6. **Sprint 6 (Testing)**: Full test suite, regresión, smoke tests
7. **Sprint 7 (Analítica avanzada)**: Dataset por campaña + insights estadísticos
8. **Sprint 8 (IA/ML)**: Entrenamiento offline + predicción + guardrails + panel ML

---

## Success Criteria

- [ ] Migración ejecuta sin errores, schema verificado en DB
- [ ] CRUD manual de eventos funciona end-to-end
- [ ] Crear riego/pozo → auto-crea PlotEvent linkedado (sin duplicados)
- [ ] Editar riego/pozo → PlotEvent se actualiza
- [ ] Borrar riego/pozo → PlotEvent se borra
- [ ] One-time events se validan (solo 1 por parcela)
- [ ] Listado muestra eventos filtrados por fecha, tipo
- [ ] Calendario muestra eventos visuales por mes
- [ ] Toggle listado ↔ calendario sin perder datos
- [ ] Eventos linkedados (riego/pozo) aparecen read-only en listado
- [ ] Tests unitarios: CRUD, auto-linking, validación, 100% cobertura service
- [ ] Tests integración: flujos end-to-end (crear riego → PlotEvent)
- [ ] Full suite: 58+ tests verdes, zero regressions
- [ ] No duplicate data: un evento no entra 2 veces en DB
- [ ] Multi-tenancy: usuario A no ve eventos de usuario B
- [ ] Dataset por campaña disponible por bancal con métricas de producción, riego y manejo
- [ ] Dashboard analítico operativo con relación riego/producción y manejo/producción
- [ ] Detección y comunicación de meseta de riego (si aplica)
- [ ] Cada insight muestra tamaño de muestra y campañas usadas
- [ ] Pipeline ML reproducible con split temporal y sin leakage
- [ ] Métricas ML (MAE/RMSE/R2) visibles por versión de modelo
- [ ] Recomendaciones ML bloqueadas automáticamente si no hay confianza suficiente

---

## Backlog ejecutable (tickets por sprint)

### Sprint 1: Datos base de eventos

Ticket S1-01: Modelo `PlotEvent` + enums
- Objetivo: introducir entidad unificada de eventos por parcela.
- Entregables:
  - `app/models/plot_event.py`
  - update relaciones en `app/models/plot.py`
- Dependencias: ninguna.
- Estimación: M.
- Done when:
  - modelo creado con relaciones y tipos de evento.
  - revisado que todas las consultas incluyen `user_id`.

Ticket S1-02: Migración Alembic `0007_add_plot_events_table`
- Objetivo: crear tabla e índices en base de datos.
- Entregables:
  - `alembic/versions/0007_add_plot_events_table.py`
- Dependencias: S1-01.
- Estimación: S.
- Done when:
  - `upgrade()` y `downgrade()` implementados.
  - migración aplicada localmente sin errores.

Ticket S1-03: Schemas de eventos
- Objetivo: definir contratos de entrada/salida.
- Entregables:
  - `app/schemas/plot_event.py`
- Dependencias: S1-01.
- Estimación: S.
- Done when:
  - `PlotEventCreate`, `PlotEventUpdate`, `PlotEventResponse` y enum funcionando.

### Sprint 2: Servicios y sincronización automática

Ticket S2-01: `plot_events_service` CRUD + filtros
- Objetivo: encapsular lógica de negocio de eventos.
- Entregables:
  - `app/services/plot_events_service.py`
- Dependencias: Sprint 1 completo.
- Estimación: L.
- Done when:
  - CRUD operativo con filtros por parcela/fecha/tipo.
  - validaciones de ownership y eventos one-time.

Ticket S2-02: Hook riego -> evento
- Objetivo: evitar doble entrada de datos al registrar riego.
- Entregables:
  - cambios en `app/services/irrigation_service.py`
- Dependencias: S2-01.
- Estimación: M.
- Done when:
  - create/update/delete de riego reflejan create/update/delete en `PlotEvent`.
  - sin duplicados por `related_irrigation_id`.

Ticket S2-03: Hook pozo -> evento
- Objetivo: evitar doble entrada de datos al registrar pozos.
- Entregables:
  - cambios en `app/services/wells_service.py`
- Dependencias: S2-01.
- Estimación: M.
- Done when:
  - create/update/delete de pozo reflejan create/update/delete en `PlotEvent`.
  - sin duplicados por `related_well_id`.

### Sprint 3: Router y API de eventos

Ticket S3-01: Router `plot_events`
- Objetivo: exponer endpoints para listado, calendario y CRUD manual.
- Entregables:
  - `app/routers/plot_events.py`
  - registro en `app/main.py`
- Dependencias: Sprint 2 completo.
- Estimación: M.
- Done when:
  - endpoints `GET/POST` operativos con auth y filtros.

Ticket S3-02: Endpoint JSON para dual-view
- Objetivo: fuente única de datos para lista y calendario.
- Entregables:
  - endpoint `/plot-events/json/`
- Dependencias: S3-01.
- Estimación: S.
- Done when:
  - devuelve formato estable y documentado para frontend.

### Sprint 4: UI listado + formulario

Ticket S4-01: Vista listado
- Objetivo: consultar el estado de parcelas en tabla filtrable.
- Entregables:
  - `app/templates/eventos_parcela/list.html`
  - componentes necesarios
- Dependencias: Sprint 3 completo.
- Estimación: M.
- Done when:
  - filtros por fecha/tipo/parcela operativos.
  - eventos linkedados mostrados read-only.

Ticket S4-02: Formulario create/edit manual
- Objetivo: registrar labrado/picado/poda y one-time events.
- Entregables:
  - `app/templates/eventos_parcela/form.html`
- Dependencias: S3-01.
- Estimación: M.
- Done when:
  - validación frontend+backend de one-time events.

### Sprint 5: UI calendario

Ticket S5-01: Vista calendario mensual
- Objetivo: visión temporal rápida del estado por parcela.
- Entregables:
  - `app/templates/eventos_parcela/calendar.html`
  - `components/calendar_grid.html`
- Dependencias: Sprint 4 completo.
- Estimación: M.
- Done when:
  - navegación mes/año.
  - modal de detalle por evento.
  - toggle calendario/listado.

### Sprint 6: Calidad y regresión funcional

Ticket S6-01: Unit tests de servicio eventos
- Objetivo: robustecer lógica de negocio y edge cases.
- Entregables:
  - `tests/services/test_plot_events_service.py`
- Dependencias: Sprint 2-5.
- Estimación: M.
- Done when:
  - pasan tests de CRUD, deduplicación, one-time, aislamiento.

Ticket S6-02: Integration tests eventos+riego+pozos
- Objetivo: validar flujos reales end-to-end.
- Entregables:
  - `tests/integration/test_plot_events_integration.py`
- Dependencias: S6-01.
- Estimación: M.
- Done when:
  - create/update/delete de riego/pozos sincronizan correctamente `PlotEvent`.

### Sprint 7: Analítica estadística avanzada

Ticket S7-01: Dataset por campaña
- Objetivo: unificar señales para análisis de producción.
- Entregables:
  - funciones de agregación en `app/services/plot_analytics_service.py`
- Dependencias: Sprint 6 completo.
- Estimación: L.
- Done when:
  - dataset por `campaign_year` disponible y validado.

Ticket S7-02: Insights estadísticos + umbral base
- Objetivo: detectar relaciones y posibles mesetas de riego.
- Entregables:
  - métodos de correlación y tramos.
  - detección inicial de umbral.
- Dependencias: S7-01.
- Estimación: L.
- Done when:
  - insights con trazabilidad y control de muestra mínima.

Ticket S7-03: UI analítica
- Objetivo: visualizar patrones por bancal y comparativas.
- Entregables:
  - `app/templates/analitica_parcelas/overview.html`
  - `app/templates/analitica_parcelas/plot_detail.html`
- Dependencias: S7-01 y S7-02.
- Estimación: M.
- Done when:
  - panel operativo con series, scatter e insights.

### Sprint 8: IA/ML (predictivo y recomendaciones)

Ticket S8-01: Feature pipeline + split temporal
- Objetivo: preparar entrenamiento reproducible sin leakage.
- Entregables:
  - `app/services/ml_training_service.py`
  - utilidades de versionado de dataset/modelo
- Dependencias: Sprint 7 completo.
- Estimación: L.
- Done when:
  - pipeline reproducible y auditado.

Ticket S8-02: Servicio de inferencia y recomendaciones
- Objetivo: producir recomendaciones con guardrails.
- Entregables:
  - `app/services/plot_ml_service.py`
  - `app/routers/plot_ml.py`
- Dependencias: S8-01.
- Estimación: L.
- Done when:
  - predicciones + confianza + explicación.
  - bloqueo automático con muestra/confianza baja.

Ticket S8-03: Validación ML + UI de insights
- Objetivo: exponer valor de negocio sin caja negra.
- Entregables:
  - `app/templates/analitica_parcelas/ml_insights.html`
  - tests ML unit/integration
- Dependencias: S8-02.
- Estimación: M.
- Done when:
  - métricas MAE/RMSE/R2 visibles por versión.
  - insights ML mostrados con estado robusta/exploratoria/datos insuficientes.

---

## Riesgos principales y mitigación

Riesgo R1: insuficiencia de histórico por usuario
- Mitigación: fallback automático a analítica estadística (sin ML).

Riesgo R2: leakage temporal en entrenamiento
- Mitigación: split temporal estricto y tests específicos de leakage.

Riesgo R3: recomendaciones inestables entre campañas
- Mitigación: umbrales de confianza mínimos y monitorización de estabilidad.

Riesgo R4: sobrecarga funcional en frontend
- Mitigación: activación gradual por feature flag (`analytics_enabled`, `ml_enabled`).

---

## Definición de Ready (DoR) y Done (DoD)

DoR por ticket:
- Requisito funcional descrito.
- Casos borde identificados.
- Datos y permisos (`user_id`) definidos.

DoD por ticket:
- Implementación en capa correcta (router/service/model).
- Tests de unidad/integración según impacto.
- Sin regresión en suite existente.
- Revisión de seguridad multi-tenant.
