# Truficultura

Aplicación web para la gestión integral de una explotación trufícola: parcelas, producción por planta, pozos, riego, gastos, ingresos, rentabilidad por campañas, KPIs, gráficas de evolución, lluvia, meteorología y suscripción de pago.

## 1. Resumen del proyecto

Truficultura permite registrar y analizar la actividad económica de una explotación de trufa con una lógica de campañas agrícolas (de mayo a abril).

### Qué resuelve

- Gestión de parcelas (bancales) con identificación cadastral y número de plantas.
- Configuración de mapas de plantas por parcela (filas/columnas, huecos y etiquetas tipo A1, C2, AA10).
- Registro de trufas por planta (manual o por QR), con histórico y filtros por campaña/parcela/planta.
- Registro de pozos por parcela y campaña, con posibilidad de asociarlos a gasto.
- Registro de gastos (con o sin parcela asignada) con opción de prorrateo plurianual.
- Registro de gastos recurrentes (semanal, mensual, anual) con generación automática de gastos reales mediante cron.
- Registro de ingresos por fecha, categoría, kg y precio por kg.
- Registro de riegos por parcela con volumen de agua y notas.
- Registro de cosechas (`PlotHarvest`) por parcela y fecha, con peso en gramos.
- Registro de eventos de parcela (riego, pozos, poda, laboreo, etc.) con calendario visual.
- Registro de presencia de trufa por planta y día (`PlantPresence`).
- Registro de lluvia por parcela, municipio o fuente externa (AEMET / Ibericam) con importación automática vía cron.
- Visualización meteorológica en tiempo real (temperatura, humedad, viento) por parcela vía API AEMET / Ibericam.
- Análisis avanzado por parcela: correlación riego-producción, poda-producción, laboreo-producción, comparativa multi-parcela y umbrales de riego.
- Cálculo automático de rentabilidad global, por campaña y por parcela.
- Visualización de métricas semanales y comparativas mediante gráficas.
- Panel de KPIs con ROI, precio medio, kg por campaña, crecimiento interanual y eficiencia hídrica.
- Importación y exportación masiva de datos históricos desde CSV para parcelas, gastos, ingresos, riego, pozos y producción.
- Asistente conversacional vía API para consultas sobre uso y datos, con métricas y rate limiting.
- Distribución proporcional de gastos generales según número de plantas por parcela.
- **Sistema de suscripción de pago** vía Stripe: periodo de prueba, checkout anual, portal de gestión y webhooks.
- Página de landing pública con formulario de contacto/captura de leads.
- Internacionalización (i18n) de la interfaz en español, inglés y francés.

### Lógica de negocio clave

- **Campaña agrícola**: mayo-abril.
  - Ejemplo: febrero de 2026 pertenece a campaña 2025.
- **Distribución de gastos sin parcela**:
  - Los gastos con `plot_id = None` se reparten proporcionalmente según el campo `porcentaje` de cada parcela.
  - El porcentaje se calcula automáticamente: `(num_plantas / total_plantas_usuario) * 100`
- **Prorrateo plurianual de gastos**:
  - Un gasto de inversión puede distribuirse en N campañas (ej: 3.000 € → 3 gastos de 1.000 €/año).
  - Se almacena un `ExpenseProrationGroup` padre que agrupa todos los gastos hijos generados.
- **Gastos recurrentes**:
  - Definidos con frecuencia `weekly` / `monthly` / `annual`, importe, categoría y parcela opcional.
  - El cron `scripts/process_recurring_expenses_cron.py` genera los gastos reales vencidos.
- **Lluvia**:
  - Los registros pueden ser `manual` (parcela concreta), `aemet` o `ibericam` (nivel municipio, `user_id` puede ser NULL).
  - El cron `scripts/import_rainfall_cron.py` descarga automáticamente datos de lluvia por municipio priorizando AEMET sobre Ibericam.
- **Suscripción**:
  - Nuevo usuario → periodo de prueba de N días (`TRIAL_DAYS`, por defecto 14).
  - Tras el trial, se requiere suscripción activa para acceder a la aplicación.
  - Usuarios `admin` nunca son bloqueados.
  - Estados posibles: `trialing`, `active`, `past_due`, `canceled`.
- **Identificación de parcelas**:
  - `plot_num`: número de parcela dentro del polígono (ej: 120)
  - `cadastral_ref`: referencia catastral oficial (ej: 44223A021001200000FP)
- **Totales de ingresos**:
  - `total = cantidad_kg * euros_kg`.

---

## 2. Detalle técnico de implementación

## Stack y tecnologías

- **Backend**: FastAPI
- **ORM**: SQLAlchemy 2.x (modo asíncrono)
- **Driver PostgreSQL**: asyncpg
- **Base de datos**: PostgreSQL
- **Migraciones**: Alembic
- **Configuración**: Pydantic Settings
- **Renderizado HTML**: Jinja2
- **Frontend**: Bootstrap 5 + Bootstrap Icons
- **Gráficas**: Chart.js
- **Internacionalización**: Babel + gettext (es / en / fr)
- **Autenticación**: sesiones `itsdangerous`, contraseñas Argon2
- **Pagos**: Stripe (Checkout, Customer Portal, webhooks)
- **Meteorología externa**: AEMET OpenData API + Ibericam (scraping)
- **Herramientas auxiliares**: python-multipart, aiofiles, greenlet, httpx

