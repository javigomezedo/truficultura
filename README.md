# Truficultura

Aplicación web para la gestión de una explotación trufícola: parcelas, gastos, ingresos, rentabilidad por campañas y gráficas de evolución.

## 1. Resumen del proyecto

Truficultura permite registrar y analizar la actividad económica de una explotación de trufa con una lógica de campañas agrícolas (de mayo a abril).

### Qué resuelve

- Gestión de parcelas (bancales) con identificación cadastral y número de plantas.
- Configuración de mapas de plantas por parcela (filas/columnas, huecos y etiquetas tipo A1, C2, AA10).
- Registro de trufas por planta (manual o por QR), con histórico y filtros por campaña/parcela/planta.
- Registro de gastos (con o sin parcela asignada).
- Registro de ingresos por fecha, categoría, kg y precio por kg.
- Registro de riegos por parcela con volumen de agua y notas.
- Cálculo automático de rentabilidad global, por campaña y por parcela.
- Visualización de métricas semanales y comparativas mediante gráficas.
- Importación y exportación masiva de datos históricos desde CSV.
- Distribución proporcional de gastos generales según número de plantas por parcela.

### Lógica de negocio clave

- **Campaña agrícola**: mayo-abril.
  - Ejemplo: febrero de 2026 pertenece a campaña 2025.
- **Distribución de gastos sin parcela**:
  - Los gastos con `plot_id = None` se reparten proporcionalmente según el campo `porcentaje` de cada parcela.
  - El porcentaje se calcula automáticamente: `(num_plantas / total_plantas_usuario) * 100`
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
- **Herramientas auxiliares**: python-multipart, aiofiles, greenlet

## Arquitectura de carpetas

```text
.
├── app/
│   ├── main.py                 # Arranque FastAPI y dashboard principal
│   ├── config.py               # Configuración (DATABASE_URL, etc.)
│   ├── database.py             # Engine/sesiones async SQLAlchemy
│   ├── utils.py                # Funciones de campaña y reparto de gastos
│   ├── models/                 # Entidades ORM: Parcela, Gasto, Ingreso
│   ├── routers/                # Rutas por módulo funcional
│   ├── services/               # Lógica de negocio y agregaciones
│   ├── schemas/                # Esquemas Pydantic (DTOs)
│   └── templates/              # Vistas Jinja2
├── alembic/                    # Configuración de migraciones
├── import_data/                # Scripts + CSV de importación
├── pyproject.toml              # Dependencias y metadata
├── alembic.ini                 # Config Alembic
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
- `app/services/expenses_service.py`: CRUD y contexto de listado de gastos por campaña.
- `app/services/incomes_service.py`: CRUD y contexto de listado de ingresos por campaña.
- `app/services/irrigation_service.py`: CRUD y contexto de listados de riego por parcela y año.
- `app/services/dashboard_service.py`: cálculo del dashboard global.
- `app/services/reports_service.py`: cálculo del informe de rentabilidad.
- `app/services/charts_service.py`: datasets para gráficas y tablas de producción.
- `app/services/import_service.py`: importación de parcelas, gastos, ingresos y riego desde CSV.
- `app/services/export_service.py`: exportación de parcelas, gastos, ingresos y riego a CSV.

Beneficios directos del refactor:

- Menos duplicación de lógica en routers.
- Más facilidad para pruebas unitarias sin levantar servidor.
- Mejor mantenibilidad y evolución del dominio.

## Modelos de datos

### Usuario (User)

Campos relevantes:

- `username`: identificador único del usuario
- `email`: email único del usuario
- `first_name`: nombre
- `last_name`: apellido
- `hashed_password`: contraseña hasheada (algoritmo Argon2)
- `role`: rol del usuario (`admin` o `user`)
- `is_active`: estado (activo/inactivo)
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
- `source`: origen del registro (`manual` o `qr`)
- `created_at`: fecha/hora del registro
- `undo_window_expires_at`: límite temporal para deshacer
- `undone_at`: marca de deshecho (si aplica)
- `user_id`: usuario propietario del dato

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
- `/expenses/` CRUD de gastos + filtros por campaña.
- `/incomes/` CRUD de ingresos + filtros por campaña.
- `/irrigation/` CRUD de registros de riego + filtros por parcela y año.
- `/plots/{id}/map` mapa visual por planta con conteos por campaña y alta rápida (+1).
- `/plots/{id}/map/configure` configuración de geometría del mapa de plantas por parcela.
- `/truffles/` listado cronológico de eventos de trufa con filtros por campaña, parcela y planta.
- `/scan/{token}` alta de trufa por escaneo QR de planta.
- `/reports/` Informe de rentabilidad detallado.
- `/charts/` Análisis visual (semanal y comparativa ingresos vs gastos).
- `/import/` Importación masiva desde CSV (parcelas, gastos, ingresos, riego).
- `/export/` Exportación de datos a CSV (parcelas, gastos, ingresos, riego).
- `/admin/users` Dashboard de gestión de usuarios (solo administrador).
  - Listado de usuarios con estado (activo/inactivo)
  - Crear nuevos usuarios
  - Editar perfil y rol de usuarios existentes
  - Activar/desactivar usuarios
  - Validación de email y username únicos

---

## Sistema de roles y permisos

### Roles disponibles

**Admin**
- Acceso a todo el dashboard de administración (`/admin/users`)
- Gestión completa de usuarios (crear, editar, activar/desactivar)
- Puede asignar roles (admin o user) a otros usuarios
- Acceso a todos los datos de todas las parcelas/gastos/ingresos como usuario normal

**User** (usuario regular)
- Acceso completo a su propia explotación (parcelas, gastos, ingresos, reportes, gráficas)
- CRUD completo de sus datos
- No puede acceder al dashboard de admin u otros usuarios
- Datos completamente aislados por usuario_id

### Primeras acciones

- El primer usuario registrado se crea automáticamente como **admin**
- Los siguientes usuarios se crean como **user**
- Solo un admin puede cambiar roles otros usuarios
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

2. Edita `.env` con tu conexión real:

```env
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/truficultura
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

