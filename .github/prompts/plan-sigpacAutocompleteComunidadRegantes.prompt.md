# Plan: SIGPAC Autocomplete + Comunidad de Regantes

**TL;DR:** Dos bloques independientes: (1) botón "Autocompletar desde SIGPAC" en el formulario de parcela que llama a la API pública y rellena `cadastral_ref` y `area_ha`; (2) reestructurar el formulario en dos secciones, controlado por un nuevo campo `comunidad_regantes` en el usuario.

---

## Fase 1 — Cambios en BD y migración

1. Añadir `comunidad_regantes: Boolean, default=False` a `app/models/user.py`
2. Añadir en `app/models/plot.py`: `recinto: String(10), default="1"` (para construir la URL de SIGPAC) y `caudal_riego: Float, nullable=True`
3. Crear `alembic/versions/0008_add_comunidad_regantes_recinto_caudal.py` con los tres `ALTER TABLE` y su `downgrade()`

## Fase 2 — Servicio SIGPAC

4. Crear `app/services/sigpac_service.py` con `async def fetch_sigpac_data(provincia, municipio, poligono, parcela, recinto, ...)` que devuelve un `dict` con dos sub-objetos:
   - Usa `httpx.AsyncClient` (ya en el proyecto, mismo patrón que `llm_adapter.py`), timeout 10s
   - URL: `https://sigpac.mapa.es/fega/serviciosvisorsigpac/layerinfo/recinto/{provincia},{municipio},0,0,{poligono},{parcela},{recinto}/`
   - Lanza excepción descriptiva si el recinto no existe o la API falla
   - Estructura de retorno:
     ```json
     {
       "autocomplete": {
         "cadastral_ref": "44223A012003090000FZ",
         "area_ha": 0.2695
       },
       "details": {
         "vigencia": "15/12/2025",
         "fecha_vuelo": "08/2024",
         "fecha_cartografia": "05/11/2023",
         "parcela": {
           "provincia": "44 - TERUEL",
           "municipio": "223 - SARRION",
           "agregado": 0, "zona": 0, "poligono": 12, "parcela": 309,
           "superficie_ha": 0.2695,
           "referencia_cat": "44223A012003090000FZ"
         },
         "recintos": [
           {
             "recinto": 1,
             "superficie_ha": 0.2695,
             "pendiente_pct": 4.2,
             "altitud_m": 998,
             "uso_sigpac": "TA - TIERRAS ARABLES",
             "coef_regadio": 0,
             "incidencias": "12,199",
             "region": 1
           }
         ],
         "incidencias_texto": [
           "12 - Contiene otros usos sin subdividir",
           "199 - Recinto inactivo"
         ]
       }
     }
     ```
   - Transformaciones: `dn_surface / 10000` → ha (4 dec.); `pendiente_media / 10` → %; `fecha_vuelo` `202408` → `"08/2024"`; `cat_fechaultimaconv` ISO → `"dd/mm/yyyy"`
5. Crear `tests/services/test_sigpac_service.py` — mock de `httpx`, test éxito (verifica `autocomplete` y `details`), test error HTTP, test mapeo de unidades (`pendiente_media`, `dn_surface`, `fecha_vuelo`)

## Fase 3 — Endpoint API de lookup

6. Añadir `GET /plots/sigpac-lookup` en `app/routers/plots.py` *(antes de las rutas con `{plot_id}`)*:
   - Parámetros query: `provincia`, `municipio`, `poligono`, `parcela`, `recinto="1"`
   - Validar que son numéricos (solo dígitos); proteger con `require_user`
   - Devuelve `JSONResponse` con el dict completo `{"autocomplete": {...}, "details": {...}}`, o `{"error": "..."}` con HTTP 400/502
   - El cliente JS usa `response.autocomplete` para rellenar campos y `response.details` para renderizar el modal

## Fase 4 — Schemas y servicio de parcelas

7. Actualizar `app/schemas/plot.py`: añadir `recinto: str = "1"` y `caudal_riego: Optional[float] = None` a `PlotBase` y `PlotUpdate`
8. Actualizar `app/services/plots_service.py`: añadir `recinto` y `caudal_riego` a `create_plot()` y `update_plot()` — actualizar tests asociados

## Fase 5 — Routers

9. Actualizar `app/routers/plots.py`: añadir `recinto: str = Form("1")` y `caudal_riego: Optional[float] = Form(None)` en create/update; pasar `current_user` al contexto del template en `new_plot_form` y `edit_plot_form`
10. Actualizar `app/routers/admin.py`: manejar `comunidad_regantes: Optional[str] = Form(None)` → `user.comunidad_regantes = (value == "on")` en create/edit de usuario

## Fase 6 — Frontend