## Arquitectura de carpetas

```text
.
├── app/
│   ├── main.py                 # Arranque FastAPI y dashboard principal
│   ├── auth.py                 # Autenticación, roles y gating de suscripción
│   ├── config.py               # Configuración (DATABASE_URL, Stripe, AEMET, SMTP…)
│   ├── database.py             # Engine/sesiones async SQLAlchemy
│   ├── i18n.py                 # Internacionalización (gettext, Babel)
│   ├── jinja.py                # Globals y filtros Jinja2
│   ├── utils.py                # Funciones de campaña y reparto de gastos
│   ├── models/                 # Entidades ORM (Parcela, Planta, Gasto, Lluvia, Suscripción…)
│   ├── routers/                # Rutas por módulo funcional
│   ├── services/               # Lógica de negocio y agregaciones
│   ├── schemas/                # Esquemas Pydantic (DTOs)
│   └── templates/              # Vistas Jinja2
├── alembic/                    # Configuración de migraciones
├── locales/                    # Ficheros de traducción .po (es/en/fr)
├── scripts/                    # Scripts de mantenimiento y cron
│   ├── process_recurring_expenses_cron.py
│   ├── import_rainfall_cron.py
│   ├── seed_full_demo.py
│   ├── seed_truffle_demo_data.py
│   └── proxy-dev-db.sh
├── import_data/                # CSV de importación de muestra
├── pyproject.toml              # Dependencias y metadata
├── alembic.ini                 # Config Alembic
├── fly.toml                    # Configuración despliegue Fly.io
└── .env / .env.example         # Variables de entorno
```

## Flujo de ejecución

1. `uvicorn` arranca `app.main:app`.
2. En startup se ejecutan migraciones Alembic en `entrypoint.sh` para asegurar esquema alineado.
3. Cada request abre sesión asíncrona de BD.
4. Los routers delegan en la capa de servicios.
5. Los servicios consultan modelos SQLAlchemy y aplican reglas de negocio.
6. Jinja2 renderiza HTML con datos agregados.
7. En la vista de gráficas, los datos se serializan y se pintan con Chart.js.

## Capa de servicios (refactor aplicada)

La aplicación ya está refactorizada para separar responsabilidades.

- **Routers**: orquestación HTTP (leer params, llamar servicios, renderizar/redirect).
- **Services**: lógica de negocio, agregaciones y operaciones CRUD.
- **Models**: persistencia ORM.

Servicios principales:

- `app/services/plots_service.py`: CRUD de parcelas con cálculo automático de porcentajes.
- `app/services/expenses_service.py`: CRUD y contexto de listado de gastos por campaña, con soporte de prorrateo.
- `app/services/recurring_expenses_service.py`: CRUD de gastos recurrentes y generación de gastos vencidos.
- `app/services/incomes_service.py`: CRUD y contexto de listado de ingresos por campaña.
- `app/services/irrigation_service.py`: CRUD y contexto de listados de riego por parcela y año.
- `app/services/wells_service.py`: CRUD y agregados de pozos por parcela y campaña.
- `app/services/plot_events_service.py`: CRUD de eventos de parcela (riego, poda, laboreo, etc.) con calendario.
- `app/services/plot_harvest_service.py`: CRUD de cosechas (`PlotHarvest`) por parcela y fecha.
- `app/services/plant_presence_service.py`: registro de presencia de trufa por planta y día.
- `app/services/rainfall_service.py`: CRUD de registros de lluvia (manual, AEMET, Ibericam) y calendario de precipitaciones.
- `app/services/weather_service.py`: consulta meteorológica en tiempo real por parcela (temperatura, humedad, viento).
- `app/services/aemet_service.py`: cliente AEMET OpenData (estaciones, observaciones, climatología).
- `app/services/ibericam_service.py`: scraping de datos meteorológicos de Ibericam.
- `app/services/plot_analytics_service.py`: análisis avanzado por parcela (correlaciones riego/poda/laboreo vs producción, comparativa multi-parcela, umbrales).
- `app/services/dashboard_service.py`: cálculo del dashboard global.
- `app/services/reports_service.py`: cálculo del informe de rentabilidad.
- `app/services/charts_service.py`: datasets para gráficas y tablas de producción.
- `app/services/kpi_service.py`: cálculo de KPIs globales y por parcela.
- `app/services/billing_service.py`: integración Stripe (trial, checkout, portal, webhooks).
- `app/services/assistant_service.py`: preparación de contexto y orquestación del asistente.
- `app/services/import_service.py`: importación de parcelas, gastos, ingresos, riego, pozos y producción desde CSV.
- `app/services/export_service.py`: exportación de parcelas, gastos, ingresos, riego, pozos y producción a CSV/ZIP.
- `app/services/email_service.py`: envío de emails (confirmación, notificaciones de leads) vía SMTP.
- `app/services/token_service.py`: generación y validación de tokens firmados (confirmación email, QR).
- `app/services/admin_service.py`: gestión de usuarios desde el panel de admin.

