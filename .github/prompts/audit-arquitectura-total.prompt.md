# Auditoría Total de Arquitectura — Trufiq

Actúa como un **arquitecto de software senior** con experiencia en seguridad (OWASP), diseño de sistemas y auditoría de código. Tu misión es realizar una **auditoría exhaustiva y sistemática** de la aplicación Trufiq, inspeccionando **cada módulo, capa y fichero relevante** sin excepción.

---

## Metodología de Auditoría

Sigue este orden estrictamente. Para cada sección: lee los ficheros implicados, analiza, detecta problemas y documenta los hallazgos con severidad.

### Escala de Severidad
- 🔴 **CRÍTICO** — Riesgo de seguridad grave, pérdida de datos o fallo total del sistema.
- 🟠 **ALTO** — Vulnerabilidad importante, violación arquitectónica severa o bug silencioso con impacto.
- 🟡 **MEDIO** — Deuda técnica significativa, antipatrón o riesgo potencial a medio plazo.
- 🟢 **BAJO** — Mejora de calidad, inconsistencia menor o sugerencia de buenas prácticas.

---

## FASE 1 — Capa de Configuración y Secretos

Lee y audita: `app/config.py`, `.env.example`, `docker-compose.yml`, `Dockerfile`, `fly.toml`

**Comprueba:**
- ¿Existe algún secreto hardcodeado (SECRET_KEY, contraseñas, API keys)?
- ¿El valor por defecto de `SECRET_KEY` es inseguro para producción?
- ¿`PRODUCTION` flag protege correctamente las cookies de sesión?
- ¿Hay variables de entorno sensibles expuestas en logs, headers o respuestas?
- ¿`DATABASE_URL` podría filtrarse en trazas de error?
- ¿Las variables opcionales (SMTP, Stripe, OpenAI) degradan correctamente si no están configuradas?
- ¿El `docker-compose.yml` expone puertos innecesarios o usa credenciales por defecto?
- ¿El `Dockerfile` sigue el principio de mínimo privilegio (usuario no-root, capas optimizadas)?

---

## FASE 2 — Autenticación y Gestión de Sesiones

Lee y audita: `app/auth.py`, `app/routers/auth.py`, `app/main.py`, `app/models/user.py`

**Comprueba:**
- ¿Las contraseñas se hashean siempre con argon2 antes de persistir? ¿Hay rutas donde se guarde texto plano?
- ¿La verificación de contraseñas es resistente a timing attacks?
- ¿Las cookies de sesión tienen `HttpOnly`, `Secure` (en producción), `SameSite`?
- ¿El `SessionMiddleware` usa una clave secreta suficientemente fuerte?
- ¿Existe protección contra fuerza bruta (rate limiting) en el login?
- ¿El logout invalida correctamente la sesión server-side?
- ¿La recuperación de contraseña usa tokens de un solo uso con expiración?
- ¿La confirmación de email usa tokens firmados y seguros?
- ¿El flujo de registro del primer usuario como `admin` es seguro?
- ¿`ADMIN_EMAIL` podría ser explotado si se filtra?
- ¿`get_current_user` podría devolver un usuario de otro tenant por error?

---

## FASE 3 — Autorización y Multi-tenancy

Lee y audita: `app/plan_access.py`, `app/auth.py` (funciones `require_*`), todos los ficheros en `app/services/`, todos los ficheros en `app/routers/`

**Comprueba:**
- ¿**Cada query** en cada service filtra por `user_id` o `tenant_id`? Busca activamente queries sin ese filtro.
- ¿Existe algún endpoint que devuelva datos de otro usuario si se manipula el ID en la URL o el cuerpo?
- ¿Los endpoints de escritura (POST, PUT, DELETE) verifican que el recurso pertenece al usuario/tenant antes de operar?
- ¿El control de planes (`plan_access.py`) se aplica en todos los routers que acceden a features premium?
- ¿Un usuario `basic` puede acceder a funcionalidades `premium` manipulando la petición?
- ¿Los endpoints de admin (`/admin/`) verifican correctamente el rol?
- ¿Existe IDOR (Insecure Direct Object Reference) en algún endpoint de plot, expense, income, plant, well, etc.?
- ¿El sistema multi-tenant (`Tenant`, `TenantMembership`) aísla los datos correctamente entre tenants?
- ¿Un miembro de un tenant puede escalar privilegios dentro del mismo tenant?

---

## FASE 4 — Modelos y Base de Datos

Lee y audita: todos los ficheros en `app/models/`, todos los ficheros en `alembic/versions/`

**Comprueba:**
- ¿Todos los modelos tienen los índices necesarios para las queries más frecuentes (especialmente `user_id`, `tenant_id`, `campaign_year`)?
- ¿Las foreign keys tienen las restricciones `CASCADE` / `SET NULL` correctas? ¿Podría haber huérfanos?
- ¿Hay campos `nullable` que deberían ser `NOT NULL` o viceversa?
- ¿Las migraciones de Alembic son reversibles (`downgrade`)? ¿Existen migraciones de datos que podrían fallar silenciosamente?
- ¿La migración `0021_data_migrate_tenants.py` (migración de datos) es idempotente?
- ¿Hay columnas que almacenan datos sensibles sin cifrar (datos personales, financieros)?
- ¿Los tipos de dato son apropiados (ej. `Numeric` para dinero, no `Float`)?
- ¿Hay riesgo de SQL injection por uso de texto literal en queries?
- ¿Los modelos de `RecurringExpense` y `ExpenseProrationGroup` tienen la lógica de negocio correctamente reflejada?
- ¿La relación entre `Plot`, `Plant` y `percentage` garantiza que los porcentajes siempre sumen 100?

