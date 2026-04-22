# Plan: Registro de Lluvia — Modelo, UI y Fuentes Externas

Añadir un módulo de precipitaciones con una tabla unificada `RainfallRecord` que centralice datos de tres fuentes (pluviómetro manual, AEMET, ibericam). Los registros manuales van ligados a una parcela concreta; los de AEMET/ibericam se almacenan a nivel de municipio. La consulta de lluvia de una parcela aplica la regla "parcela primero, municipio como fallback".

---

## Fase 1 — Infraestructura base

1. **Nuevo modelo `app/models/rainfall.py`** — siguiendo el patrón de `irrigation.py`:
   - Campos: `id`, `user_id` (FK NOT NULL), `plot_id` (FK, nullable), `municipio_cod` (String, nullable), `date` (Date), `precipitation_mm` (Float), `source` (String 20, enum `manual|aemet|ibericam`), `notes` (String 500, nullable)
   - Índices compuestos: `(user_id, date)`, `(user_id, plot_id, date)`, `(user_id, municipio_cod, date)`
   - Relationships: `user`, `plot` (lazy="joined")

2. **Actualizar `app/models/plot.py`** — añadir `rainfall_records: Mapped[List["RainfallRecord"]]` con lazy="select"

3. **Actualizar `app/models/__init__.py`** — importar y exportar `RainfallRecord`

4. **Migración `alembic/versions/0011_add_rainfall_records.py`** — tabla `rainfall_records`, FKs con `ondelete="CASCADE"` para `user_id` y `SET NULL` para `plot_id`. Implementar `upgrade()` y `downgrade()`.

5. **Schema `app/schemas/rainfall.py`**:
   - `RainfallCreate`: `plot_id` (optional), `municipio_cod` (optional), `date`, `precipitation_mm`, `source` (default `"manual"`), `notes`
   - `RainfallUpdate`: todos los campos opcionales
   - Validador: debe tener `plot_id` OR `municipio_cod` (no ambos nulos a la vez)

6. **Servicio `app/services/rainfall_service.py`** con las funciones:
   - `list_rainfall_records(db, user_id, plot_id?, municipio_cod?, year?)` — siempre filtra por `user_id`
   - `get_rainfall_record(db, id, user_id)` → 404 si no pertenece al usuario
   - `create_rainfall_record(db, data, user_id)`
   - `update_rainfall_record(db, id, data, user_id)`
   - `delete_rainfall_record(db, id, user_id)`
   - `get_rainfall_for_plot_on_date(db, plot, date, user_id)` — lógica de prioridad: busca primero `plot_id=plot.id`, sino por `municipio_cod=plot.municipio_cod AND plot_id IS NULL`
   - `get_rainfall_list_context(db, user_id, year?, plot_id?)` — datos para la vista listado, agrupados por campaña

7. **Tests unitarios `tests/services/test_rainfall_service.py`** — patrón `FakeExecuteResult` de `conftest.py`, decorados `@pytest.mark.asyncio`. Cubrir:
   - `list_rainfall_records`: lista vacía, lista con resultados, filtros por plot y municipio
   - `get_rainfall_record`: encontrado, no encontrado, pertenece a otro usuario
   - `create_rainfall_record`: `db.add` llamado, objeto retornado correcto
   - `update_rainfall_record`, `delete_rainfall_record`
   - `get_rainfall_for_plot_on_date`: caso con registro de parcela exacto, caso con fallback a municipio, caso sin datos

8. **Tests de integración `tests/integration/test_rainfall_integration.py`** — SQLite en memoria, verificar la lógica de prioridad parcela/municipio con relaciones reales

---

## Fase 2 — UI manual (depende de Fase 1)

9. **Router `app/routers/lluvia.py`**:
   - `GET /lluvia/` — listado con filtros (año campaña, parcela, fuente)
   - `GET /lluvia/nuevo` — formulario alta
   - `POST /lluvia/` — crear registro
   - `GET /lluvia/{id}/editar` — formulario edición
   - `POST /lluvia/{id}/editar` — actualizar
   - `POST /lluvia/{id}/eliminar` — eliminar

10. **Templates `app/templates/lluvia/`**:
    - `list.html` — tabla con fecha, parcela / municipio, mm, fuente; filtros; totales por mes
    - `form.html` — formulario Bootstrap 5 (parcela vs municipio selector; campo fuente)

11. **Registrar router en `app/main.py`** y añadir enlace en `app/templates/base.html`

---

## Fase 3 — Integración AEMET (puede avanzar en paralelo con Fase 2, depende de Fase 1)

12. **Investigar branch `backup/wip-aemet-eventos-2026-04-20`** — extraer la lógica del servicio AEMET ya implementada (`aemet_service.py`, mapeo estación↔municipio, endpoint de clima diario)

13. **Config `app/config.py`** — añadir `aemet_api_key: Optional[str] = None` (con `settings`); añadir a `.env.example`

14. **Servicio `app/services/aemet_service.py`** basado en el WIP:
    - `get_daily_precipitation(api_key, station_id, date_from, date_to) → list[dict]` — llama a `GET /api/valores/climatologicos/diarios/datos/fechaini/{}/fechafin/{}/estacion/{}` de la API AEMET OpenData
    - `find_nearest_station(municipio_cod) → str` — mapeo municipio → `idema` de estación AEMET
    - `import_aemet_rainfall(db, user_id, municipio_cod, date_from, date_to)` — llama al API y crea `RainfallRecord`s con `source="aemet"`, saltando los que ya existen para esa fecha/municipio (upsert por `(user_id, municipio_cod, date, source)`)

