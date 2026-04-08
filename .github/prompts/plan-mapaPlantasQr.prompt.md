## Plan: Mapa de Plantas y QR de Recolección

Implementar un nuevo dominio de plantas por parcela para pasar de un conteo agregado a un mapa editable por filas tipo Excel (A1, B3, AA12), registrar eventos de trufa por planta (+1 por captura), y habilitar escaneo QR desde móvil web para alta rápida con deshacer de 30 segundos. Se mantiene separación estricta routers → services → models, multi-tenant por user_id, y coexistencia con ingresos actuales (sin acoplar contabilidad de kg/€ en esta fase).

**Steps**
1. Fase 0 - Diseño funcional y contratos (bloqueante)
1. Definir contrato de configuración de forma por parcela: entrada manual por filas (lista de conteos por fila), etiquetas autogeneradas continuas por fila y filas estilo Excel (A..Z, AA..AZ...).
1. Definir contratos de eventos: cada scan crea evento unitario (+1 trufa) con timestamp servidor; deshacer válido 30 segundos para el último evento del usuario en esa sesión de trabajo.
1. Definir UX de login diferido para scan: QR abre URL de scan; si no hay sesión, redirección a login y retorno automático a la acción pendiente. *Depende de 1.1-1.2*

2. Fase 1 - Modelo de datos y migración (bloqueante para backend)
1. Crear entidad de planta por parcela con identificador lógico por etiqueta (row_label + plant_index) y coordenadas lógicas de ordenado para render estable; incluir user_id para reforzar aislamiento multiusuario.
1. Crear entidad de evento de trufa por planta (append-only): user_id, plot_id, plant_id, source (manual/qr), created_at, undo_window_expires_at, undone_at nullable.
1. Añadir restricciones e índices: unicidad por planta dentro de parcela (plot_id + row_order + col_order y/o plot_id + label), y consultas rápidas por user_id + plot_id + plant_id + created_at.
1. Crear migración Alembic con upgrade/downgrade completas y estrategia de compatibilidad para parcelas existentes (sin autogenerar plantas hasta que el usuario configure la forma). *Depende de 2.1-2.3*

3. Fase 2 - Servicios de dominio (bloqueante para routers)
1. Implementar servicio de mapeo de parcela: validar lista de filas, generar etiquetas A1..AAx continuas, crear/reemplazar mapa de plantas de parcela en transacción.
1. Implementar servicio de consulta de mapa para UI: devolver estructura 2D por filas con celdas vacías no permitidas (según decisión de secuencia continua).
1. Implementar servicio de eventos de trufa: create_manual_event, create_qr_event, get_counts_by_plant, undo_last_event (validando ventana 30s y ownership por user_id).
1. Implementar servicio de token/acción pendiente para flujo login-then-scan: persistencia temporal en sesión para retomar acción después de autenticarse.
1. Mantener coherencia con percentage de parcela: no modificar cálculo actual; num_plants de parcela se sincroniza desde cantidad de plantas configuradas para mantener distribución de gastos generales. *Depende de 2.x*

4. Fase 3 - Routers y casos de uso web
1. Añadir rutas de parcelas para editor de mapa: ver mapa, configurar por filas y bloquear regeneración cuando existan eventos de trufa asociados.
1. Añadir rutas de registro manual por planta: sumar trufa desde UI de mapa y endpoint para deshacer último registro.
1. Añadir rutas de escaneo QR: endpoint web autenticado que procesa token de planta y registra evento; soporte redirección a login si no hay sesión y reanudación automática al volver.
1. Añadir rutas admin para generación de QR filtrada por usuario/parcela seleccionados y descarga en PDF imprimible por parcela. *Parcialmente en paralelo con Fase 4 una vez exista servicio QR mínimo*

5. Fase 4 - UI/UX (móvil + escritorio)
1. Crear pantalla de configuración de forma de parcela (lista de filas editable: A=4, B=5...) con previsualización del mapa y validaciones inmediatas.
1. Crear vista de mapa de plantas como tabla/cuadrícula: cada celda muestra etiqueta fija y resumen visible en un vistazo con al menos tres métricas: trufas de campaña seleccionada, trufas acumuladas históricas y estado sin producción (0 histórico).
1. Añadir selector de campaña en la vista de mapa para recalcular métricas por planta sin perder el acumulado histórico en pantalla.
1. Diseñar flujo de scan en móvil web: feedback inmediato de alta correcta, anti doble toque breve y botón deshacer visible 30s.
1. Integrar acceso desde listado de parcelas (acción "Mapa") y navegación admin para "QR por plantas".
1. Añadir vista de listado detallado de trufas (tabla) con filtros por campaña, parcela y planta, mostrando fecha/hora de registro, origen (manual/qr), estado (activo/deshecho) y usuario propietario.

6. Fase 5 - QR y seguridad
1. Definir payload de QR firmado y de vida larga (incluye plant_id y control de integridad), evitando exponer datos sensibles.
1. Implementar validaciones antiabuso: throttle básico por sesión/usuario para scans repetidos en segundos y deduplicación temporal configurable (sin impedir cosecha real secuencial).
1. Verificar autorización en cada operación con patrón user_id en todas las queries (planta, parcela, eventos, undo, generación QR).
1. Añadir trazabilidad mínima: quién, cuándo, origen (manual/qr), estado (activo/deshecho).