Beneficios directos del refactor:

- Menos duplicación de lógica en routers.
- Más facilidad para pruebas unitarias sin levantar servidor.
- Mejor mantenibilidad y evolución del dominio.

## Modelos de datos

### Usuario (User)

Campos relevantes:

- `username`: identificador único del usuario
- `email`: email único del usuario
- `first_name` / `last_name`: nombre y apellido
- `hashed_password`: contraseña hasheada (Argon2)
- `role`: `admin` o `user`
- `is_active`: estado (activo/inactivo)
- `email_confirmed`: indica si el email fue verificado (boolean)
- `comunidad_regantes`: pertenece a comunidad de regantes (boolean)
- `stripe_customer_id`: ID de cliente en Stripe
- `subscription_status`: `trialing` | `active` | `past_due` | `canceled`
- `trial_ends_at` / `subscription_ends_at`: fechas de expiración del trial o suscripción
- `created_at`: fecha de creación

Relaciones:

- 1:N con `Plot`
- 1:N con `Expense`
- 1:N con `Income`

### Parcela (Plot)

Campos relevantes:

- `name`: nombre de la parcela
- `polygon`: referencia del polígono
- `plot_num`: número de parcela dentro del polígono
- `cadastral_ref`: identificador único del catastro
- `num_plants`: número total de plantas (trufa trufera, encina, etc.)
- `area_ha`: superficie en hectáreas
- `hydrant`: referencia del hidrante
- `sector`: sector de la explotación
- `planting_date`: fecha de plantación
- `production_start`: inicio de producción
- `percentage`: porcentaje dentro del total de plantas (calculado automáticamente)
- `has_irrigation`: indica si la parcela tiene riego habilitado

Relaciones:

- 1:N con `Expense`
- 1:N con `Income`
- 1:N con `IrrigationRecord`
- 1:N con `Well`
- 1:N con `Plant`

### Planta (Plant)

Campos relevantes:

- `plot_id`: parcela a la que pertenece
- `label`: etiqueta legible (`A1`, `B3`, `AA12`)
- `row_label`: etiqueta de fila (`A`, `B`, `AA`)
- `row_order`: orden interno de fila (0-index)
- `col_order`: orden interno de columna (0-index)
- `visual_col`: columna visual en el mapa (1-index, soporta filas no uniformes)
- `user_id`: usuario propietario del dato

Relaciones:

- N:1 con `Plot`
- 1:N con `TruffleEvent`

### Evento de trufa (TruffleEvent)

Campos relevantes:

- `plant_id`: planta donde se registra la trufa
- `plot_id`: parcela denormalizada para filtrado rápido
- `estimated_weight_grams`: peso estimado en gramos
- `source`: origen del registro (`manual` o `qr`)
- `created_at`: fecha/hora del registro
- `undo_window_expires_at`: límite temporal para deshacer
- `undone_at`: marca de deshecho (si aplica)
- `user_id`: usuario propietario del dato

### Pozos (Well)

Campos relevantes:

- `date`: fecha del trabajo de pozos
- `plot_id`: parcela asociada
- `wells_per_plant`: número de pozos realizados por planta en esa sesión
- `expense_id`: gasto asociado (opcional)
- `notes`: notas opcionales
- `user_id`: usuario propietario del dato

### Gasto recurrente (RecurringExpense)

Campos relevantes:

- `description`: descripción del gasto
- `amount`: importe en euros
- `category`: categoría opcional
- `plot_id`: parcela asignada (opcional)
- `person`: persona responsable
- `frequency`: `weekly` | `monthly` | `annual`
- `is_active`: si sigue activo para futuras generaciones
- `last_run_date`: última fecha en que se generó un gasto real
- `user_id`: usuario propietario

### Prorrateo de gasto (ExpenseProrationGroup)

Agrupa N gastos generados al distribuir una inversión en varias campañas:

- `description`: descripción del gasto original
- `total_amount`: importe total sin prorratear
- `years`: número de años del prorrateo
- `start_year`: campaña inicial
- `user_id`: usuario propietario

### Evento de parcela (PlotEvent)

Campos relevantes:

- `plot_id`: parcela asociada
- `event_type`: tipo de evento (`riego`, `pozos`, `poda`, `laboreo`, `sulfatado`, etc.)
- `date`: fecha del evento
- `notes`: notas opcionales
- `is_recurring`: si es recurrente
- `related_irrigation_id` / `related_well_id`: referencias opcionales a riego o pozo asociado
- `user_id`: usuario propietario

### Cosecha de parcela (PlotHarvest)

Campos relevantes:

- `plot_id`: parcela asociada
- `harvest_date`: fecha de recogida
- `weight_grams`: peso recogido en gramos
- `notes`: notas opcionales
- `user_id`: usuario propietario

### Presencia de trufa por planta (PlantPresence)

Campos relevantes:

- `plot_id` / `plant_id`: parcela y planta
- `presence_date`: fecha del registro
- `has_truffle`: indica si la planta tenía trufa ese día
- `user_id`: usuario propietario

