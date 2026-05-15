# Plan: Trufiq para todos — Mejoras UX integrales

Hacer que Trufiq sea usable por truficultores sin formación digital. Se ejecuta en 4 fases secuenciales: primero limpiar la jerga existente (gana rápida y barata), luego rediseñar formularios y la importación (mayor impacto en frustración), luego cambiar la navegación (orientada a tareas) y por último el acompañamiento (onboarding guiado + vídeos).

**Decisiones confirmadas con el usuario**:
- Orden estricto: Fase 1 → 2 → 3 → 4. Cada fase debe quedar verde en tests antes de pasar a la siguiente.
- El **wizard sustituye** al formulario actual de parcela (no se mantiene "modo avanzado").
- Los **vídeos se incluyen** en el plan con guiones listos para grabar; el usuario los grabará después.
- **Alojamiento de vídeos**: self-host en `app/static/videos/` (sin canal de YouTube). Cero cookies de terceros, control total, reproducción HTML5 nativa. Se generarán dos resoluciones (720p / 1080p) con `<source media>` y `poster` JPG. Migración futura a Cloudflare R2 si el catálogo crece, sin cambios en la UI.
- **Estado de onboarding del usuario**: la tabla `users` no tiene columnas JSON. Se añadirá una migración Alembic con dos columnas nuevas: `onboarding_step` (string nullable, p. ej. `"welcome"`, `"first_plot"`, `"first_expense"`, `"done"`, `"skipped"`) y `onboarding_completed_at` (timestamp nullable). Sin defaults destructivos para usuarios existentes (se marcan como `"done"` en el upgrade).

---

## FASE 1 — Lenguaje y transparencia

Objetivo: eliminar conceptos opacos sin tocar lógica de negocio. Solo plantillas + un componente de tooltip + revisión de textos.

### 1.1 Componente reutilizable de ayuda contextual
- Crear `app/templates/_partials/help_hint.html`: macro Jinja `help_hint(term, body, link=None)` que renderiza un icono `bi-question-circle` con popover Bootstrap 5.
- Inicializar popovers en [app/templates/base.html](app/templates/base.html) con un bloque JS (delegated) que active `[data-bs-toggle="popover"]` al cargar y tras inserciones dinámicas.
- Estilo: el icono va inline junto al label, tamaño pequeño, color `text-muted`. En móvil se activa con tap.
- Accesibilidad: `aria-label="Más información sobre <term>"`, contenido del popover accesible por teclado.

### 1.2 Página de glosario `/ayuda/glosario`
- Nuevo router ligero `app/routers/help.py` con vista pública (no requiere login para que sea linkable).
- Plantilla `app/templates/ayuda/glosario.html`: lista alfabética de términos con anclas. Cada `help_hint` enlaza a `#anchor` del glosario para "saber más".
- Términos a cubrir (mínimo): Brulé, Campaña agrícola, Bancal, Catastro/SIGPAC, Polígono, Recinto, Prorrateo, Porcentaje de parcela, Distribución de gastos generales, ROI/Rentabilidad, Host (carrasca/roble), Recolecta vs Cosecha.