7. Fase 6 - Reporte y analítica mínima (incluida en alcance)
1. Añadir métricas por planta embebidas en el mapa: campaña seleccionada, acumulado histórico y marca de planta sin producción.
1. Añadir resumen por parcela (top plantas, total trufas por campaña y total histórico) sin alterar los ingresos económicos existentes.
1. Añadir listado cronológico de trufas por campaña/parcela/planta con filtros y orden por fecha para auditoría operativa diaria.
1. Dejar preparado punto de extensión para futura vinculación opcional con ingresos (fuera del alcance actual).

8. Fase 7 - Testing y validación final (bloqueante para cierre)
1. Tests unitarios de servicios nuevos con patrón FakeExecuteResult/result() y verificación de filtros user_id, generación de etiquetas y reglas de undo 30s.
1. Tests de router para nuevos endpoints (mapa, +1 manual, scan QR, login-retorno, undo).
1. Tests de integración SQLite para relaciones parcela-planta-eventos y consultas de agregación por campaña/planta.
1. Ejecutar suite completa: .venv/bin/python -m pytest -q tests/.
1. Pruebas manuales guiadas en móvil: scan con sesión activa, scan sin sesión + retorno post-login, anti doble toque, deshacer dentro y fuera de ventana.

**Relevant files**
- app/models/plot.py — ampliar relación con plantas y estrategia de sincronización num_plants.
- app/models/income.py — mantener desacoplado de eventos de trufa en esta fase.
- app/models/__init__.py — registrar nuevas entidades ORM.
- app/services/plots_service.py — reutilizar patrón get/list/create/update/delete con user_id y recálculo de percentage.
- app/routers/plots.py — extender con endpoints de mapa, selector de campaña y acciones por planta.
- app/routers/incomes.py — sin cambios de lógica principal; validar coexistencia funcional.
- app/routers/admin.py — añadir entrada de generación QR por usuario/parcela.
- app/auth.py — reutilizar dependencia de sesión y flujo de retorno post-login.
- app/main.py — registrar nuevos routers y asegurar plantillas compartidas.
- app/routers/reports.py — añadir endpoint/vista de listado cronológico de trufas con filtros.
- app/services/reports_service.py — agregar consultas agregadas por campaña/planta y listado detallado por fecha.
- app/templates/parcelas/list.html — añadir acción de acceso al mapa por parcela.
- app/templates/parcelas/mapa.html — (nueva) tabla de plantas con métricas por campaña y acumulado histórico.
- app/templates/reportes/trufas_list.html — (nueva) tabla de eventos de trufa con filtros por campaña/parcela/planta.
- app/templates/base.html — enlazar navegación según rol para QR y listado de trufas.
- tests/conftest.py — patrón obligatorio de mocks para servicios async.
- tests/test_incomes_router.py — referencia de estilo para nuevos tests de router.
- tests/services/test_expenses_incomes_service.py — referencia de estilo para tests de servicios.

**Verification**
1. Configurar A=4, B=5, C=5, D=6, E=3 y verificar etiquetas exactas A1..A4, B1..B5, C1..C5, D1..D6, E1..E3.
2. Verificar filas > 26: continuar con AA1, AA2... sin colisiones.
3. Todas las consultas nuevas devuelven 404/redirect cuando plot/plant no pertenece al user autenticado.
4. Registro manual y por QR incrementan la planta correcta con timestamp.
5. Cada celda del mapa muestra correctamente: total campaña seleccionada, total histórico y estado sin producción cuando histórico es 0.
6. Cambio de campaña en UI actualiza totales de campaña por planta sin alterar el acumulado histórico.
7. Listado cronológico de trufas filtra correctamente por campaña/parcela/planta y ordena por fecha/hora.
8. Deshacer solo revierte el último evento dentro de 30 segundos y solo si pertenece al usuario.
9. Scan sin sesión redirige a login y, tras autenticar, completa la acción pendiente automáticamente una sola vez.
10. Suite completa verde: .venv/bin/python -m pytest -q tests/

**Decisions**
- Entrada de forma: manual por filas (no matriz fija ni CSV en esta fase).
- Etiquetado: automático fijo estilo fila+índice, filas tipo Excel (A..Z, AA...).
- Secuencia por fila: continua, sin huecos.
- Registro de trufas: solo contador unitario + timestamp automático.
- Visualización operativa obligatoria en mapa: por planta mostrar campaña seleccionada + acumulado histórico + indicador de sin producción.
- Reporte operativo obligatorio: listado cronológico de trufas con filtros por campaña/parcela/planta.
- Integración con ingresos económicos: separada (sin acoplar a kg/€ en este alcance).
- QR: flujo principal en web móvil autenticada, no app nativa en esta fase.
- Seguridad operativa: anti doble toque y opción de deshacer último scan en 30 segundos.
- Generación QR: desde admin, filtrando por usuario/parcela seleccionados; descarga en PDF imprimible.
- Regeneración de mapa bloqueada si existen eventos de trufa ya registrados.
- Escala objetivo: hasta ~50 parcelas por usuario y decenas/cientos de plantas por parcela.

**Further Considerations**
1. Estrategia de visualización para cientos de plantas: tabla responsive simple en primera versión; evaluar virtualización/canvas solo si aparece problema real de rendimiento.
2. Umbral objetivo de rendimiento en móvil: tiempo de carga < 2s para ~300 celdas como criterio para activar mejoras en una segunda iteración.