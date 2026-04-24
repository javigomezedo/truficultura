---
description: Mantén sincronizado el contexto del asistente IA cada vez que se añada o cambie una funcionalidad de la aplicación.
applyTo: app/models/**,app/routers/**,app/services/**
---

## Contexto del asistente IA

El asistente de Truficultura obtiene su conocimiento de la aplicación desde `app/services/assistant_service.py`.
**Cada vez que añadas o modifiques una funcionalidad, actualiza ese fichero** para que el asistente sepa explicarla y pueda responder preguntas sobre ella.

---

## Qué actualizar y dónde

### 1. `_APP_KNOWLEDGE` — descripción de módulos

Añade o edita el módulo correspondiente en la sección `MÓDULOS DE LA APLICACIÓN`.
- Una o dos líneas por módulo, indicando qué gestiona, campos principales y cualquier regla especial.
- Usa el mismo estilo que los módulos existentes: guión inicial + nombre en negrita implícita + descripción concisa.

### 2. `_DATA_KEYWORDS` — palabras clave para detección de intención

Añade términos en español (sin acentos, en minúsculas) que el usuario pueda emplear para preguntar por el nuevo módulo.

Ejemplo: si añades un módulo de facturas, agrega `"factura"`, `"facturas"`, `"mi factura"`.

### 3. `_DATA_PATTERNS` — patrones regex de detección

Si el nuevo módulo genera preguntas con estructura predecible, añade un `re.compile(...)` al listado `_DATA_PATTERNS`.

Ejemplo: `re.compile(r"\b(factura|facturas)\b.*\b(parcela|campana|año)\b")`.

### 4. `_SOURCES_DATA` — metadatos de trazabilidad

Si el nuevo módulo tiene su propio modelo de BD, añade `"db:<nombre_tabla>"` a la lista `_SOURCES_DATA`.

### 5. `_build_user_context` — datos del usuario en tiempo real

Si el nuevo módulo tiene registros propios del usuario (filtrados por `user_id`), añade:

```python
# Query al final del bloque de consultas
nuevo_result = await db.execute(
    select(NuevoModel).where(NuevoModel.user_id == user_id)
)
nuevo_list = nuevo_result.scalars().all()
```

Y en la sección de `lines`, añade un resumen agregado (totales, no registros individuales):

```python
if nuevo_list:
    lines.append(f"NuevoMódulo: {len(nuevo_list)} registros ...")
```

---

## Tabla de cambios → acciones

| Cambio en la app | Acción en el asistente |
|---|---|
| Nuevo modelo en `app/models/` | Añadir módulo en `_APP_KNOWLEDGE` |
| Nuevo router en `app/routers/` | Describir la pantalla/flujo en `_APP_KNOWLEDGE` |
| Nueva regla de negocio en `app/services/` | Actualizar la descripción del módulo afectado |
| Nuevo modelo con datos por usuario | Añadir query + línea resumen en `_build_user_context` |
| Campo nuevo relevante en modelo existente | Actualizar la descripción del módulo en `_APP_KNOWLEDGE` |
| Nuevas palabras clave en el dominio | Actualizar `_DATA_KEYWORDS` y/o `_DATA_PATTERNS` |
| Nueva fuente de datos | Añadir `"db:<tabla>"` a `_SOURCES_DATA` |

---

## Reglas de calidad

- Los resúmenes en `_build_user_context` deben ser **agregados** (totales, conteos, promedios), nunca listas de registros en crudo.
- Todos los textos del asistente deben estar en **español**.
- Mantén `_APP_KNOWLEDGE` por debajo de ~80 líneas para no inflar el prompt del sistema.
- Tras cualquier cambio en `assistant_service.py`, ejecuta los tests para verificar que no hay regresiones:

```bash
.venv/bin/python -m pytest -q tests/
```