### 1.3 Aplicar `help_hint` en formularios y listados
Archivos a tocar:
- [app/templates/parcelas/list.html](app/templates/parcelas/list.html): tooltip junto al header "% parcela" con: "Calculado automáticamente según el nº de plantas que tiene esta parcela respecto al total de tu explotación. Sirve para repartir los gastos generales entre parcelas."
- [app/templates/gastos/form.html](app/templates/gastos/form.html): tooltip junto a "Categoría", "Prorratear" y "Bancal".
- [app/templates/brule/*.html](app/templates/brule/): tooltip junto a "Brulé" en cada formulario y cabecera.
- [app/templates/parcelas/form.html](app/templates/parcelas/form.html): tooltips en "Polígono", "Recinto", "Provincia/Municipio SIGPAC".
- Headers/labels de campaña en dashboard y reportes: tooltip "La campaña agrícola va de mayo a abril. 2025/26 = mayo 2025 a abril 2026."

### 1.4 Aviso visible del reparto de gastos generales
- En [app/templates/gastos/form.html](app/templates/gastos/form.html), si el campo "Bancal" queda vacío, mostrar bajo el select un `alert-info` dinámico (JS) con texto:
  > "ℹ️ Al no asignar bancal, este gasto se repartirá entre tus N parcelas según su tamaño en plantas. Ver detalle ▾"
  Donde "Ver detalle" expande una mini tabla con el % de cada parcela.
- En [app/templates/gastos/list.html](app/templates/gastos/list.html): badge "General" en gastos sin bancal con tooltip explicando el reparto.
- Backend: ya existe `distribute_unassigned_expenses()` en [app/utils.py](app/utils.py), solo hace falta exponer los porcentajes actuales por AJAX o renderizarlos en el GET.

### 1.5 Reescritura de copy crítico
Sustitución manual revisada en plantillas. Lista no exhaustiva, ampliar al implementar:
- "Prorratear en varios años" → **"¿Es una inversión grande que dura varios años?"** + ayuda: "Marca si es un tractor, riego, nave o cualquier compra que aprovecharás durante más de una campaña. La aplicación lo repartirá entre los años que indiques para que tus números cuadren mejor."
- "Has agotado la cuota de X/N sesiones" → **"Has usado tus N importaciones asistidas con IA este mes. Se reinician el día 1. Mientras tanto puedes importar manualmente desde Análisis → Importar."**
- "Sólo lectura" / "Plan superior" → mensaje concreto: **"Esta función requiere el plan Premium. Tu plan actual: Basic. Ver planes →"**.
- "Parcela no encontrada" en errores → "No encontramos esa parcela. Puede que la hayas borrado o que no sea tuya."
- "El bancal no existe" → unificar terminología (usar **siempre "parcela"** en la UI, dejar "bancal" como alias mostrado solo en tooltip).

### 1.6 Tests Fase 1
- Añadir test en `tests/test_help_router.py`: GET `/ayuda/glosario` → 200, contiene "Brulé".
- Smoke render tests existentes deben seguir pasando con los cambios de plantilla.

---

## FASE 2 — Formularios menos hostiles

Objetivo: eliminar abandono en formularios largos y errores de importación.

### 2.1 Wizard de creación/edición de parcela (sustituye al form actual)

**Diseño en 3 pasos**, una sola URL `/plots/new` con estado en sesión o en query string:

- **Paso 1 — Lo básico** (siempre obligatorio):
  - Nombre de la parcela (requerido).
  - Superficie en hectáreas (opcional, con texto: "Si no la sabes, déjalo en blanco; puedes rellenarlo después").
  - Botón grande "Siguiente".
- **Paso 2 — Datos del catastro** (saltable):
  - Banner: "¿Tienes a mano los datos del SIGPAC? Te ahorrará escribirlo todo. Si no, dale a **Saltar**."
  - Buscador SIGPAC actual (provincia → municipio → polígono → parcela → recinto + botón autocompletar).
  - Si autocompleta, muestra resumen "Hemos encontrado: 1,2 ha en Soria, polígono 17 parcela 42".
  - Botones "Atrás" / "Saltar" / "Siguiente".
- **Paso 3 — Detalles** (saltable):
  - Descripción libre.
  - Checkbox "Tiene riego automático" con icono y ayuda.
  - Botones "Atrás" / **"Crear parcela"**.
- En todos los pasos: barra de progreso superior (1 de 3, 2 de 3, 3 de 3) con etiquetas.
- En móvil: cada paso ocupa toda la pantalla, botones de pulgar grandes (`btn-lg w-100`).

**Implementación**:
- Reescribir [app/templates/parcelas/form.html](app/templates/parcelas/form.html) como template único con `{% if step == 1 %}…` o tres includes (`_step1.html`, `_step2.html`, `_step3.html`).
- En [app/routers/plots.py](app/routers/plots.py): GET acepta `?step=` y conserva los campos previos vía query string o sesión (`request.session["plot_draft"]`).
- POST del paso final crea la parcela usando el servicio existente. Pasos intermedios actualizan borrador y redirigen al siguiente.
- Edición: mantener un único formulario en una página (el wizard solo aplica al alta) pero con la misma estética y tooltips.
- Tests: añadir a [tests/test_plots_router.py](tests/test_plots_router.py) cobertura de los 3 pasos y del salto del paso 2.

### 2.2 Autoguardado en `localStorage` para formularios largos
- Nuevo `app/static/js/form_autosave.js`: para cualquier `<form data-autosave="<id>">` serializa los inputs cada 5s en `localStorage` bajo `trufiq:draft:<id>:<user_id_from_meta>`. Excluye contraseñas y `file`.
- Al cargar el form, si hay borrador no enviado, mostrar banner: "Tienes datos sin guardar de hace X min. **Restaurar** / **Descartar**".
- Limpia el borrador en `submit` exitoso (escuchando `submit` y al volver con flash success).
- Aplicar `data-autosave` en: alta de parcela (wizard, cada paso), alta de gasto, alta de brulé, perfil.
- Incluir el script en [app/templates/base.html](app/templates/base.html) (defer).

### 2.3 Texto de "prorrateo" rediseñado
Ya cubierto en Fase 1.5 a nivel de copy, ahora en Fase 2 se acompaña de UI:
- Al marcar el checkbox, animación de revelado con ejemplo numérico vivo: "Si gastas 18.000 € en 3 años, contaremos 6.000 €/año en las campañas 2025/26, 2026/27 y 2027/28."
- Archivo: [app/templates/gastos/form.html](app/templates/gastos/form.html) + pequeño JS de cálculo en `app/static/js/expense_form.js`.

### 2.4 Importación de CSV/Excel: validación cariñosa
- En [app/routers/imports.py](app/routers/imports.py) y servicio asociado en `app/services/`:
  - Antes de procesar, detectar separador (`,` vs `;`) leyendo la primera línea con `csv.Sniffer`.
  - Detectar formato numérico mirando si hay valores con `,` como decimal vs `.`.
  - Detectar formato de fecha probando `dd/mm/yyyy`, `yyyy-mm-dd`, `dd-mm-yyyy`.
- En plantillas de [app/templates/imports/](app/templates/imports/):
  - Tras subir, mostrar **vista previa de las primeras 5 filas** parseadas (no importadas todavía) con check verde por columna correctamente detectada o aviso amarillo si algo huele raro.
  - Si el separador no es `;`, mostrar aviso amarillo: "Tu fichero parece usar coma como separador. **Convertir automáticamente** / **Cancelar**".
  - Botón "Confirmar importación" solo aparece tras la vista previa.
- Mantener la opción IA actual para usuarios Premium intacta.
- Tests: ampliar [tests/test_imports_router.py](tests/test_imports_router.py) con fixtures de CSV mal formados (coma, formato anglo, fechas ISO) y verificar mensajes amigables + posibilidad de autocorrección.

### 2.5 Verificación Fase 2
- Test manual: alta de parcela en móvil real con conexión 4G simulada.
- Test manual: subir CSV con coma como separador y comprobar que el sistema lo propone convertir.
- Test manual: rellenar gasto, cerrar pestaña, reabrir → ver banner de restaurar.
- Suite completa de tests en verde.

---

## FASE 3 — Navegación orientada a tareas

Objetivo: reducir el tiempo entre "tengo algo que apuntar" y el formulario correcto.

### 3.1 Dashboard reorientado
- En [app/templates/index.html](app/templates/index.html), reemplazar la primera fila por **tarjetas de acción** grandes (4 a 6 columnas en desktop, 2 columnas en móvil, full-width en xs):
  - "📝 Apuntar gasto" → `/expenses/new`
  - "🌧️ Apuntar lluvia" → `/lluvia/new` (o flujo más corto)
  - "🌰 Apuntar cosecha" → `/harvests/new`
  - "🔬 Apuntar brulé" → `/brule/new`
  - "🚜 Apuntar labor" → `/plot-events/new`
  - "📊 Ver rentabilidad" → `/reports/profitability`
- Cada tarjeta: icono grande Bootstrap Icons, título, una línea de subtítulo ("último: hace X días").
- Mantener debajo el checklist de primeros pasos (solo se muestra hasta que esté completo) y el resumen por campaña.

### 3.2 Búsqueda global / paleta de comandos
- Icono lupa en [app/templates/base.html](app/templates/base.html) navbar (también accesible con `Ctrl/Cmd+K`).
- Modal con input grande y lista filtrada en cliente. Índice estático JSON en `app/static/data/search_index.json` generado a mano con entradas tipo:
  ```json
  [{"label":"Apuntar gasto","keywords":["gasto","factura","gasoil","compra"],"url":"/expenses/new"},
   {"label":"Lluvia","keywords":["lluvia","mm","agua","precipitacion"],"url":"/lluvia/"},
   {"label":"Crear parcela","keywords":["parcela","bancal","nueva"],"url":"/plots/new"}]
  ```
- Búsqueda fuzzy ligera (sin librería pesada). Atajo Enter abre.
- En el futuro se puede generar dinámicamente; por ahora estático es suficiente.

### 3.3 Modo lista para el mapa visual de plantas
- En [app/templates/parcelas/mapa.html](app/templates/parcelas/mapa.html), añadir toggle "🗺️ Mapa" / "📋 Lista".
- La lista muestra plantas paginadas con filtros (estado, host, brulé reciente) y enlace directo al detalle. Reutiliza datos ya cargados.
- En móvil, modo lista es el predeterminado.

### 3.4 Tests Fase 3
- Test de render del nuevo dashboard.
- Test de presencia del modal de búsqueda.

---

## FASE 4 — Acompañamiento y vídeos

Objetivo: que un usuario nuevo aprenda sin documentación externa.

### 4.1 Onboarding guiado conversacional
- **Migración Alembic nueva** que añade a la tabla `users` dos columnas:
  - `onboarding_step` (`String(32)`, nullable). Valores previstos: `"welcome"`, `"first_plot"`, `"first_plants"`, `"first_expense"`, `"done"`, `"skipped"`.
  - `onboarding_completed_at` (`DateTime`, nullable).
  - En el `upgrade()`, marcar a todos los usuarios existentes con `onboarding_step = "done"` y `onboarding_completed_at = now()` para que el modal no les aparezca.
  - `downgrade()` elimina ambas columnas.
- Actualizar el modelo `User` en [app/models/](app/models/) con los dos campos.
- Tras el primer login (detectar `onboarding_step IS NULL` o `"welcome"`), mostrar **modal de bienvenida** que pregunta:
  1. "¿Cuántas parcelas tienes? [1] [2-5] [Más de 5]".
  2. Según respuesta, ofrece: "Crear tu primera parcela" (lleva al wizard) o "Importar todas a la vez" (lleva al onboarding IA con explicación).
  3. Al terminar la primera parcela, ofrece "Añadir plantas" y luego "Apuntar tu primer gasto" o "Importar histórico".
- El paso actual se persiste en `onboarding_step` tras cada hito completado.
- Botón "Saltar onboarding" siempre disponible → `onboarding_step = "skipped"`.
- Endpoint `POST /onboarding/guide/step` que recibe el siguiente paso y actualiza el usuario.
- Aprovecha el modal existente en base.html y el asistente IA si está disponible.

### 4.2 Mejoras al asistente IA para principiantes
- En la pantalla del asistente, sugerir **3-5 preguntas frecuentes** clickables tipo "¿Cuánto gasté en gasoil este año?", "¿Cuál fue mi mejor campaña?", "¿Qué parcelas tengo sin brulé este año?".
- Botón flotante visible en todas las páginas (mobile + desktop) con tooltip "Pregúntame".

### 4.3 Vídeos tutoriales (a grabar por el usuario)
- Catálogo en un fichero de configuración Python `app/help_videos.py` con un diccionario:
  ```python
  HELP_VIDEOS = {
      "primera_parcela": {"title": "Crea tu primera parcela", "slug": "primera_parcela", "duration_s": 70, "poster": "primera_parcela.jpg"},
      "primer_gasto": {...},
      ...
  }
  ```
- **Alojamiento self-hosted**: ficheros físicos en `app/static/videos/` con la convención `{slug}-720p.mp4`, `{slug}-1080p.mp4` y `{slug}.jpg` para el póster. La URL final la construye el componente.
- Componente Jinja `help_video(slug)` (macro en `app/templates/_partials/help_video.html`) que renderiza un botón discreto `▶️ Vídeo (1 min)` y abre un modal Bootstrap con:
  ```html
  <video controls preload="metadata" poster="/static/videos/{slug}.jpg">
    <source src="/static/videos/{slug}-1080p.mp4" type="video/mp4" media="(min-width: 768px)">
    <source src="/static/videos/{slug}-720p.mp4" type="video/mp4">
  </video>
  ```
- El catálogo solo lista los vídeos cuyo fichero existe en disco (check en startup o lazy). Mientras el usuario no haya grabado un vídeo, el botón no aparece en la UI correspondiente.
- Insertar en cada sección clave: dashboard, listado de parcelas, alta de parcela, alta de gasto, importación, brulé, cosechas, mapa de plantas.
- Página índice `/ayuda/videos` con tarjetas de todos los vídeos disponibles.
- **Recomendaciones de codificación para el usuario al grabar/exportar**: H.264 + AAC, bitrate ~2 Mbps para 720p y ~4 Mbps para 1080p, faststart activado (`-movflags +faststart`) para que el navegador empiece a reproducir antes de descargar entero. Comando ffmpeg de ejemplo en el README de la carpeta.
- Añadir `app/static/videos/README.md` con las convenciones de nombres y el comando ffmpeg recomendado.

### 4.4 Guiones de vídeo (listos para grabar)

Formato común para todos: 50-90 segundos, primera persona ("vamos a…"), pantalla compartida con cursor visible, voz tranquila. Cada guion incluye **lo que se ve** y **lo que se dice**. Recomendación: grabar con OBS a 1080p, fuente del navegador ampliada (Ctrl++ x2) para que se vea bien en móvil.

#### Vídeo 1 — "Bienvenido a Trufiq" (60 s)
- **Voz**: "Hola, soy [nombre]. En este minuto te enseño qué puedes hacer con Trufiq."
- **Pantalla**: dashboard recién creado.
- **Voz**: "Esta es tu pantalla principal. Aquí vas a apuntar lo que pasa en tu finca: parcelas, gastos, lluvia, cosechas… y al final del año, la aplicación te dice si has ganado o has perdido dinero, parcela por parcela."
- **Pantalla**: cursor pasa por las tarjetas de acción.
- **Voz**: "Estas tarjetas son los atajos para lo que harás más a menudo. Si no encuentras algo, arriba a la derecha tienes una lupa: escribe lo que quieras y te lleva."
- **Pantalla**: clic en lupa, escribir "lluvia".
- **Voz**: "Empezamos por crear tu primera parcela. Pulsa la tarjeta 'Crear parcela' o sigue el siguiente vídeo."

#### Vídeo 2 — "Crea tu primera parcela" (70 s)
- **Voz**: "Vamos a crear una parcela. Solo necesitas el nombre."
- **Pantalla**: clic en "Crear parcela", paso 1 del wizard.
- **Voz**: "Le pongo nombre, por ejemplo 'El Carrasco'. Si sé las hectáreas las pongo, si no, lo dejo en blanco. Siguiente."
- **Pantalla**: paso 2.
- **Voz**: "Si tengo los datos del catastro, los meto y el SIGPAC me rellena el resto automáticamente. Provincia, municipio, polígono, parcela. Le doy a 'Autocompletar'."
- **Pantalla**: campos se rellenan solos.
- **Voz**: "Si no los tengo a mano, le doy a 'Saltar' y los pongo otro día. Siguiente."
- **Pantalla**: paso 3, marca "Tiene riego automático".
- **Voz**: "Por último, una descripción si quiero, y si tiene riego lo marco. Listo. **Crear parcela**."
- **Pantalla**: aparece en la lista.
- **Voz**: "Ya está. Ahora puedes añadirle plantas o apuntar un gasto."

#### Vídeo 3 — "Apunta un gasto en 30 segundos" (50 s)
- **Voz**: "Vamos a apuntar el gasto del gasoil de hoy."
- **Pantalla**: tarjeta "Apuntar gasto" del dashboard.
- **Voz**: "Pulso aquí. Fecha de hoy, ya está puesta. Concepto: 'Gasoil tractor'. Cantidad: 120 euros."
- **Pantalla**: rellena los campos.
- **Voz**: "Si el gasto es para una parcela concreta, la elijo. Si es general, lo dejo en blanco y la aplicación lo repartirá entre todas mis parcelas. Mira, aquí me lo avisa."
- **Pantalla**: aparece el aviso amarillo del reparto.
- **Voz**: "Le doy a guardar y listo. Si fuera una inversión grande como un tractor, marcaría esta casilla para que se reparta en varios años. Pero para el gasoil, no."

#### Vídeo 4 — "Apunta una cosecha desde el móvil" (45 s)
- **Voz**: "Estás en el campo con el móvil. Acabas de coger trufas. Así lo apuntas en cinco segundos."
- **Pantalla**: móvil real o vista responsive. Barra inferior.
- **Voz**: "Abajo a la derecha, 'Cosechas'. Pulsa. Elijo la parcela, fecha de hoy, kilos: 1,3. Precio del kilo: 400. Guardar."
- **Pantalla**: confirmación verde.
- **Voz**: "Si tienes el QR de la planta impreso, todavía más rápido: lo escaneas con la cámara y solo pones los kilos."

#### Vídeo 5 — "Importar tu Excel de toda la vida" (90 s)
- **Voz**: "Llevas años apuntando en Excel. Tranquilo, no tienes que volver a meter nada a mano."
- **Pantalla**: menú Análisis → Importar.
- **Voz**: "Tienes dos formas. La primera, importación manual: subes un CSV con la estructura que te indicamos, y la aplicación te enseña una vista previa antes de importar nada."
- **Pantalla**: arrastra un CSV, aparece la vista previa.
- **Voz**: "Si algo está mal, te avisa y te lo intenta arreglar automáticamente. Por ejemplo, si tu Excel usa comas en vez de punto y coma, pulsas 'Convertir' y listo."
- **Pantalla**: clic en "Convertir", luego "Confirmar".
- **Voz**: "La segunda forma, si tienes el plan Premium, es la importación con inteligencia artificial: subes tu Excel tal cual, con las hojas que sea, y el asistente entiende solo qué es cada cosa. Tú revisas que esté bien y confirmas."

#### Vídeo 6 — "Mira si tu finca da dinero" (60 s)
- **Voz**: "Aquí está el por qué de toda esta aplicación: saber si ganas o pierdes."
- **Pantalla**: menú Finanzas → Rentabilidad.
- **Voz**: "Esta tabla te enseña cada campaña: lo que has gastado, lo que has ingresado, y el resultado. En verde si has ganado, en rojo si has perdido."
- **Pantalla**: hace scroll, hover en barras del gráfico.
- **Voz**: "Y si quieres saberlo parcela por parcela, vas a Análisis → KPIs y ves cuál es la que mejor te funciona. Esto te ayuda a decidir dónde plantar más o dónde ajustar gastos."

#### Vídeo 7 — "Pregúntale al asistente con tu voz" (40 s)
- **Voz**: "Tienes las manos sucias y quieres saber cuánto llevas gastado este año."
- **Pantalla**: icono flotante del asistente.
- **Voz**: "Pulso el icono del asistente, pulso el micrófono, y le pregunto."
- **Audio**: "¿Cuánto he gastado en gasoil este año?"
- **Pantalla**: respuesta en chat.
- **Voz**: "Y me lo dice. Puedes pedirle resúmenes, comparativas, lo que necesites."

### 4.5 Página /ayuda con vídeos y FAQ
- Plantilla `app/templates/ayuda/index.html` con secciones: vídeos, glosario, preguntas frecuentes.
- FAQ inicial con 8-10 entradas: "¿Qué es una campaña?", "¿Por qué se reparten los gastos sin parcela?", "¿Cómo borro una parcela?", "¿Mis datos son míos?", "¿Cómo cambio el idioma?", "He perdido la contraseña", "¿Puedo dar acceso a mi asesor?", "¿Cómo exporto todo para mi gestor fiscal?".

### 4.6 Tests Fase 4
- GET `/ayuda/`, `/ayuda/videos`, `/ayuda/glosario` → 200.
- Modal de bienvenida solo aparece para usuarios nuevos sin parcelas.

---

## Orden de ejecución y handoffs

Cada fase es un commit (o PR) independiente. Tras cada fase: ejecutar `pytest`, revisar manualmente y avisar al usuario antes de comenzar la siguiente. El usuario puede grabar los vídeos en paralelo a la Fase 3 (los guiones ya están listos).

## Archivos clave que se tocarán (resumen)

- [app/templates/base.html](app/templates/base.html) — popovers, búsqueda global, asistente flotante, autosave script
- [app/templates/_partials/help_hint.html](app/templates/_partials/help_hint.html) — nuevo
- [app/templates/ayuda/](app/templates/ayuda/) — nuevo directorio (glosario, vídeos, FAQ, index)
- [app/templates/index.html](app/templates/index.html) — dashboard con tarjetas de acción
- [app/templates/parcelas/form.html](app/templates/parcelas/form.html) — wizard 3 pasos
- [app/templates/gastos/form.html](app/templates/gastos/form.html) — copy prorrateo, aviso reparto
- [app/templates/gastos/list.html](app/templates/gastos/list.html) — badge "General"
- [app/templates/imports/](app/templates/imports/) — vista previa y autocorrección
- [app/templates/parcelas/mapa.html](app/templates/parcelas/mapa.html) — toggle mapa/lista
- [app/routers/help.py](app/routers/help.py) — nuevo
- [app/routers/plots.py](app/routers/plots.py) — soporte wizard
- [app/routers/imports.py](app/routers/imports.py) — detección de formato
- [app/services/imports_service.py](app/services/) — sniffing, conversión
- [app/help_videos.py](app/) — nuevo, catálogo de vídeos
- [app/static/videos/](app/static/videos/) — nueva carpeta + README con convenciones (`{slug}-720p.mp4`, `{slug}-1080p.mp4`, `{slug}.jpg`) y comando ffmpeg recomendado
- [app/templates/_partials/help_video.html](app/templates/_partials/) — nuevo, macro del reproductor
- [app/static/js/form_autosave.js](app/static/js/) — nuevo
- [app/static/js/expense_form.js](app/static/js/) — preview prorrateo
- [app/static/js/global_search.js](app/static/js/) — nuevo, paleta de comandos
- [app/static/data/search_index.json](app/static/data/) — nuevo
- `tests/test_help_router.py` — nuevo
- Tests existentes ampliados: `test_plots_router.py`, `test_imports_router.py`, `test_expenses_router.py`
- Migración Alembic nueva en `alembic/versions/` para `users.onboarding_step` + `users.onboarding_completed_at`
- Modelo `User` en [app/models/](app/models/) — añadir los dos nuevos campos

## Verificación final

1. Suite `pytest` en verde al final de cada fase.
2. Test manual en móvil real: crear parcela completa por el wizard + apuntar gasto + apuntar cosecha desde la barra inferior, sin instrucciones.
3. Subir un CSV mal formado y verificar que el sistema lo corrige.
4. Verificar tooltips accesibles con teclado (Tab + Enter).
5. Comprobar que el modal de bienvenida no reaparece para usuarios existentes.
6. Lighthouse en móvil ≥ 90 en accesibilidad.

## Fuera de alcance

- Rediseño visual completo / cambio de tema.
- App nativa móvil (la PWA actual ya cubre el caso).
- Reescritura del asistente IA (solo se mejoran sugerencias y visibilidad).
- Generación dinámica del índice de búsqueda (basta JSON estático por ahora).
- Grabación real de los vídeos (los grabará el usuario).