11. Reestructurar `app/templates/parcelas/form.html` en tres bloques:
    - **Búsqueda SIGPAC** *(nuevo, al inicio)*: usa los campos ya existentes `provincia_cod`, `municipio_cod`, `polygon`, `plot_num` + nuevo input `recinto` + dos botones en línea:
      - **"Autocompletar desde SIGPAC"** (`id="btn-sigpac-fill"`): al click hace fetch a `/plots/sigpac-lookup`, rellena `cadastral_ref` y `area_ha` desde `response.autocomplete`; muestra badge de éxito o error
      - **"Ver detalles SIGPAC"** (`id="btn-sigpac-details"`, inicialmente oculto, `data-bs-toggle="modal" data-bs-target="#sigpacModal"`): se hace visible tras una búsqueda exitosa
    - **Datos genéricos**: `name`, `polygon`, `plot_num`, `recinto`, `cadastral_ref`, `provincia_cod`, `municipio_cod`, `area_ha`, `num_plants`, fechas, porcentaje
    - **Comunidad de Regantes de Sarrión** *(solo si `current_user.comunidad_regantes`)*: `sector`, `hydrant`, checkbox `has_irrigation`, `caudal_riego`

    **Modal `#sigpacModal`** (Bootstrap 5, colocado al final del `{% block content %}`, fuera del `<form>`):
    - Cabecera del modal: `bi-map` + "Información SIGPAC"
    - Banner azul: "La siguiente información es la vigente en SigPac a fecha: {vigencia}"
    - Fila con dos badges: "Fecha de vuelo: {fecha_vuelo}" y "Fecha cartografía catastral: {fecha_cartografia}"
    - Tabla **Datos parcela** (cabeceras: Provincia, Municipio, Agregado, Zona, Polígono, Parcela, Superficie (ha), Referencia Catastral) — una fila con los datos de `details.parcela`
    - Tabla **Recintos** (cabeceras: Recinto, Superficie (ha), Pendiente (%), Altitud (m), Uso, Coef. Regadío, Incidencias, Región) — una fila por ítem en `details.recintos`
    - Lista **Incidencias** (solo si `details.incidencias_texto.length > 0`): título "Incidencias" + `<ul>` con cada texto
    - Todo el HTML del modal se genera en JS mediante `renderSigpacModal(details)` que construye las tablas dinámicamente y los inyecta en el `modal-body` antes de mostrar el modal
    - Estilo: tablas `table table-sm table-bordered`, banner con `bg-primary text-white rounded p-2 mb-3`
12. Actualizar `app/templates/admin/user_create.html`: añadir checkbox `comunidad_regantes`
13. Actualizar `app/templates/admin/user_edit.html`: añadir checkbox `comunidad_regantes` con estado precargado

---

## Archivos afectados

- `app/models/user.py` — nuevo campo `comunidad_regantes`
- `app/models/plot.py` — nuevos campos `recinto`, `caudal_riego`
- `alembic/versions/0008_add_comunidad_regantes_recinto_caudal.py` — nueva migración
- `app/services/sigpac_service.py` — nuevo servicio
- `app/services/plots_service.py` — añadir campos nuevos + actualizar tests
- `app/schemas/plot.py` — añadir campos nuevos
- `app/routers/plots.py` — endpoint SIGPAC lookup + campos nuevos en create/update + pasar `current_user` al template
- `app/routers/admin.py` — manejar `comunidad_regantes` en create/edit usuario
- `app/templates/parcelas/form.html` — reestructurar secciones + JS SIGPAC
- `app/templates/admin/user_create.html` — checkbox `comunidad_regantes`
- `app/templates/admin/user_edit.html` — checkbox `comunidad_regantes`
- `tests/services/test_sigpac_service.py` — nuevo
- Tests de plots_service — actualizar para nuevos campos

---

## Verificación

1. `alembic upgrade head` aplica sin errores
2. Usuario con `comunidad_regantes=True` → formulario de parcela muestra la sección de regantes; con `False` → la sección no aparece
3. Lookup SIGPAC: provincia 44, municipio 223, polígono 25, parcela 12, recinto 1 → rellena `cadastral_ref = "44223A025000120000FZ"` y `area_ha ≈ 1.7733`
4. Crear/editar parcela guardando todos los campos nuevos
5. `.venv/bin/python -m pytest -q tests/` — todos los tests verdes

---

## Decisiones y scope

- `recinto` se persiste en BD para poder re-hacer el lookup en modo edición sin reintroducir el dato
- `agregado` y `zona` se fijan en "0" (valor habitual); no aparecen en el formulario
- Los campos `sector`, `hydrant`, `has_irrigation` **no se eliminan del modelo** (compatibilidad con datos existentes); solo se ocultan en el formulario para usuarios fuera de la comunidad de regantes
- No se almacenan campos adicionales de SIGPAC (`uso_sigpac`, `altitud`, `pendiente_media`): solo `cadastral_ref` y `area_ha` encajan con campos ya existentes
- El modal se rellena íntegramente en el cliente (JS): el endpoint devuelve `details` ya transformado (unidades, fechas formateadas); el template no hace ningún render Jinja2 del modal
- El estado del modal (`details`) se guarda en memoria JS (`window._sigpacDetails`) para poder reabrirlo sin un segundo fetch
