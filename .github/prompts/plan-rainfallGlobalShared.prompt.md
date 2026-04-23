# Plan: Rainfall records AEMET/Ibericam sin user_id

## Objetivo
Hacer que los registros importados de AEMET e Ibericam sean globales (user_id = NULL), evitando duplicados entre usuarios. Los registros manuales siguen siendo por usuario.

## Decisiones tomadas
- `source="manual"` → user_id obligatorio (sin cambios)
- `source="aemet"` / `source="ibericam"` → user_id = NULL (compartidos)
- Shared records son **de solo lectura** (sin botones edit/delete en UI)
- Lista muestra shared records solo de los municipios de las parcelas del usuario
- La deduplicación sigue siendo a nivel aplicación (upsert sin UNIQUE constraint en DB)

## Archivos a modificar

### Fase 1 — Modelo + Migración
- `app/models/rainfall.py` — hacer user_id nullable (quitar `nullable=False`)
- `alembic/versions/0014_make_rainfall_user_id_nullable.py` — nueva migración:
  ALTER COLUMN user_id DROP NOT NULL + actualizar/añadir índices

### Fase 2 — Services AEMET/Ibericam
- `app/services/aemet_service.py`:
  - `upsert_aemet_rainfall(db, user_id, ...)` → quitar user_id param; set user_id=None; filtrar con user_id IS NULL
  - `import_aemet_rainfall(db, user_id, ...)` → quitar user_id param
- `app/services/ibericam_service.py`:
  - `upsert_ibericam_rainfall(db, user_id, ...)` → igual
  - `import_ibericam_rainfall(db, user_id, ...)` → igual

### Fase 3 — rainfall_service.py
- `list_rainfall_records`: cambiar query a OR condition:
  (user_id == X) OR (user_id IS NULL AND municipio_cod IN user_plot_municipios)
- `get_rainfall_record`: permitir acceso si record.user_id IS NULL (shared)
- `update_rainfall_record`: bloquear si record.user_id is None → raise/403
- `delete_rainfall_record`: bloquear si record.user_id is None → raise/403
- `get_rainfall_for_plot_on_date`: municipio fallback → OR(user_id==X, user_id IS NULL)
- `_get_user_municipios`: obtener desde plots del usuario (no solo desde records)
- `create_rainfall_record`: añadir validación source == "manual"

### Fase 4 — Router (lluvia.py)
- Quitar user_id de llamadas a import_aemet_rainfall / import_ibericam_rainfall
- Endpoints GET/POST /lluvia/{id}/editar: si record.user_id is None → flash error + redirect a /lluvia/
- Endpoint POST /lluvia/{id}/eliminar: si record.user_id is None → flash error + redirect a /lluvia/

### Fase 5 — Schema
- `app/schemas/rainfall.py`: user_id en RainfallResponse → Optional[int]

### Fase 6 — Template (read-only UI para AEMET/Ibericam)
- `app/templates/lluvia/list.html`, columna Acciones:
  - Botón Editar: ya está bajo `{% if r.source == 'manual' %}` (sin cambios)
  - Botón Eliminar: añadir la misma condición `{% if r.source == 'manual' %}` (actualmente visible para todos)
  - Para filas aemet/ibericam la columna Acciones queda vacía o con badge "Compartido" / icono candado

### Fase 7 — Tests
- `tests/services/test_aemet_service.py`: quitar user_id de upsert calls
- `tests/services/test_ibericam_service.py`: quitar user_id de upsert/import calls
- `tests/integration/test_rainfall_integration.py`:
  - Actualizar tests de aislamiento (shared records visibles por municipio, no por user_id)
  - Añadir test: dos usuarios importan misma fecha/municipio → solo 1 registro en DB

### Fase 8 — Admin: panel de lluvia + importación manual
- Nueva ruta GET `/admin/lluvia` (en admin.py): muestra tabla de municipios del sistema
- Nueva función `get_admin_rainfall_overview(db)` en `app/services/admin_service.py`:
  - Query 1: todos los `municipio_cod` distintos de Plot (sin filtro user_id), con count de parcelas
  - Query 2: MIN(date) y MAX(date) de rainfall_records WHERE source='aemet' AND user_id IS NULL GROUP BY municipio_cod
  - Query 3: igual para source='ibericam'
  - Nombre del municipio: RainfallRecord.municipio_name → MUNICIPIO_COD_TO_NAME → fallback cod
  - Retorna lista de dicts: municipio_cod, municipio_name, num_plots, aemet_desde, aemet_hasta, ibericam_desde, ibericam_hasta
- Tabla en `admin/lluvia_overview.html`:
  | Municipio | Parcelas | AEMET (desde - hasta) | Ibericam (desde - hasta) | Acciones |
  - Fila con cobertura vacía → badge "Sin datos" en rojo
  - Botón "Importar AEMET" → redirect a `/admin/lluvia/{municipio_cod}/importar/aemet` con fechas prerellenadas (max_date+1 → hoy, o inicio del año si sin datos)
  - Botón "Importar Ibericam" → igual para ibericam
- Rutas de importación admin (GET form + POST acción):
  - GET `/admin/lluvia/{municipio_cod}/importar/aemet` → formulario con station_code, date_from (pre-filled), date_to (pre-filled)
  - POST → llama `import_aemet_rainfall(db, municipio_cod=..., station_code=..., date_from=..., date_to=...)` (sin user_id)
  - GET/POST `/admin/lluvia/{municipio_cod}/importar/ibericam` → igual
  - Reutilizar lógica JS AJAX de importación existente adaptada al contexto admin

### Fase 9 — Eliminar importación para usuarios normales
- `app/routers/lluvia.py`: eliminar endpoints GET/POST de `/lluvia/importar/aemet` e `/lluvia/importar/ibericam`
- Eliminar los templates `lluvia/importar_aemet.html` y `lluvia/importar_ibericam.html` (o moverlos a admin/)
- Eliminar/esconder el acceso a esas rutas desde la UI de usuario

### Fase 10 — Fly.io Scheduled Machine (cron diario)
- `scripts/import_rainfall_cron.py`: script Python standalone que:
  1. Conecta a la DB (via DATABASE_URL del entorno)
  2. Obtiene todos los municipio_cod distintos de Plot (todos los usuarios)
  3. Para cada municipio: llama `import_aemet_rainfall` e `import_ibericam_rainfall` desde ayer → hoy
  4. Loguea resultados (created/updated por municipio y fuente)
- `fly.toml`: añadir proceso cron con schedule diario ejecutando el script anterior
- Requiere que las vars de entorno `DATABASE_URL` y `AEMET_API_KEY` estén disponibles en la máquina cron

## Verificación
1. `uv run pytest tests/ -x` — todos los tests verdes
2. Importar mismo municipio+fechas dos veces desde admin → 2ª llamada devuelve `created=0`
3. Filas AEMET/Ibericam en `/lluvia/` sin botones Editar ni Eliminar
4. `/admin/lluvia` muestra cobertura real; municipios sin datos muestran badge rojo
5. Botón "Importar AEMET" de un municipio abre formulario con fechas pre-rellenadas
6. `alembic upgrade head` sin errores
7. Script cron ejecuta sin errores con DB y API key disponibles
