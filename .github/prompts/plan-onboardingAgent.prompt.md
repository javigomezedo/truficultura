# Plan: Agente IA de onboarding de datos históricos (LangGraph)

## TL;DR

Construir un agente LangGraph integrado en Trufiq que reciba ficheros Excel arbitrarios de clientes, detecte la entidad (parcelas, gastos, ingresos), proponga mapeo de columnas usando OpenAI (solo cabeceras + filas sintéticas), permita al usuario resolver ambigüedades y previsualizar el resultado, y finalmente genere los CSV en el formato exacto que espera `app/services/import_service.py` o invoque directamente las funciones de importación.

MVP cubre **3 entidades**: parcelas, gastos, ingresos. Solo Excel (.xlsx/.xls). Revisión humana obligatoria.

## Decisiones tomadas

- **Framework**: LangGraph (manejo de estado, ciclos, human-in-the-loop)
- **LLM**: OpenAI (GPT-4o / GPT-4.1) vía `langchain-openai` con `with_structured_output()`
- **Formatos fuente v1**: Solo Excel (xlsx/xls). SQL/BD queda para v2
- **Entidades v1 (MVP)**: parcelas + gastos + ingresos
- **Entidades v2**: producción/trufas, riego, labores
- **Integración**: dentro de Trufiq como router FastAPI (`/onboarding`)
- **Privacidad**: al LLM solo se envían cabeceras y filas sintéticas (valores genéricos)
- **Ambigüedades**: chat/formulario interactivo en flujo HTTP multi-paso
- **Revisión humana**: obligatoria — preview de tabla antes de confirmar import
- **Persistencia de estado**: tabla `onboarding_sessions` con `state_json`
- **Datos de prueba**: 3 ficheros Excel sintéticos generados como fixtures; datos reales (anonimizados) si llegan después afinan los prompts pero no bloquean

## Alcance

**Incluido en MVP:**
- Upload de Excel y parsing con openpyxl (celdas fusionadas, detección de cabecera)
- Detección de entidad y mapeo de columnas con LLM
- Resolución interactiva de ambigüedades
- Transformación local (fechas, números europeos, normalización)
- Validación contra reglas de `import_service.py`
- Preview con filas válidas/erróneas
- Importación directa o descarga de CSV

**Excluido (v2+):**
- SQL dumps / exportaciones BD
- PDF, Google Sheets, ODS, DOCX
- Entidades: producción, riego, labores, plantas, lluvia, pozos, brulé, presencias, cosechas, gastos_recurrentes
- Múltiples hojas mapeadas a entidades distintas en un único upload
- Memoria del mapeo por usuario (aprender de onboardings anteriores)

---

## Estructura de archivos nueva

```
app/
  services/onboarding/
    __init__.py
    agent.py             # Construcción del grafo LangGraph
    state.py             # OnboardingState TypedDict
    excel_parser.py      # Parsing con openpyxl
    entity_schemas.py    # Esquemas objetivo (parcelas/gastos/ingresos)
    llm_nodes.py         # Nodos LLM: detect_entity, propose_mapping
    transform_nodes.py   # Transformación local sin LLM
    validate_nodes.py    # Reglas de negocio
    csv_writer.py        # Generación CSV formato import_service
  routers/onboarding.py
  models/onboarding.py   # OnboardingSession
  templates/onboarding/
    index.html
    ambiguities.html
    preview.html
    result.html
alembic/versions/
  NNNN_add_onboarding_sessions.py
tests/
  test_onboarding_router.py
  services/test_onboarding_agent.py
  services/test_excel_parser.py
  services/test_transform_nodes.py
  fixtures/onboarding/
    parcelas_limpio.xlsx
    gastos_cabeceras_irregulares.xlsx
    ingresos_celdas_fusionadas.xlsx
```

---

## Fases

### Fase 0 — Fundamentos (sin LLM)

**Objetivo:** infraestructura completa funcionando antes de invocar a OpenAI.

