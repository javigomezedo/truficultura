# Sprint 1 - Checklist Técnico Implementable

Fecha: 18/04/2026
Objetivo del sprint: añadir caudal de riego por parcela (litros/segundo) como base para la futura simulación de horas recomendadas.

## 1. Resultado del Sprint

Al finalizar el sprint, la aplicación debe permitir:

1. Guardar el caudal de entrada de agua por parcela en litros/segundo.
2. Exigir este dato cuando la parcela tenga riego activo.
3. Validar que el caudal sea mayor que 0.
4. Mostrar y editar el valor en formularios de parcelas.
5. Mantener toda la suite de tests en verde.

## 2. Alcance In / Out

### In scope

- Modelo de datos de parcela.
- Validaciones de dominio de parcela con riego.
- Formularios y flujo de alta/edición.
- Pruebas unitarias y de router relacionadas.

### Out of scope

- Integración AEMET.
- Turnos externos de riego.
- Motor de simulación.
- Recomendación automática de horas.

## 3. Cambios por fichero

## 3.1 Modelo y esquema

### Archivo: app/models/plot.py

Tareas:

1. Añadir columna `water_flow_lps` (Float, nullable=True).
2. Mantener compatibilidad con parcelas sin riego (`has_irrigation=false`).

Criterios:

- El modelo migra sin romper entidades existentes.

### Archivo: app/schemas/plot.py

Tareas:

1. Añadir campo `water_flow_lps: Optional[float]` en `PlotBase` y `PlotUpdate`.
2. Añadir validación de reglas:
   - Si `has_irrigation=true`, `water_flow_lps` requerido.
   - Si `water_flow_lps` informado, debe ser `> 0`.

Criterios:

- Esquemas rechazan combinaciones inválidas.

## 3.2 Capa de servicios

### Archivo: app/services/plots_service.py

Tareas:

1. Añadir parámetro `water_flow_lps` en `create_plot`.
2. Añadir parámetro `water_flow_lps` en `update_plot`.
3. Aplicar validación de negocio antes de persistir.
4. Guardar valor en la entidad `Plot`.

Criterios:

- Alta y edición cumplen reglas de negocio.
- No se altera la lógica de porcentajes ni multi-tenant.

## 3.3 Capa de routers

### Archivo: app/routers/plots.py

Tareas:

1. Añadir `water_flow_lps` como `Form(...)` opcional en create/update.
2. Pasar el valor al servicio.
3. Gestionar validación fallida con mensaje amigable (si aplica al patrón actual).

Criterios:

- El flujo web de parcelas acepta y guarda el dato.

## 3.4 Plantillas

### Archivo: app/templates/parcelas/form.html

Tareas:

1. Añadir campo de formulario para caudal (`L/s`).
2. Mostrar pista de uso: "Dato necesario para estimar horas recomendadas de riego".
3. UX sugerida:
   - Mostrar campo siempre.
   - Marcar como obligatorio cuando "tiene riego" esté activo.

Criterios:

- En edición se visualiza valor actual.
- En creación permite introducirlo correctamente.

### Archivo: app/templates/parcelas/list.html

Tareas opcionales (si entra en sprint):

1. Añadir columna resumen de caudal para visibilidad operativa.

Criterios:

- No rompe diseño actual.

## 3.5 Migración Alembic

### Carpeta: alembic/versions/

Tareas:

1. Generar migración para añadir `water_flow_lps` en `plots`.
2. Revisar manualmente `upgrade()` y `downgrade()`.

Criterios:

- Upgrade añade columna.
- Downgrade elimina columna.

## 4. Reglas de negocio (Sprint 1)

1. `has_irrigation=false`:
   - `water_flow_lps` puede ser null.
2. `has_irrigation=true`:
   - `water_flow_lps` obligatorio.
   - `water_flow_lps > 0`.
3. El valor representa litros/segundo en la entrada de la instalación de esa parcela.

## 5. Casos de prueba mínimos obligatorios

## 5.1 Tests de servicio

### Archivo: tests/services/test_plots_service.py

Añadir/actualizar casos:

1. Crear parcela con riego y caudal válido -> OK.
2. Crear parcela con riego y caudal ausente -> error de validación.
3. Crear parcela con riego y caudal <= 0 -> error.
4. Crear parcela sin riego y caudal nulo -> OK.
5. Editar parcela activando riego sin caudal -> error.
6. Editar parcela con caudal válido -> persiste correctamente.

## 5.2 Tests de router

### Archivo: tests/test_plots_router.py

Añadir/actualizar casos:

1. POST create con riego + caudal válido -> redirección OK.
2. POST create con riego + caudal inválido -> respuesta esperada (error o mensaje).
3. POST update con cambios de caudal -> redirección OK y llamada correcta al servicio.

## 5.3 Test de integración (si aplica en sprint)

- Verificar persistencia real de columna en flujo create/edit de parcela.

## 6. Orden recomendado de implementación

1. Modelo (`app/models/plot.py`).
2. Migración Alembic.
3. Esquema (`app/schemas/plot.py`).
4. Servicio (`app/services/plots_service.py`).
5. Router (`app/routers/plots.py`).
6. Templates (`app/templates/parcelas/form.html` y opcional `list.html`).
7. Tests (`tests/services/test_plots_service.py`, `tests/test_plots_router.py`).
8. Ejecución de suite completa.

## 7. Comandos de verificación

1. Ejecutar tests de parcelas:

   .venv/bin/python -m pytest -q tests/services/test_plots_service.py tests/test_plots_router.py

2. Ejecutar suite completa (obligatorio):

   .venv/bin/python -m pytest -q tests/

## 8. Checklist de cierre

- [ ] Columna `water_flow_lps` añadida con migración reversible.
- [ ] Reglas de validación aplicadas y probadas.
- [ ] Formularios de parcela actualizados.
- [ ] Tests unitarios y de router actualizados.
- [ ] Suite completa en verde.
- [ ] Documentación de plan y alcance actualizada.

## 9. Puente a Sprint 2

Con este sprint cerrado, la base queda preparada para:

1. Convertir horas de riego en volumen real aplicado.
2. Cruce de volumen de riego con lluvia AEMET.
3. Recomendación futura de "regar/no regar" y "cuántas horas" por turno.