### Registro de lluvia (RainfallRecord)

Campos relevantes:

- `user_id`: usuario propietario (NULL para registros compartidos AEMET/Ibericam)
- `plot_id`: parcela asociada (NULL para registros a nivel de municipio)
- `municipio_cod` / `municipio_name`: código INE y nombre del municipio
- `date`: fecha del registro
- `precipitation_mm`: precipitación en milímetros
- `source`: `manual` | `aemet` | `ibericam`
- `notes`: notas opcionales

### Captura de lead (LeadCapture)

Campos relevantes:

- `name` / `email`: nombre y email del contacto
- `ip_hash`: hash parcial SHA-256 de la IP (nunca se guarda la IP en claro, RGPD)
- `message`: mensaje libre del formulario de contacto
- `contacted` / `contacted_at`: gestión de seguimiento
- `created_at`: fecha del registro

### Gasto (Expense)

Campos relevantes:

- `date`: fecha del gasto
- `description`: descripción/concepto
- `person`: persona responsable
- `plot_id`: parcela asignada (opcional, `None` para gastos generales)
- `amount`: cantidad en euros
- `category`: categoría opcional (Riego, Mantenimiento, etc.)
- `user_id`: usuario propietario del dato

### Ingreso (Income)

Campos relevantes:

- `date`: fecha del ingreso
- `plot_id`: parcela asignada (opcional)
- `amount_kg`: cantidad en kilogramos
- `category`: categoría de trufa (Extra, A, B, etc.)
- `euros_per_kg`: precio por kilogramo
- `total`: propiedad calculada (`amount_kg * euros_per_kg`) no persistida en BD
- `user_id`: usuario propietario del dato

### Riego (IrrigationRecord)

Campos relevantes:

- `date`: fecha del riego
- `plot_id`: parcela asociada (obligatoria)
- `water_m3`: volumen de agua en m³
- `notes`: notas opcionales
- `expense_id`: gasto de riego asociado (opcional, uso interno)
- `user_id`: usuario propietario del dato

## Endpoints y vistas principales

- `/` Dashboard con totales globales y matriz campaña x parcela.
- `/plots/` CRUD de parcelas con gestión automática de porcentajes.
- `/expenses/` CRUD de gastos + filtros por campaña + prorrateo plurianual.
- `/recurring-expenses/` CRUD de gastos recurrentes (semanal/mensual/anual).
- `/incomes/` CRUD de ingresos + filtros por campaña.
- `/irrigation/` CRUD de registros de riego + filtros por parcela y año.
- `/wells/` CRUD de registros de pozos + filtros por parcela y campaña.
- `/plot-events/` CRUD de eventos de parcela con vista de calendario mensual.
- `/harvests/` Registro de cosechas por parcela con desglose por campaña.
- `/lluvia/` CRUD de registros de lluvia (manual, AEMET, Ibericam) con calendario de precipitaciones.
- `/tiempo/` Visualización meteorológica en tiempo real (temperatura, humedad, viento) por parcelas del usuario.
- `/plot-analytics/` Análisis avanzado por parcela: correlación riego/poda/laboreo-producción, comparativa multi-parcela, umbrales de riego.
- `/plots/{id}/map` mapa visual por planta con conteos por campaña y alta rápida (+1).
- `/plots/{id}/map/configure` configuración de geometría del mapa de plantas por parcela.
- `/truffles/` listado cronológico de eventos de trufa con filtros por campaña, parcela y planta.
- `/scan/{token}` alta de trufa por escaneo QR de planta.
- `/reports/profitability` informe de rentabilidad detallado por campaña y parcela.
- `/charts/` Análisis visual (semanal y comparativa ingresos vs gastos).
- `/kpis/` panel de indicadores con ROI, precio medio, kg/ha, kg/planta y métricas de agua.
- `/import/` importación masiva desde CSV (parcelas, gastos, ingresos, riego, pozos, producción).
- `/export/` exportación de datos a CSV/ZIP (parcelas, gastos, ingresos, riego, pozos, producción).
- `/api/assistant/chat` y `/api/assistant/stream` API del asistente para consultas guiadas.
- `/billing/subscribe` página de suscripción con estado actual (trial, activo, caducado).
- `/billing/checkout` inicia sesión de Stripe Checkout (redirige al pago).
- `/billing/success` / `/billing/cancel` páginas de retorno desde Stripe.
- `/billing/portal` redirige al Customer Portal de Stripe para gestionar/cancelar.
- `/stripe/webhook` receptor de eventos Stripe (checkout, invoice, subscription).
- `/admin/users` Dashboard de gestión de usuarios (solo administrador).
  - Listado de usuarios con estado (activo/inactivo) y estado de suscripción
  - Crear nuevos usuarios
  - Editar perfil y rol de usuarios existentes
  - Activar/desactivar usuarios
  - Validación de email y username únicos
- `/` (landing pública) Página de presentación con formulario de contacto para captura de leads.

---

## Sistema de roles, permisos y suscripción

### Roles disponibles

