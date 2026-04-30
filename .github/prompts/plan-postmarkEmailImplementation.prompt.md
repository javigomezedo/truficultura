## Plan: Migracion Email a Postmark

Adoptar Postmark como proveedor transaccional principal para Trufiq, manteniendo un despliegue por fases para minimizar riesgo: preparacion sin dominio, integracion tecnica en app, validacion en DEV, y cutover progresivo a STAGING/PROD cuando el dominio este verificado. Estrategia recomendada: separar correos de producto (Postmark) y operativos/humanos (buzones dedicados), con rollback sencillo durante la transicion.

**Steps**
1. Fase 1 - Preparacion funcional y operativa (sin dominio): definir direcciones objetivo (noreply, alerts, soporte, billing, security), alta de cuenta Postmark, servidor de envio para entorno DEV/sandbox, y politica de ownership (quien recibe alertas y quien administra proveedor).
2. Fase 1 - Alineacion tecnica: decidir implementacion Postmark via cliente HTTP async (recomendado para stack async actual) y acordar modo fallback durante migracion (dual config temporal: SMTP legado + Postmark; prioridad Postmark).
3. Fase 2 - Configuracion de aplicacion: ampliar settings para Postmark (API key, from address, flag configured), conservar compatibilidad temporal con variables SMTP hasta completar cutover. *depende on 2*
4. Fase 2 - Servicio de email: refactor del envio central para usar Postmark y mantener intactos los casos de uso existentes (confirmacion cuenta, reset password, lead notification). Agregar logging estructurado con resultado de entrega y errores (sin romper flujo de usuario). *depende on 3*
5. Fase 2 - Seguridad de contenido: sanitizar/escapar campos de entrada en correos de contacto para evitar inyeccion HTML en notificaciones internas. *parallel with step 4*
6. Fase 2 - Pruebas automatizadas: migrar tests de mocks SMTP a mocks Postmark, cubrir exito y fallo de API (incluyendo timeout/5xx), y asegurar que los flujos de auth y landing siguen verdes. *depende on 4*
7. Fase 2 - Config y documentacion: actualizar .env.example y README con variables y runbook de troubleshooting Postmark; documentar secretos requeridos por entorno en Fly y checklist de validacion. *parallel with step 6*
8. Fase 3 - Activacion en DEV: cargar secretos en trufiq-dev, desplegar, ejecutar smoke tests de envio real y validar trazabilidad en Postmark (delivered/bounced) para los tres flujos de email de app. *depende on 6 and 7*
9. Fase 3 - Alertas operativas: configurar canal alerts dedicado para Grafana/operacion (mismo dominio cuando exista) y fallback temporal a correo personal/equipo durante pre-dominio. *depends on 1*
10. Fase 4 - Cutover de dominio: cuando exista dominio, completar SPF/DKIM/DMARC, verificar sender en Postmark, mover from definitivo (noreply@trufiq.app), y activar STAGING/PROD con despliegue escalonado. *depende on 8 and 9*
11. Fase 4 - Endurecimiento post-cutover: activar monitorizacion de rebotes/complaints, definir politica de supresion, y retirar configuracion SMTP legado tras una ventana de estabilidad acordada. *depende on 10*

**Relevant files**
- /Users/javiergomez/Dev/Sandbox/truficultura/app/config.py — extender settings para Postmark y propiedad de configuracion activa.
- /Users/javiergomez/Dev/Sandbox/truficultura/app/services/email_service.py — punto unico de envio a migrar a Postmark.
- /Users/javiergomez/Dev/Sandbox/truficultura/app/routers/auth.py — validar integracion sin cambios de contrato en flujos de registro/reset.
- /Users/javiergomez/Dev/Sandbox/truficultura/app/main.py — validar ruta landing/contact que dispara notificacion por email.
- /Users/javiergomez/Dev/Sandbox/truficultura/tests/services/test_email_service.py — adaptar mocks/asserts a Postmark.
- /Users/javiergomez/Dev/Sandbox/truficultura/tests/test_auth_router.py — verificar flujos auth con nuevo backend de email.
- /Users/javiergomez/Dev/Sandbox/truficultura/tests/test_landing_contact.py — verificar envio de lead notification.
- /Users/javiergomez/Dev/Sandbox/truficultura/.env.example — nuevas variables y notas de uso.
- /Users/javiergomez/Dev/Sandbox/truficultura/README.md — documentacion de configuracion y troubleshooting.
- /Users/javiergomez/Dev/Sandbox/truficultura/monitoring/README.md — checklist operativo de alertas por email (si aplica al proceso del equipo).

**Verification**
1. Unit tests: ejecutar tests de email service, auth router y landing contact para validar contratos y manejo de errores.
2. Smoke test DEV: registro nuevo usuario (confirmacion), forgot password (reset), y POST landing/contact con respuesta OK y evidencia de entrega en Postmark.
3. Observabilidad: revisar logs de app y eventos de Postmark para confirmar IDs de mensaje, entregas y fallos.
4. Infra DEV: comprobar secretos cargados en trufiq-dev y ausencia de errores de configuracion al arrancar.
5. Post-cutover dominio: validar SPF, DKIM y DMARC en verificacion de proveedor y ejecutar envio end-to-end a una bandeja externa real.

**Decisions**
- Proveedor seleccionado: Postmark.
- Mantener prompts historicos con nombre anterior sin cambios (fuera de alcance).
- Mantener scripts legacy no criticos sin refactor (fuera de alcance en esta migracion).
- Implementacion recomendada: cliente HTTP async para mantener coherencia con stack FastAPI/SQLAlchemy async.
- Estrategia de riesgo: migracion por fases con fallback temporal y retirada de SMTP al final.

**Further Considerations**
1. Reintentos de envio: opcion A sin retry (simple), opcion B retry basico en errores transitorios, opcion C cola asyncrona dedicada.
2. Politica de rebotes: opcion A solo monitorizar, opcion B suprimir automatico para evitar reintentos a direcciones invalidas.
3. Uso de plantillas Postmark: opcion A mantener HTML inline inicialmente, opcion B mover a templates gestionadas por Postmark tras estabilizar cutover.