1. Añadir dependencias en `pyproject.toml`: `langgraph`, `langchain-openai`, `langchain-core`, `openpyxl`. Reusar `OPENAI_API_KEY` desde `app/config.py` (verificar si ya existe; añadir setting si no).
2. Crear modelo `OnboardingSession` en `app/models/onboarding.py`:
   - Campos: `id`, `user_id` (FK), `status` (enum: `uploaded|mapping|awaiting_user|previewing|imported|cancelled|error`), `entity_type`, `original_filename`, `state_json` (JSONB), `created_at`, `updated_at`.
   - Multi-tenancy: filtrar siempre por `user_id` (regla obligatoria de Trufiq).
3. Migración Alembic con `upgrade()` y `downgrade()` (índice por `user_id` + `status`).
4. `entity_schemas.py`: estructuras Python que describen los campos destino de parcelas/gastos/ingresos, marcando obligatorios/opcionales, tipo (`date|number|text|enum`) y enumeraciones permitidas. Reflejan exactamente las firmas de `import_expenses_csv`, `import_incomes_csv`, `import_plots_csv`.
5. `state.py`: `OnboardingState` TypedDict con `session_id`, `headers`, `sample_rows`, `entity_type`, `proposed_mapping`, `ambiguities`, `resolved_mapping`, `transformed_rows`, `validation_errors`, `csv_output`.
6. `excel_parser.py`: extrae hojas de un xlsx/xls; detecta fila de cabecera (heurística: primera fila con ≥3 celdas no vacías y mayoría texto); resuelve celdas fusionadas propagando valor; devuelve `(headers, sample_rows[:5])`.
7. Router `app/routers/onboarding.py` con esqueleto:
   - `GET /onboarding/` — landing.
   - `POST /onboarding/upload` — guarda fichero temporal + crea sesión.
   - `GET /onboarding/{id}` — dispatcher según `status`.
   - `POST /onboarding/{id}/cancel` — marca cancelada.
   - Registrar router en `app/main.py`. Aplicar `require_write_access`.
8. Generar fixtures Excel sintéticos (3 ficheros: limpio / cabeceras irregulares / celdas fusionadas) mediante un script reproducible en `tests/fixtures/onboarding/_generate.py` que use openpyxl.

**Verificación Fase 0:**
- `alembic upgrade head` aplica la migración sin errores.
- Test unitario: `excel_parser.parse(fixture)` devuelve cabeceras y filas correctas para los 3 fixtures.
- Test integración: `POST /onboarding/upload` crea fila en `onboarding_sessions` y redirige a `/onboarding/{id}`.
- `pytest` sigue 100% verde.

---

### Fase 1 — Grafo LangGraph + nodos LLM

**Objetivo:** detectar entidad y proponer mapeo de columnas.

1. `llm_nodes.py` — Nodo `detect_entity`:
   - Prompt sistema: descripción de Trufiq + lista de entidades soportadas.
   - Input: solo cabeceras + nombre de hoja.
   - `with_structured_output(EntityDetection)` donde `EntityDetection` es Pydantic con `entity_type: Literal[...]` y `confidence: float`.
   - Si `entity_type=desconocido` o `confidence<0.6` → estado `awaiting_user` con pregunta "¿Qué tipo de datos contiene este fichero?".
2. `llm_nodes.py` — Nodo `propose_mapping`:
   - Input: cabeceras + 2-3 filas **sintéticas** (anonimizar antes: fechas → `01/01/2024`, números → `100,00`, strings cortos se mantienen tal cual).
   - Función `_anonymize_sample()` aplica reglas por tipo detectado heurísticamente.
   - Output Pydantic `ColumnMapping[]` con `source_column`, `target_field`, `confidence`, `reason`, `transformation_hint` (ej: `date_dmy`, `number_eu`).
   - Para campos obligatorios del esquema sin mapeo → entrada con `target_field=MISSING`.
3. `agent.py` — construir grafo LangGraph:
   - Nodos: `parse_excel → detect_entity → (check ambigüedad entidad) → propose_mapping → (check ambigüedades columnas) → END (pausa para usuario)`.
   - Persistencia: usar `MemorySaver` inicialmente; pasar a checkpointer con BD propia más adelante si interesa. Para el MVP basta con serializar `state` en `OnboardingSession.state_json` tras cada nodo.