**Admin**
- Acceso a todo el dashboard de administración (`/admin/users`)
- Gestión completa de usuarios (crear, editar, activar/desactivar)
- Puede asignar roles (admin o user) a otros usuarios
- **Nunca bloqueado por expiración de suscripción**
- Acceso a todos los datos de todas las parcelas/gastos/ingresos como usuario normal

**User** (usuario regular)
- Acceso completo a su propia explotación (parcelas, gastos, ingresos, reportes, gráficas, lluvia, météo…)
- CRUD completo de sus datos
- No puede acceder al dashboard de admin u otros usuarios
- Datos completamente aislados por `user_id`
- **Requiere suscripción activa** (o trial vigente) para acceder a la aplicación

### Estados de suscripción

| Estado | Descripción | Acceso |
|---|---|---|
| `trialing` | Periodo de prueba activo | ✅ Acceso completo |
| `active` | Suscripción Stripe activa | ✅ Acceso completo |
| `active` (caducado) | `subscription_ends_at` en el pasado | ❌ Bloqueado → `/billing/subscribe` |
| `past_due` | Pago fallido, Stripe reintentando | ❌ Bloqueado |
| `canceled` | Suscripción cancelada | ❌ Bloqueado |

### Primeras acciones

- El primer usuario registrado se crea automáticamente como **admin**
- Los siguientes usuarios se crean como **user** con periodo de prueba de `TRIAL_DAYS` días
- Solo un admin puede cambiar roles a otros usuarios
- No se puede desactivar a uno mismo (protección de seguridad)

---

## 3. Uso de la aplicación

## Requisitos previos

- Python 3.11 o superior
- PostgreSQL disponible
- Base de datos creada para el proyecto

## Configuración del entorno

1. Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

2. Edita `.env` con tu conexión real y los secretos necesarios:

```env
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/truficultura
SECRET_KEY=una-clave-secreta-larga-y-aleatoria

# Stripe (opcional; sin configurar, el billing queda deshabilitado)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
TRIAL_DAYS=14

# Email/SMTP (opcional; para confirmación y notificaciones de leads)
SMTP_HOST=smtp.ejemplo.com
SMTP_PORT=587
SMTP_USER=usuario@ejemplo.com
SMTP_PASSWORD=contraseña
SMTP_FROM=noreply@truficultura.app
CONTACT_EMAIL=admin@truficultura.app

# AEMET (opcional; para importación de lluvia y meteorología)
AEMET_API_KEY=tu_api_key_aemet

# URL pública de la app (para links en emails)
APP_BASE_URL=https://tudominio.com
```

## Instalación de dependencias

Con `uv` (recomendado si usas `uv.lock`):

```bash
uv sync
```

Alternativa con `venv` + `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Aplicar migraciones

```bash
alembic upgrade head
```

## Ejecutar la aplicación

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abrir en navegador:

- http://localhost:8000

## 3.1 Guía operativa corta (Docker)

### Requisitos

- Docker Desktop (o Docker Engine + Compose)
- Archivo `.env` con `DATABASE_URL` y `SECRET_KEY`

Ejemplo de `DATABASE_URL` para la base de datos del `docker-compose.yml` actual:

```env
DATABASE_URL=postgresql+asyncpg://trufi:trufi@localhost:5433/truficultura
```

### 1) Levantar PostgreSQL local con Docker Compose

```bash
docker compose up -d db
```

### 2) Construir la imagen de la app

```bash
docker build -t truficultura:local .
```

### 3) Ejecutar la app en contenedor

```bash
docker run --rm -p 8000:8000 --env-file .env truficultura:local
```

Notas:
- El contenedor ejecuta `alembic upgrade head` al arrancar (si `RUN_MIGRATIONS` no se cambia).
- Para desactivar migraciones en arranque: `-e RUN_MIGRATIONS=0`.

### 4) Verificar estado

```bash
curl http://localhost:8000/health
```

### 5) Parar la base de datos local

```bash
docker compose down
```

## 3.2 Conectar a la DB dev de Fly.io desde local

Para conectarte a `truficultura-db-dev` desde tu cliente SQL local, usa el proxy de Fly.

### 1) Levantar el proxy

Se incluye un script auxiliar:

```bash
./scripts/proxy-dev-db.sh
```

Este comando abre un túnel local en `localhost:5434` hacia `truficultura-db-dev`.
Mantén esta terminal abierta mientras uses el cliente.

### 2) Parámetros de conexión

- Host: `localhost`
- Port: `5434`
- Database: `truficultura_dev`
- User: `postgres`
- Password: usa la variable local `TRUFICULTURA_DB_DEV_PASSWORD`

Connection string:

```text
postgresql://postgres:<password>@localhost:5434/truficultura_dev
```

Puedes obtener la password desde Fly cuando la necesites:

```bash
flyctl postgres credentials --app truficultura-db-dev
```

Y guardarla solo en local en un `.env` (no versionado):

```env
TRUFICULTURA_DB_DEV_PASSWORD=tu_password_real
```

Nota: Se usa `5434` para evitar conflicto con PostgreSQL local (`5432`) y con `docker-compose` (`5433`).

---

## 4. Modo debug, importaciones y operaciones frecuentes

## Datos de prueba para mapa y trufas por planta

Para poblar la base de datos con datos realistas (múltiples campañas, parcelas, plantas y eventos de trufa), se incluye:

- `scripts/seed_truffle_demo_data.py`

Ejemplo recomendado:

```bash
.venv/bin/python scripts/seed_truffle_demo_data.py \
  --plots 3 \
  --start-campaign 2021 \
  --end-campaign 2026 \
  --events-min 20 \
  --events-max 60 \
  --seed 123
