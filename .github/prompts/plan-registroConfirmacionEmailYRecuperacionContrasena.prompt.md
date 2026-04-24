## Plan: Registro con confirmación de email + recuperación de contraseña

**TL;DR**: Se reemplaza el flujo de registro actual por auto-registro con confirmación de email. Se añade recuperación de contraseña. El admin pierde la capacidad de crear usuarios; solo gestiona los existentes. Los tokens (confirmación y reset) son stateless con `itsdangerous` (ya en el stack). SMTP genérico via `aiosmtplib`.

---

### Phase 1 — Infraestructura de email

1. Añadir `aiosmtplib` a `pyproject.toml`
2. Ampliar `app/config.py`: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`, `APP_BASE_URL`, `ADMIN_EMAIL: Optional[str]`, propiedad calculada `smtp_configured: bool`
3. Crear `app/services/email_service.py`:
   - `send_email(to, subject, html_body)` — async via `aiosmtplib`
   - `send_confirmation_email(to_email, token)`
   - `send_password_reset_email(to_email, token)`

### Phase 2 — Modelo y migración

4. Añadir `email_confirmed: bool` a `User` en `app/models/user.py` (default `False`)
5. Crear `alembic/versions/0016_add_email_confirmed_to_users.py` con `upgrade()` y `downgrade()`

### Phase 3 — Sistema de tokens

6. Crear `app/services/token_service.py`:
   - `generate_token(payload: str, salt: str) -> str` — `itsdangerous.URLSafeTimedSerializer`
   - `confirm_token(token, salt, max_age) -> str | None`
   - Sales distintas: `"email-confirmation"` (24h) y `"password-reset"` (1h), para que los tokens no sean intercambiables

### Phase 4 — Flujo de registro modificado

7. Modificar `POST /register` en `app/routers/auth.py`:
   - Si `ADMIN_EMAIL` coincide → `role="admin"`, activo y confirmado directamente
   - Si no hay `ADMIN_EMAIL` y es primer usuario → `role="admin"`, activo (fallback)
   - Resto → `role="user"`, `is_active=False`, `email_confirmed=False`
   - Con SMTP → enviar email → `/login?pending_confirmation=1`
   - Sin SMTP (dev) → activar directo → `/login?registered=1`
8. Añadir `GET /register/confirm/{token}`: valida token, activa cuenta, redirige con query param de estado

### Phase 5 — Login

9. En `POST /login`: si `email_confirmed=False` → error *"Debes confirmar tu email antes de acceder"* (distinto de cuenta desactivada por admin)

### Phase 6 — Recuperación de contraseña

10. `GET /forgot-password` → formulario con campo email
11. `POST /forgot-password`:
    - Buscar usuario por email; respuesta idéntica exista o no (evita enumeración de emails)
    - Con SMTP → token (salt `"password-reset"`, 1h) → `send_password_reset_email()` → `/login?reset_sent=1`
    - Sin SMTP (dev) → loguear token en consola
12. `GET /reset-password/{token}` → formulario nueva contraseña + confirmación
13. `POST /reset-password/{token}`:
    - Validar token (max_age 3600s); inválido/expirado → `/login?reset_error=1`
    - Validar contraseña (min 8 chars, coinciden)
    - `hash_password()` → guardar → `/login?password_reset=1`

### Phase 7 — Eliminar creación de usuarios por admin

14. En `app/routers/admin.py`: eliminar `GET /admin/users/create` y `POST /admin/users` (líneas ~59–141)
15. Eliminar `app/templates/admin/user_create.html`
16. En `app/templates/admin/users_list.html`: quitar botón "Crear usuario"
17. **El admin mantiene**: listar usuarios, editar (nombre/email/rol/comunidad_regantes), activar/desactivar — sin cambios en esas rutas

### Phase 8 — Templates

18. Actualizar `app/templates/auth/login.html`: banners para `pending_confirmation`, `confirmed`, `confirm_error`, `already_confirmed`, `reset_sent`, `password_reset`, `reset_error`; añadir links "¿Olvidaste tu contraseña?" y "¿No tienes cuenta?"
19. Crear `app/templates/auth/forgot_password.html`
20. Crear `app/templates/auth/reset_password.html`
21. Crear `app/templates/email/confirmation_email.html`
22. Crear `app/templates/email/reset_password_email.html`

### Phase 9 — Tests

23. `tests/services/test_email_service.py` — mock `aiosmtplib`, verificar parámetros
24. `tests/services/test_token_service.py` — token válido, expirado, manipulado, sales distintas
25. Actualizar `tests/test_auth_router.py` — nuevo comportamiento de `/register`, `/register/confirm`, login con pendiente
26. Añadir tests para `/forgot-password` y `/reset-password/{token}`
27. Actualizar `tests/test_admin_router.py` — eliminar tests de `POST /admin/users` y `GET /admin/users/create`

---

**Ficheros a modificar**
- `app/config.py` — settings SMTP + ADMIN_EMAIL
- `app/models/user.py` — campo `email_confirmed`
- `app/routers/auth.py` — register, confirm, forgot-password, reset-password
- `app/routers/admin.py` — eliminar rutas de creación
- `app/templates/auth/login.html` — nuevos mensajes y links
- `app/templates/admin/users_list.html` — quitar botón crear

**Ficheros nuevos**
- `app/services/email_service.py`
- `app/services/token_service.py`
- `app/templates/auth/forgot_password.html`
- `app/templates/auth/reset_password.html`
- `app/templates/email/confirmation_email.html`
- `app/templates/email/reset_password_email.html`
- `alembic/versions/0016_add_email_confirmed_to_users.py`

**Ficheros a eliminar**
- `app/templates/admin/user_create.html`

---

**Decisiones tomadas**
- SMTP genérico (`aiosmtplib`), sin vendor lock-in
- Tokens stateless con `itsdangerous` (ya en el stack) — no requieren tabla en BD
- Sales distintas por propósito — tokens de confirmación y reset no son intercambiables
- Sin SMTP configurado: activación directa en dev, log del token en consola para reset
- Admin pierde capacidad de crear usuarios; mantiene edición y activación/desactivación
- `ADMIN_EMAIL` en `.env` define el admin inicial; sin él, el primer usuario sigue siendo admin (backward-compatible)