4. Umbral de ambigüedad: confianza columna `<0.75` o múltiples columnas mapeadas al mismo campo obligatorio → añadir a `ambiguities`.
5. Integrar invocación del grafo en `POST /onboarding/upload`: ejecuta hasta el primer "punto de pausa" y persiste estado.

**Verificación Fase 1:**
- Test con mock de OpenAI (usando `langchain-core` `FakeListChatModel` o stub) validando que el grafo avanza con outputs estructurados predeterminados.
- Test end-to-end con OpenAI real (marcado `@pytest.mark.llm`, opcional) que sube `gastos_cabeceras_irregulares.xlsx` y verifica que detecta `entity_type=gastos` y mapea ≥80% de columnas con confianza alta.
- Verificar que en el log/BD no aparecen valores reales de las filas (solo cabeceras y muestras anonimizadas).

---

### Fase 2 — Human-in-the-loop (UI multi-paso)

**Objetivo:** usuario resuelve ambigüedades y aprueba preview.

1. Template `ambiguities.html`:
   - Por cada ambigüedad: nombre columna fuente + dropdown con campos del esquema destino + opción "Ignorar columna".
   - Si entidad ambigua, primer paso es seleccionar tipo de entidad.
   - Bootstrap 5, Spanish strings, extiende `base.html`.
2. Endpoint `POST /onboarding/{id}/resolve`:
   - Aplica respuestas del usuario al `state.resolved_mapping`.
   - Reanuda el grafo (transition `awaiting_user → transform`).
3. Si tras resolver siguen quedando campos obligatorios sin mapear → segundo formulario explicando qué falta y opciones (cancelar / asignar valor por defecto cuando aplique, ej: `categoria` por defecto).
4. Template `preview.html`:
   - Tabla paginada (50 filas/página) con filas transformadas.
   - Resaltar filas con error en rojo + tooltip con motivo.
   - Resumen arriba: `X filas válidas | Y filas con error | Z filas a importar`.
   - Botones "Confirmar e importar" / "Descargar CSV" / "Cancelar".
5. Endpoint `POST /onboarding/{id}/confirm`:
   - Llama directamente a la función correspondiente de `import_service.py` con el CSV en memoria (`io.StringIO`), respetando `user_id`.
   - Marca sesión `imported`.
6. Endpoint `GET /onboarding/{id}/download` — descarga el CSV generado.
7. Dispatcher `GET /onboarding/{id}` redirige al template adecuado según `status`.

**Verificación Fase 2:**
- Test integración: simulación completa del flujo con cliente HTTP (upload → resolve → confirm) usando un fixture con ambigüedad provocada.
- Test de seguridad: usuario A no puede ver/manipular `onboarding_sessions` de usuario B (404).
- Validar manualmente la UX en navegador con los 3 fixtures.

---

### Fase 3 — Transformación, validación y cierre

**Objetivo:** convertir datos sin LLM con robustez, validar contra reglas de negocio, generar CSV idénticos a los del sistema actual.

1. `transform_nodes.py`:
   - **Fechas**: parser tolerante (`dateutil.parser` con `dayfirst=True`, fallback a número de serie Excel, fallback a regex `YYYY-MM-DD`). Salida siempre `DD/MM/YYYY`.
   - **Números**: detección automática de formato (1,234.56 vs 1.234,56), normalización a coma decimal sin separador de miles.
   - **Nombres de parcela**: matching fuzzy (`rapidfuzz`) contra parcelas existentes del `user_id`; si coincidencia >85% sugerir corrección, marcar como warning si <85%.
   - **Enums**: normalizar a minúsculas/sin acentos antes de validar contra la enumeración del esquema.
2. `validate_nodes.py`:
   - Reproducir las validaciones que hace `import_service.py` (columnas mínimas, tipos, formato fechas) y emitir errores por fila con `{row_index, column, message}`.
   - Reglas extra: para gastos, si `bancal` no existe en BD del usuario y no está vacío → warning "se importará como general".