```

Parámetros más útiles:

- `--user-id`: usuario destino (si no se indica, usa el primer usuario de la BD)
- `--plots`: número de parcelas demo a crear
- `--start-campaign` / `--end-campaign`: rango de campañas (año de inicio)
- `--events-min` / `--events-max`: eventos de trufa por parcela y campaña
- `--rows-min` / `--rows-max`: tamaño del mapa por filas
- `--cols-min` / `--cols-max`: amplitud potencial de columnas por fila
- `--seed`: semilla para resultados reproducibles

El script crea parcelas nuevas con mapas de plantas no uniformes y eventos de trufa por planta (incluyendo algunos deshechos) para validar filtros y reportes.

## Dataset demo completo para validar toda la aplicación

Para poblar una base de datos vacía con un escenario más amplio y realista, se incluye:

- `scripts/seed_full_demo.py`

Qué genera:

- 10 campañas agrícolas (por defecto, hasta la campaña actual)
- 10 parcelas con nombres realistas y superficies distintas
- plantas y mapas por parcela
- ingresos de producción con categorías y precios por campaña
- gastos directos y gastos generales sin parcela
- registros de riego
- registros de pozos
- eventos de producción por planta

Ejemplo recomendado:

```bash
.venv/bin/python scripts/seed_full_demo.py
```

Opciones útiles:

- `--user-id`: usuario destino (si no se indica, usa el primero de la BD)
- `--plots`: número de parcelas a crear (máximo 10)
- `--start-campaign`: campaña inicial; si no se indica, genera los últimos 10 años
- `--seed`: semilla para hacer reproducible el dataset

Este script es el más útil para validar informes, gráficas, KPIs, comparativas por parcela y rendimiento de listados con datos voluminosos.

## Modo desarrollo/debug

Arranque con autoreload:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Con mayor nivel de logs:

```bash
uvicorn app.main:app --reload --log-level debug
```

## Importación y exportación de datos CSV

La importación y exportación de datos se realiza directamente desde la interfaz web en `/import/` y `/export/`.

### Tipos de importación disponibles

**1) Importar Parcelas**

Accede a `/import/` → Pestaña "Parcelas" → Carga un archivo CSV

Formato esperado (semicolon-delimited, sin header):
```
nombre;fecha_plantacion;poligono;parcela;ref_catastral;hidrante;sector;n_plantas;superficie_ha;inicio_produccion;tiene_riego
Bancal Sur;15/03/2018;21;120;44223A021001200000FP;H-3;S2;120;1,25;01/11/2023;1
```

Obligatorio: `nombre` y `fecha_plantacion`
Opcional: resto de campos. `tiene_riego` acepta `1` o `0`; si falta, se asume `0`.

**2) Importar Gastos**

Accede a `/import/` → Pestaña "Gastos" → Carga un archivo CSV

Formato esperado (semicolon-delimited, sin header):
```
fecha;concepto;persona;bancal;cantidad;categoria
15/11/2025;Riego por goteo;Javi;Bancal Sur;1.250,00;Riego
```

Obligatorio: `fecha`, `concepto`, `persona`, `cantidad`
Opcional: `bancal` (si está vacío, se registra como gasto general), `categoria`

**3) Importar Ingresos**

Accede a `/import/` → Pestaña "Ingresos" → Carga un archivo CSV

Formato esperado (semicolon-delimited, sin header):
```
fecha;bancal;kg;categoria;euros_kg
05/12/2025;Bancal Norte;2,500;Extra;120,00
```

Obligatorio: `fecha`, `kg`, `euros_kg`
Opcional: `bancal`, `categoria`

**4) Importar Riego**

Accede a `/import/` → Pestaña "Riego" → Carga un archivo CSV

Formato esperado (semicolon-delimited, sin header):
```
fecha;bancal;agua_m3;notas
15/06/2025;Bancal Sur;12,500;Primera pasada
```

Obligatorio: `fecha`, `bancal`, `agua_m3`
Opcional: `notas`

Reglas específicas:

- El bancal debe existir.
- La parcela debe tener `has_irrigation=True`.
- Si no se cumple alguna de estas condiciones, la fila se omite con aviso.

**5) Importar Pozos**

Accede a `/import/` → Pestaña "Pozos" → Carga un archivo CSV

Formato esperado (semicolon-delimited, sin header):
```
fecha;bancal;pozos_por_planta;notas
15/06/2025;Bancal Sur;2;Refuerzo micorrización
```

Obligatorio: `fecha`, `bancal`, `pozos_por_planta`
Opcional: `notas`

**6) Importar Producción**

Accede a `/import/` → Pestaña "Producción" → Carga un archivo CSV

Formato esperado (semicolon-delimited, sin header):
```
fecha_hora;bancal;planta;peso_estimado_gramos;origen
12/12/2025 08:45:00;Bancal Sur;A12;35,5;qr
```

Obligatorio: `fecha_hora`, `bancal`, `planta`
Opcional: `peso_estimado_gramos`, `origen` (`manual` o `qr`)

## Exportación de datos CSV

La exportación se realiza desde `/export/` y descarga ficheros listos para reutilizar en la importación.

Tipos de exportación disponibles:

- **Parcelas**: incluye columna `tiene_riego` (`1`/`0`) y configuración del mapa de plantas
- **Gastos**
- **Ingresos**
- **Riego**: exporta `fecha;bancal;agua_m3;notas`
- **Pozos**: exporta `fecha;bancal;pozos_por_planta;notas`
- **Producción**: exporta `fecha_hora;bancal;planta;peso_estimado_gramos;origen`
- **ZIP completo**: descarga `parcelas.csv`, `gastos.csv`, `ingresos.csv`, `riego.csv`, `pozos.csv` y `produccion.csv`

Características del formato exportado:

- Delimitador `;`
- Sin fila de cabecera
- Fechas en formato `dd/mm/yyyy`
- Números en formato europeo
- Compatible con la importación de la propia aplicación
- En riego no se exporta `expense_id`, porque es una referencia interna
- En pozos no se exporta `expense_id`, porque es una referencia interna
- En producción solo se exportan eventos activos (no deshechos)

### Comportamiento de la importación

- **Fechas**: Formato `dd/mm/yyyy`
- **Números**: Formato europeo (1.250,50 = 1250.50)
- **Validación**: Se validan fechas y formatos; líneas inválidas se omiten con aviso
- **Porcentajes**: Se calculan automáticamente después de importar parcelas
- **Avisos**: Si un bancal no existe en ingresos/gastos, se importa sin asignar y se muestra aviso
- **Riego**: Solo se importan registros sobre parcelas existentes y con riego habilitado
- **Pozos**: Solo se importan registros sobre parcelas existentes
- **Producción**: La planta debe existir dentro de la parcela indicada

La importación y exportación NO requieren ejecutar scripts; todo se hace desde el UI con feedback visual inmediato.

## Migraciones en desarrollo

Historial de migraciones activas (en `alembic/versions/`):

| Nº | Descripción |
|---|---|
| 0001 | Baseline inicial (schema completo) |
| 0002 | Plantas y eventos de trufa |
| 0003 | Columna visual en plantas |
| 0004 | Campos catastrales en parcelas |
| 0005 | Peso estimado en eventos de trufa |
| 0006 | Tabla de pozos |
| 0007 | Tabla de eventos de parcela |
| 0008 | Comunidad de regantes, recinto y caudal |
| 0009 | Gastos recurrentes |
| 0010 | Cosechas de parcela y presencias de planta |
| 0011 | Registros de lluvia |
| 0012 | Campos de agua y nombre de municipio |
| 0013 | Eliminación de `water_flow_lps` |
| 0014 | `user_id` nullable en registros de lluvia |
| 0015 | Grupos de prorrateo de gastos |
| 0016 | `email_confirmed` en usuarios |
| 0017 | Corrección de cascada en `wells.user_id` |
| 0018 | Tabla de captura de leads |

Nota: Las migraciones históricas previas al reset se conservaron en `alembic/versions_archive_YYYYMMDD_HHMMSS/` solo como referencia.

Crear migración automática:

```bash
alembic revision --autogenerate -m "descripcion_del_cambio"
```

Aplicar migraciones:

```bash
alembic upgrade head
```

Volver una migración atrás:

```bash
alembic downgrade -1
```

## Comandos útiles

```bash
# Verificar que la app levanta
curl -I http://localhost:8000

