## Plan: Asistente In-App Para Truficultura

Objetivo: incorporar un asistente en español que resuelva dudas de uso y también preguntas sobre los datos del usuario, con experiencia de chat moderna en streaming y proveedor externo con minimización de datos.

Enfoque recomendado: implementar por fases con base de arquitectura estable desde el principio (API + servicio + proveedor LLM), arrancando con alcance controlado para reducir riesgo y coste, y dejando preparada la evolución a mayor inteligencia (RAG y acciones transaccionales) sin rehacer la base.

**Steps**
1. Fase 0 - Contrato funcional y de seguridad
- Definir alcance del MVP: preguntas de uso + preguntas analíticas de solo lectura sobre datos propios del usuario.
- Definir explícitamente fuera de alcance inicial: acciones de escritura (crear/editar/borrar), recomendaciones agronómicas críticas, automatizaciones.
- Definir política de minimización de datos enviada al LLM: solo métricas agregadas y contexto indispensable.
- Definir límites de consumo: timeout, rate limit por usuario/sesión, tamaño máximo de contexto.

2. Fase 1 - Arquitectura base de backend
- Crear router dedicado al asistente siguiendo separación por capas y dependencias de autenticación existentes.
- Crear servicio de orquestación de respuestas: clasificación de intención, recuperación de contexto de producto y agregados de usuario, composición de prompt seguro.
- Añadir cliente de proveedor LLM externo con adaptador desacoplado para permitir cambio de proveedor sin tocar router/servicio.
- Asegurar filtrado estricto por user_id en todas las consultas de contexto.
- Definir respuesta estructurada: texto, fuentes usadas, trazabilidad básica y metadatos de coste/latencia.

3. Fase 2 - Streaming y experiencia de chat
- Implementar endpoint de streaming con Server-Sent Events como opción recomendada para MVP web (menor complejidad operativa que WebSocket).
- Crear widget de chat global en layout base con apertura flotante y panel lateral/modal adaptable a móvil.
- Integrar historial corto de conversación por sesión y controles de UX: estado cargando, reintento, cancelación.
- Añadir mensajes de seguridad/alcance en la UI: qué puede y no puede hacer el asistente.

4. Fase 3 - Base de conocimiento de uso de la app
- Preparar corpus inicial desde documentación funcional existente (módulos, campañas, riego, reportes, import/export).
- Iniciar sin vector DB (contexto curado por secciones) para acelerar entrega.
- Diseñar estructura de crecimiento a RAG posterior (fuentes versionadas, chunking, trazabilidad de respuestas).

5. Fase 4 - Calidad, observabilidad y tests
- Tests unitarios del servicio de asistente para: clasificación, ensamblado de contexto, guardrails, fallback cuando falla proveedor.
- Tests de router para autenticación obligatoria, streaming correcto y errores controlados.
- Validaciones de seguridad: nunca exponer datos de otro usuario, truncado de PII en prompts, registro sin contenido sensible.
- Métricas mínimas: latencia, tasa de error, coste por 100 consultas, ratio de respuestas útiles.

6. Fase 5 - Evolución (post-MVP)
- Incorporar RAG real con índice vectorial si crece el contenido de ayuda.
- Añadir herramientas de consulta avanzadas con consultas analíticas predefinidas y resultados explicables.
- Evaluar WebSocket solo si se necesita bidireccionalidad avanzada o experiencias más complejas que SSE.
- Evaluar modo de acciones seguras con confirmación explícita del usuario (write operations) en fase separada.

**Opciones evaluadas (pros y cons)**
1. FAQ guiada sin LLM (rápida y barata)
- Pros: implementación muy rápida, coste casi nulo, riesgo bajo.
- Cons: pobre para preguntas abiertas, poca personalización con datos del usuario, experiencia menos natural.

2. API JSON + LLM sin streaming
- Pros: buena calidad de respuesta, implementación moderada, fácil de testear.
- Cons: UX menos fluida, percepción de latencia en respuestas largas.

3. API con streaming SSE + LLM (recomendada)
- Pros: UX moderna, complejidad razonable, buena compatibilidad con stack FastAPI/Jinja.
- Cons: mayor trabajo de frontend que opción 2, requiere control fino de errores y reconexión.

4. WebSocket + LLM streaming
- Pros: máxima interactividad en tiempo real.
- Cons: complejidad técnica y de pruebas superior para MVP, mayor carga operativa.

5. RAG completo con vector DB desde inicio
- Pros: respuestas más fundamentadas en conocimiento propio, mejor escalabilidad de contenido.
- Cons: sobrecoste inicial alto, más piezas a mantener, no ideal para primera iteración.

**Relevant files**
- /Users/javiergomez/Dev/Sandbox/truficultura/app/main.py — incluir nuevo router y cableado general.
- /Users/javiergomez/Dev/Sandbox/truficultura/app/auth.py — reutilizar dependencias de autenticación y sesión.
- /Users/javiergomez/Dev/Sandbox/truficultura/app/templates/base.html — punto ideal para inyectar widget global del chat.
- /Users/javiergomez/Dev/Sandbox/truficultura/app/services/ — capa para lógica de negocio del asistente y recuperación de contexto del usuario.
- /Users/javiergomez/Dev/Sandbox/truficultura/tests/ — cobertura de router y servicios del asistente siguiendo patrón actual de tests.
- /Users/javiergomez/Dev/Sandbox/truficultura/pyproject.toml — dependencias del proveedor LLM/cliente HTTP si son necesarias.

**Verification**
1. Verificar que una consulta de usuario A nunca retorna información de usuario B (pruebas de aislamiento por user_id).
2. Verificar comportamiento de streaming: inicio, chunks, finalización y cancelación sin bloquear UI.
3. Verificar degradación controlada cuando falla el proveedor externo (mensaje útil + sin traceback al usuario).
4. Verificar coste y latencia de muestra con preguntas frecuentes de uso real.
5. Ejecutar la suite completa de tests tras integrar la primera versión.

**Decisions**
- Incluido: asistente de consulta y explicación en español sobre uso + datos del usuario en modo lectura.
- Excluido en MVP: operaciones de escritura automáticas, multidioma, RAG completo desde día 1.
- Proveedor: externo permitido con minimización de datos.
- UX: chat con streaming requerido.

**Further Considerations**
1. Política de retención de conversaciones: recomendación inicial 30 días máximo o solo sesión para minimizar riesgo.
2. Nivel de detalle de respuestas sobre datos: recomendación inicial solo agregados por campaña/parcela y evitar enviar registros crudos al LLM.
3. Mecanismo de trazabilidad para confianza: mostrar siempre qué fuentes internas se usaron en la respuesta (módulo y periodo).