3. `csv_writer.py`:
   - Genera CSV con `csv.writer(delimiter=';')`, sin cabecera, en el orden exacto que espera `import_service.py` para cada entidad.
   - Test parametrizado verifica que el CSV generado se puede importar directamente por `import_service.py` con 0 errores.
4. Integrar nodos 5 y 6 en el grafo entre `resolve` y `awaiting_preview`.
5. Manejo de errores global del agente:
   - Excepciones LLM (rate limit, timeout) → estado `error` con mensaje al usuario y botón "Reintentar".
   - Logging con `structlog` (ya usado en el proyecto, según `observability.py`).
6. Documentación de usuario en `app/templates/onboarding/index.html` con limitaciones conocidas y formatos soportados.

**Verificación Fase 3:**
- Test parametrizado: para cada fixture, ejecutar el flujo completo y validar que el CSV resultante es importable por `import_service.py` sin errores.
- Test unitario de cada helper de transformación con casos edge (fecha como número Excel, número con separador anglosajón, parcela con typo).
- Test de regresión: las funciones de `import_service.py` no han sido modificadas (siguen pasando sus tests originales).
- Suite completa `pytest` verde, incluyendo los 58+ existentes.

---

## Relevant files

- [app/services/import_service.py](app/services/import_service.py) — referencia obligatoria de formatos CSV destino; especialmente `import_expenses_csv`, `import_incomes_csv`, `import_plots_csv`.
- [app/routers/imports.py](app/routers/imports.py) — patrón de router para imports (auth, manejo de archivo).
- [app/utils.py](app/utils.py) — `campaign_year`, `campaign_label`, helpers de fechas.
- [app/models/__init__.py](app/models/__init__.py) — patrón de declaración de modelos SQLAlchemy 2.x async.
- [app/config.py](app/config.py) — añadir `OPENAI_API_KEY` si no existe.
- [app/main.py](app/main.py) — registrar el nuevo router `onboarding`.
- [tests/conftest.py](tests/conftest.py) — patrón `FakeExecuteResult` para mocks de DB.
- [alembic/versions/](alembic/versions/) — patrón de migraciones existente.
- [import_data/gastos_2025_2026.csv](import_data/gastos_2025_2026.csv) y [import_data/ingresos_2025_2026.csv](import_data/ingresos_2025_2026.csv) — referencia de datos reales para fixtures.

---

## Verificación global

1. `alembic upgrade head` aplica migraciones sin errores; `downgrade -1` revierte limpiamente.
2. `pytest` completo (unitarios + integración) verde, incluyendo los nuevos tests del módulo onboarding.
3. Test E2E manual: subir cada fixture Excel y completar el flujo hasta importación correcta en BD de desarrollo.
4. Validar que `user_id` filtra correctamente en todas las queries nuevas (multi-tenancy).
5. Confirmar en logs que no se envían datos reales al LLM (solo cabeceras + muestras anonimizadas).
6. Lint/type-check: `ruff` y `mypy` sin nuevos warnings.
7. Actualizar `.github/copilot-instructions.md` con la nueva carpeta `app/services/onboarding/` (requisito por `assistant.instructions.md`).

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| LLM mapea mal columnas crípticas | Revisión humana obligatoria + threshold de confianza |
| Coste OpenAI fuera de control | Solo cabeceras + muestras pequeñas; límite de 1 sesión activa por usuario |
| Datos sensibles enviados al LLM | Función `_anonymize_sample` testeada; auditoría en logs |
| Excel con formatos exóticos | Fallback a "selección manual de columnas" si parser falla |
| Estado del grafo se pierde entre requests | Persistir state_json tras cada nodo |
| `import_service.py` cambia firmas | Tests parametrizados que verifican CSV→import end-to-end |

---

## Estimación de orden de implementación

- Fase 0 — Fundamentos
- Fase 1 — LangGraph + LLM
- Fase 2 — UI multi-paso
- Fase 3 — Transform + validate + cierre

Cada fase es independientemente verificable y desplegable (la app sigue funcionando aunque solo esté la Fase 0).