---

## FASE 5 — Capa de Servicios (Business Logic)

Lee y audita: todos los ficheros en `app/services/`

**Comprueba — por cada service:**
- ¿Las funciones son atómicas y usan transacciones donde es necesario?
- ¿Se llama a `session.commit()` en los lugares correctos? ¿Podría haber commits parciales?
- ¿Se recalculan los porcentajes de `Plot` en **toda** mutación (create, update, delete)?
- ¿`distribute_unassigned_expenses()` de `utils.py` se usa consistentemente o hay lógica inline duplicada?
- ¿`campaign_year()` y `campaign_label()` de `utils.py` se usan siempre o hay cálculos de campaña inline?
- ¿Los servicios de importación (`import_service.py`) validan y sanitizan todos los campos del CSV?
- ¿`export_service.py` podría exponer datos de otros usuarios?
- ¿`assistant_service.py` / `llm_adapter.py` sanitizan el input antes de enviarlo al LLM? ¿Hay riesgo de prompt injection?
- ¿`billing_service.py` valida la firma del webhook de Stripe antes de procesar eventos?
- ¿`email_service.py` previene header injection en los campos `To`, `Subject`?
- ¿`sigpac_service.py` / `aemet_service.py` tienen timeouts y manejan errores de servicios externos?
- ¿`weather_service.py` / `rainfall_service.py` podrían causar race conditions con tareas cron?
- ¿Los servicios de riego (`irrigation_service.py`, `water_balance_service.py`) manejan correctamente unidades y precisión numérica?

---

## FASE 6 — Capa de Routers (HTTP)

Lee y audita: todos los ficheros en `app/routers/`

**Comprueba — por cada router:**
- ¿Todos los endpoints que modifican estado (POST/PUT/DELETE) tienen protección CSRF?
- ¿Los parámetros de URL y query son validados con tipos estrictos (no `str` libre para IDs)?
- ¿Hay endpoints que devuelvan stack traces o información interna en errores de producción?
- ¿Los redirects post-acción usan URLs fijas o podrían ser Open Redirects?
- ¿Los formularios de upload de ficheros (`imports.py`) limitan tamaño y validan el tipo MIME?
- ¿El endpoint de métricas (`/metrics`) está protegido con token?
- ¿Los endpoints de webhook (`billing.py`) rechazan peticiones sin firma válida?
- ¿`scan.py` / `reports.py` generan URLs o contenido dinámico con datos de usuario sin escapar?
- ¿Los routers de admin aplican doble verificación (autenticado + rol admin)?
- ¿Hay endpoints no documentados o dead code que podrían ser vectores de ataque?

---

## FASE 7 — Schemas (Validación de Input)

Lee y audita: todos los ficheros en `app/schemas/`

**Comprueba:**
- ¿Hay schemas para todos los recursos que reciben input de usuario?
- ¿Los schemas usan validadores que prevengan valores extremos (longitudes, rangos numéricos)?
- ¿Los campos de texto libre tienen límite de longitud para prevenir DoS?
- ¿Hay campos que deberían ser `Optional` pero son requeridos o viceversa?
- ¿Los schemas de importación CSV son suficientemente estrictos?

---

## FASE 8 — Frontend y Templates

Lee y audita: `app/templates/base.html`, y muestras representativas de templates en `gastos/`, `ingresos/`, `parcelas/`, `plantas/`, `pozos/`, `lluvia/`, etc.

**Comprueba:**
- ¿Todos los valores de usuario se renderizan con `{{ variable }}` (auto-escaped) y no con `{{ variable | safe }}`?
- ¿Los usos de `| safe` están justificados y el contenido es realmente seguro?
- ¿Los datos pasados a Chart.js están correctamente serializados con `json.dumps` y escapados?
- ¿Hay formularios sin token CSRF?
- ¿Los mensajes de error muestran información técnica interna al usuario?
- ¿Las URLs con IDs en formularios ocultos podrían ser manipuladas por el usuario?
- ¿Se carga JavaScript de CDNs externos sin Subresource Integrity (SRI)?
- ¿Hay inline scripts con datos de usuario sin sanitizar?
- ¿Los formularios de búsqueda/filtro reflejan el input del usuario sin escapar?

---

## FASE 9 — Seguridad OWASP Top 10

Realiza un barrido específico contra las 10 vulnerabilidades más críticas:

1. **A01 - Broken Access Control**: revisado en Fases 3, 5, 6.
2. **A02 - Cryptographic Failures**: contraseñas, tokens, cookies, datos en reposo.
3. **A03 - Injection**: SQL injection, prompt injection (LLM), SSTI en Jinja2, command injection en imports.
4. **A04 - Insecure Design**: flujos de negocio con bypasses lógicos, lógica de trial/suscripción.
5. **A05 - Security Misconfiguration**: cabeceras HTTP de seguridad, CORS, debug en producción.
6. **A06 - Vulnerable Components**: revisa `pyproject.toml` en busca de dependencias con CVEs conocidos.
7. **A07 - Auth Failures**: gestión de sesión, tokens, expiración.
8. **A08 - Software Integrity**: validación de webhooks (Stripe), imports de CSV.
9. **A09 - Logging Failures**: ¿se loguean intentos de acceso fallidos? ¿Se filtran datos sensibles en logs?
10. **A10 - SSRF**: `sigpac_service.py`, `aemet_service.py`, `ibericam_service.py` — ¿se validan las URLs destino?

---

## FASE 10 — Rendimiento y Escalabilidad

**Comprueba:**
- ¿Hay queries N+1 en algún service (bucles que lanzan queries individuales)?
- ¿Las queries pesadas usan `selectinload` / `joinedload` donde corresponde?
- ¿El connection pool de asyncpg está correctamente dimensionado?
- ¿Hay operaciones bloqueantes (sync I/O) dentro de corrutinas async?
- ¿Los cálculos de `percentage` en plots se recalculan en bucle en lugar de en una sola query?
- ¿`dashboard_service.py` y `kpi_service.py` hacen demasiadas queries separadas que podrían unificarse?
- ¿Los endpoints de exportación cargan colecciones enteras en memoria sin paginación?
- ¿Hay resultados que deberían estar cacheados (datos de campaña histórica, datos climáticos)?

---

## FASE 11 — Calidad del Código y Arquitectura

**Comprueba:**
- ¿Hay lógica de negocio en los routers (violación de la separación de capas)?
- ¿Hay queries SQL directas en los routers o templates?
- ¿Hay servicios que llaman a otros servicios creando dependencias circulares?
- ¿Hay código duplicado entre servicios que debería estar en `utils.py` o en un service compartido?
- ¿Las funciones superan las 50 líneas de forma injustificada?
- ¿Hay `print()` o `logging.debug()` con datos sensibles?
- ¿Hay `TODO` / `FIXME` / `HACK` que representen riesgos reales?
- ¿Los nombres de variables y funciones son consistentes y descriptivos?
- ¿Hay imports no usados o imports de `*`?

---

## FASE 12 — Testing

Lee y audita: `tests/conftest.py`, muestras de `tests/services/`, muestras de `tests/integration/`, y los test de routers.

**Comprueba:**
- ¿Hay tests para los caminos críticos de seguridad (acceso no autorizado, IDOR, plan gating)?
- ¿Los tests de servicios usan correctamente `FakeExecuteResult` del conftest?
- ¿Los tests de integración cubren las migraciones y el esquema real?
- ¿Hay tests que pasen por razones incorrectas (falsos positivos)?
- ¿Qué módulos tienen cobertura nula o insuficiente?
- ¿Los tests validan comportamientos de negocio o solo que el código "no explota"?
- ¿El conftest expone fixtures que podrían compartir estado entre tests?

---

## FASE 13 — Observabilidad y Operaciones

Lee y audita: `app/observability.py`, `scripts/`, `docker/entrypoint.sh`

**Comprueba:**
- ¿Los logs incluyen suficiente contexto (user_id, tenant_id, request_id) para diagnóstico?
- ¿Se loguean eventos de seguridad (login fallido, acceso denegado, cambio de plan)?
- ¿Las métricas de Prometheus exponen información sensible?
- ¿El endpoint `/metrics` está protegido en producción?
- ¿Los scripts cron (`process_recurring_expenses_cron.py`, `import_rainfall_cron.py`) manejan errores y tienen alertas?
- ¿El `entrypoint.sh` ejecuta migraciones de forma segura antes de arrancar la app?
- ¿Sentry captura suficiente contexto sin filtrar datos personales (GDPR)?

---

## ENTREGA FINAL

Una vez completadas todas las fases, genera un **Informe de Auditoría** con esta estructura:

```
# Informe de Auditoría Trufiq — [fecha]

## Resumen Ejecutivo
[Párrafo conciso con el estado general de la aplicación, riesgos principales y prioridad de acción]

## Hallazgos Críticos 🔴
[Lista numerada de cada hallazgo: fichero, línea si aplica, descripción del problema, impacto y recomendación concreta]

## Hallazgos Altos 🟠
[Ídem]

## Hallazgos Medios 🟡
[Ídem]

## Hallazgos Bajos 🟢
[Ídem]

## Aspectos Positivos
[Lo que está bien implementado — importante para equilibrio y confianza]

## Plan de Acción Recomendado
[Orden de prioridad para abordar los hallazgos, agrupados por sprint o sesión de trabajo]
```

**Regla fundamental:** No hagas suposiciones. Si no puedes leer un fichero, dilo explícitamente. Si un módulo no existe, indícalo. El valor de esta auditoría está en la exhaustividad y en la honestidad de los hallazgos.