# Ejecutar pruebas unitarias de servicios
uv run pytest -q tests/services/

# Ejecutar pruebas de integración (SQLite real)
uv run pytest -q tests/integration/

# Ejecutar toda la suite con cobertura
uv run pytest -q tests/

# Generar gastos recurrentes vencidos (simular cron diario)
uv run scripts/process_recurring_expenses_cron.py

# Vista previa sin escribir nada (dry-run)
uv run scripts/process_recurring_expenses_cron.py --dry-run

# Importar lluvia desde AEMET/Ibericam para todos los municipios
uv run scripts/import_rainfall_cron.py

# Vista previa sin escribir nada
uv run scripts/import_rainfall_cron.py --dry-run
```

### Acceso inicial a la aplicación

1. **Registrarse**: Visita `/register` para crear el primer usuario (será admin automáticamente)
2. **Login**: Ve a `/login` con tus credenciales
3. **Dashboard**: Accede al dashboard principal en `/`
4. **Admin (solo si eres admin)**: Gestiona usuarios en `/admin/users`

## Pruebas unitarias (services first)

Se cuenta con una suite de tests unitarios y de integración en `tests/`.

Cobertura actual: **>82%** (umbral mínimo exigido en CI).

Cobertura por módulo:

- CRUD de `plots_service` con cálculo automático de porcentajes.
- CRUD y contexto de listados de `expenses_service`, `recurring_expenses_service` e `incomes_service`.
- CRUD y contexto de listados de `irrigation_service` y `wells_service`.
- Cálculo de contexto en `dashboard_service` y `reports_service`.
- Generación de contexto serializado de `charts_service`.
- Cálculo de KPIs en `kpi_service`.
- Integración Stripe en `billing_service` (trial, checkout, portal, webhooks).
- Autenticación, roles y gating de suscripción en `auth.py`.
- Routers: auth, billing, expenses, plots, incomes, irrigation, plants, wells, scan, assistant, exports, imports, plot events, plot analytics, recurring expenses.
- Utilidades de campaña agrícola.

Ejecutar pruebas:

```bash
uv run pytest -v tests/
```

Resultado actual de referencia:

- **751 tests pasando** (unitarios, integración y routers)

## 3.2 Operativa Fly.io (Semana 1)

### Pipeline activo

- `CI` se ejecuta en PR/push a `main` (tests + build + bootstrap de migraciones en BD vacía).
- `Fly Deploy` se dispara tras `CI` exitoso en `main` y ejecuta healthcheck post-deploy.

### Verificación rápida de entorno dev

```bash
curl -sS -i https://truficultura-dev.fly.dev/health | head -n 20
flyctl status --app truficultura-dev
flyctl logs --app truficultura-dev --no-tail | tail -n 120
```

### Rollback rápido (imagen previa)

1. Identificar imagen/release estable previa en logs o Actions.
2. Desplegar de nuevo esa imagen/commit desde el workflow o con `flyctl deploy` apuntando al commit anterior.
3. Verificar `/health` y login.

### Notas de disponibilidad

- `fly.toml` mantiene `min_machines_running = 2` y `auto_stop_machines = 'off'` para reducir riesgo de downtime en dev durante despliegues.

---

## Pruebas de integración (BD SQLite real)

Se cuenta con tests de integración en `tests/integration/` que ejercitan los servicios contra una base de datos SQLite real creada en `tmp_path` por pytest (sin necesidad de levantar PostgreSQL).

Requiere `aiosqlite` (incluido en dependencias de desarrollo):

```bash
uv pip install "aiosqlite>=0.20.0"  # si no está ya instalado
```

Escenarios cubiertos:

- **CRUD completo**: crea parcela, gasto e ingreso; verifica que aparecen en los contextos de listado; elimina la parcela y comprueba que `get_plot` devuelve `None`.
- **Dashboard y rentabilidad**: dos parcelas con reparto automático por plantas, gastos asignados y sin asignar, ingresos. Valida totales y rentabilidad.
- **Gráficas**: crea un registro de cada tipo y valida que `build_charts_context` devuelve valores y etiquetas correctos.

Ejecutar pruebas de integración:

```bash
.venv/bin/python -m pytest -v tests/integration
```

Suite completa (unitarios + integración):

```bash
.venv/bin/python -m pytest -v tests/
```

---

## Notas de implementación y mantenimiento

- La app usa sesiones asíncronas por request, con commit/rollback automático en dependencia de BD.
- **Cálculo automático de porcentajes**: Cada vez que se crea, actualiza o elimina una parcela, los porcentajes se recalculan automáticamente basándose en el total de plantas de todas las parcelas del usuario.
- El filtro Jinja `campaign_label` permite representar campañas como `2025/26`.
- Las plantillas comparten layout base (`base.html`) y usan Bootstrap para UI consistente.
- El dashboard y reportes agregan datos en Python tras consulta a BD.
- Los KPIs también se calculan en la capa de servicios a partir de ingresos, gastos y riego, sin columnas redundantes en BD.
- **Autenticación por sesiones**: Sistema de login/logout con sesiones HTTP. Los datos están aislados por usuario_id.
  - Las contraseñas se hashean usando Argon2 (no se almacenan en texto plano)
  - Las sesiones se validan contra la BD en cada request protegido
  - Si un usuario se desactiva, su sesión sigue siendo válida hasta que expire o cierre sesión
- **Sistema de roles**:
  - `admin`: Acceso completo a gestión de usuarios + datos como usuario regular
  - `user`: Acceso solo a sus propios datos
  - Protección: Los usuarios solo ven/modifican sus propios datos (filtrados por user_id)
- **Gestión de datos**: Limpieza de histórico de repositorio usando `git-filter-repo` para remover datos confidenciales.
- **Asistente**: expone endpoints API con rate limiting por sesión y métricas básicas solo visibles para admin.

---

## Futuras mejoras recomendadas

- Alertas por email ante heladas, sequía u otros umbrales climáticos configurables.
- Exportación de informes analíticos a PDF.
- Ampliar tests de integración con contenedor PostgreSQL real para comportamientos específicos de pgSQL.
- Tipar los contextos de plantillas con dataclasses o Pydantic para evitar errores de claves.
- Añadir más opciones de filtrado y búsqueda en listados.
- Comparativa anual con campañas anteriores en el dashboard global.
- Integración con más fuentes meteorológicas (p. ej. Open-Meteo, Meteofrance).
- App móvil / PWA optimizada para uso en campo.

---

## Licencia

Definir según necesidades del proyecto.