15. **Endpoints de importación en `app/routers/lluvia.py`**:
    - `GET /lluvia/importar/aemet` — formulario: seleccionar municipio, rango de fechas
    - `POST /lluvia/importar/aemet` — llamada a `import_aemet_rainfall`, redirige con flash de resumen
    - `GET /lluvia/importar/manual` — subida de CSV simple `fecha;mm;municipio_cod`
    - `POST /lluvia/importar/manual` — procesa CSV

16. **Test `tests/services/test_aemet_service.py`** — mockear `httpx` o `aiohttp` para simular respuestas AEMET

---

## Fase 4 — Integración ibericam (independiente, puede avanzar tras Fase 1)

17. **Investigación del endpoint ibericam** — los datos de las gráficas se cargan via AJAX/JS; pasos:
    - Abrir `https://ibericam.com/teruel/informe-estacion-meteorologica-de-sarrion/` en DevTools → pestaña Network → filtrar XHR/Fetch
    - Identificar la URL del endpoint JSON (probable patrón `ibericam.com/api/estacion/{id}/datos/{mes}` o similar)
    - Documentar parámetros, formato de respuesta y si requiere cookies/auth
    - Confirmar si los datos históricos (más de un mes) son accesibles
    - Si los datos están embebidos en HTML (no AJAX), el scraping sería con BeautifulSoup

18. **Servicio `app/services/ibericam_service.py`** (condicional a que haya endpoint viable):
    - `get_daily_precipitation(municipio_slug, year, month)` — HTTP GET al endpoint descubierto
    - `import_ibericam_rainfall(db, user_id, municipio_cod, municipio_slug, year, month)` → crea `RainfallRecord`s con `source="ibericam"`
    - Añadir mapping `ibericam_slug ↔ municipio_cod INE` como constante o config de usuario

19. **Endpoints de importación** — `GET/POST /lluvia/importar/ibericam` — formulario con municipio y mes/año

---

## Archivos a modificar / crear

| Acción | Fichero |
|--------|---------|
| Crear | `app/models/rainfall.py` |
| Modificar | `app/models/plot.py` — añadir relationship |
| Modificar | `app/models/__init__.py` — añadir export |
| Crear | `alembic/versions/0011_add_rainfall_records.py` |
| Crear | `app/schemas/rainfall.py` |
| Crear | `app/services/rainfall_service.py` |
| Crear | `app/services/aemet_service.py` (Fase 3) |
| Crear | `app/services/ibericam_service.py` (Fase 4, condicional) |
| Crear | `app/routers/lluvia.py` |
| Modificar | `app/main.py` — registrar router |
| Modificar | `app/templates/base.html` — enlace navegación |
| Crear | `app/templates/lluvia/list.html` |
| Crear | `app/templates/lluvia/form.html` |
| Modificar | `app/config.py` — añadir `aemet_api_key` (Fase 3) |
| Modificar | `.env.example` — añadir `AEMET_API_KEY` (Fase 3) |
| Crear | `tests/services/test_rainfall_service.py` |
| Crear | `tests/services/test_aemet_service.py` (Fase 3) |
| Crear | `tests/integration/test_rainfall_integration.py` |

---

## Verificación

1. `alembic upgrade head` — migración aplica sin errores
2. `.venv/bin/python -m pytest -q tests/` — suite completa verde (≥58 tests + los nuevos)
3. Prueba manual: crear registro manual desde UI → aparece en el listado
4. Prueba fallback: crear registro de municipio → consultarlo desde una parcela de ese municipio → retorna el registro
5. AEMET: configurar `AEMET_API_KEY` y lanzar importación para un municipio + rango de fechas → verificar registros en BD
6. ibericam (tras investigación): importar datos de un mes → verificar registros en BD con `source="ibericam"`

---

## Decisiones de diseño

- `plot_id` nullable — registro de municipio (`plot_id=NULL`) aplica a todas las parcelas del municipio por fallback en `get_rainfall_for_plot_on_date`
- Sin integración con `PlotEvent` en esta iteración — la lluvia tendrá su propio listado; se puede enlazar al timeline de parcela en el futuro
- AEMET: API OpenData gratuita (requiere registro y `AEMET_API_KEY`). Si el WIP branch ya tiene la lógica de mapeo estación↔municipio, se reutilizará directamente
- ibericam: la Fase 4 depende de que la investigación del endpoint sea exitosa; si no hay API accesible, la alternativa es importación manual por CSV

## Consideraciones abiertas

1. **ibericam sin API pública**: si los datos están embebidos en JS o requieren cookies de sesión, el scraping puede ser frágil. Alternativa: importación por CSV donde el usuario pega los datos manualmente.
2. **AEMET estación más cercana**: el mapeo `municipio_cod → idema` requiere una tabla estática o una llamada al API de inventario de AEMET. El WIP branch puede ya tener esto resuelto.
3. **Gráficas de lluvia**: añadir chart de precipitación acumulada por campaña en el dashboard o en la vista de parcela queda fuera de scope aquí pero es el siguiente paso lógico.