## Exportación de datos CSV

La exportación se realiza desde `/export/` y descarga ficheros listos para reutilizar en la importación.

Tipos de exportación disponibles:

- **Parcelas**: incluye columna `tiene_riego` (`1`/`0`)
- **Gastos**
- **Ingresos**
- **Riego**: exporta `fecha;bancal;agua_m3;notas`

Características del formato exportado:

- Delimitador `;`
- Sin fila de cabecera
- Fechas en formato `dd/mm/yyyy`
- Números en formato europeo
- Compatible con la importación de la propia aplicación
- En riego no se exporta `expense_id`, porque es una referencia interna

### Comportamiento de la importación

- **Fechas**: Formato `dd/mm/yyyy`
- **Números**: Formato europeo (1.250,50 = 1250.50)
- **Validación**: Se validan fechas y formatos; líneas inválidas se omiten con aviso
- **Porcentajes**: Se calculan automáticamente después de importar parcelas
- **Avisos**: Si un bancal no existe en ingresos/gastos, se importa sin asignar y se muestra aviso
- **Riego**: Solo se importan registros sobre parcelas existentes y con riego habilitado

La importación y exportación NO requieren ejecutar scripts; todo se hace desde el UI con feedback visual inmediato.

## Migraciones en desarrollo

Historial de migraciones:

- `0001`: baseline inicial tras reset de Alembic (schema completo actual).

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
.venv/bin/python -m pytest -q tests/services

# Ejecutar pruebas de integración (SQLite real)
.venv/bin/python -m pytest -q tests/integration

# Ejecutar toda la suite
.venv/bin/python -m pytest -q tests/

# Listar usuarios desde Python shell
python3 -c "
from sqlalchemy.sync_engine import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User
from app.config import settings

engine = create_engine(settings.DATABASE_URL.replace('asyncpg', 'psycopg2'))
Session = sessionmaker(bind=engine)
session = Session()
for user in session.query(User).all():
    print(f'{user.username} ({user.email}) - Role: {user.role} - Active: {user.is_active}')
"
```

### Acceso inicial a la aplicación

1. **Registrarse**: Visita `/register` para crear el primer usuario (será admin automáticamente)
2. **Login**: Ve a `/login` con tus credenciales
3. **Dashboard**: Accede al dashboard principal en `/`
4. **Admin (solo si eres admin)**: Gestiona usuarios en `/admin/users`

## Pruebas unitarias (services first)

Se cuenta con una suite de tests unitarios y de integración en `tests/`.

Cobertura actual:

- CRUD de `plots_service` con cálculo automático de porcentajes.
- CRUD y contexto de listados de `expenses_service` e `incomes_service`.
- Cálculo de contexto en `dashboard_service` y `reports_service`.
- Generación de contexto serializado de `charts_service`.
- Autenticación y gestión de usuarios.
- Utilidades de campaña agrícola.

Ejecutar pruebas:

```bash
.venv/bin/python -m pytest -v tests/
```

Resultado actual de referencia:

- **206 tests pasando** (unitarios, integración y routers)

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
- **Autenticación por sesiones**: Sistema de login/logout con sesiones HTTP. Los datos están aislados por usuario_id.
  - Las contraseñas se hashean usando Argon2 (no se almacenan en texto plano)
  - Las sesiones se validan contra la BD en cada request protegido
  - Si un usuario se desactiva, su sesión sigue siendo válida hasta que expire o cierre sesión
- **Sistema de roles**:
  - `admin`: Acceso completo a gestión de usuarios + datos como usuario regular
  - `user`: Acceso solo a sus propios datos
  - Protección: Los usuarios solo ven/modifican sus propios datos (filtrados por user_id)
- **Gestión de datos**: Limpieza de histórico de repositorio usando `git-filter-repo` para remover datos confidenciales.

---

## Futuras mejoras recomendadas

- Ampliar tests de integración con un contenedor PostgreSQL real para cubrir comportamientos específicos de pgSQL.
- Añadir validaciones más estrictas en formularios (frontend y backend).
- Incorporar exportación de reportes (CSV/PDF).
- Tipar los contextos de plantillas con dataclasses o Pydantic para evitar errores de claves.
- Añadir más opciones de filtrado y búsqueda en listados.
- Implementar notificaciones por email para alertas de campaña.
- Mejorar visualizaciones con gráficas más avanzadas (tendencias, predicciones).

---

## Licencia

Definir según necesidades del proyecto.
