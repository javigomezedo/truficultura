# Plan: Migración a Azure OpenAI Service

## Objetivo

Sustituir las llamadas al API de OpenAI consumer por Azure OpenAI Service, garantizando que los datos de la finca (gastos, ingresos, parcelas) nunca salgan del entorno EU ni se usen para entrenamiento de modelos.

## Garantías de privacidad verificadas

Documentación oficial de Microsoft ([Data, privacy, and security for Azure Direct Models](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)):

- Prompts y respuestas **NO están disponibles para OpenAI** ni para otros proveedores.
- **NO se usan para entrenar** ningún modelo de IA generativa sin permiso explícito.
- Azure Direct Models **NO interactúa con ningún servicio operado por OpenAI** (ChatGPT, OpenAI API).
- Los modelos son stateless: ningún prompt ni respuesta se almacena en el modelo.

Matiz: abuse monitoring puede almacenar temporalmente prompts si se detecta un patrón abusivo. Personal de Microsoft en la UE puede acceder a ellos en ese caso. No es entrenamiento y se puede desactivar solicitándolo. Para una finca de trufas el riesgo es prácticamente inexistente.

## Contexto técnico relevante

- Adaptador actual: `OpenAIAdapter` en `app/services/llm_adapter.py`
- Ya existe clase abstracta `LLMAdapter` — diseñada explícitamente para el swap de proveedor
- El router instancia el adaptador en `_get_adapter()` en `app/routers/assistant.py`
- Se usa `httpx` raw, sin el SDK de OpenAI — fácil de adaptar
- El endpoint `/transcribe` (Whisper) se mantiene en OpenAI — no cambia

## Fase 1 — Infraestructura Azure (manual)

1. Crear recurso **Azure OpenAI Service** en región `francecentral` o `swedencentral` (UE, latencia ~0ms extra desde fly.io `cdg`)
2. Desplegar modelo `gpt-4o-mini` → dar nombre al deployment (ej. `trufiq-chat`)
3. Copiar:
   - Endpoint URL: `https://{nombre}.openai.azure.com/`
   - API key
   - Deployment name

## Fase 2 — Nuevo `AzureOpenAIAdapter`

Añadir clase `AzureOpenAIAdapter(LLMAdapter)` en `app/services/llm_adapter.py`:

- URL: `{AZURE_OPENAI_ENDPOINT}/openai/deployments/{DEPLOYMENT_NAME}/chat/completions?api-version=2024-05-01-preview`
- Header de auth: `api-key: {key}` (distinto de OpenAI que usa `Authorization: Bearer`)
- Payload idéntico: `messages`, `max_tokens`, `temperature`, `stream`
- Métodos `complete()` y `stream()` prácticamente idénticos a `OpenAIAdapter`

## Fase 3 — Configuración

En `app/config.py`, añadir tres variables opcionales:

```python
AZURE_OPENAI_API_KEY: str | None = None
AZURE_OPENAI_ENDPOINT: str | None = None  # ej. https://trufiq.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT: str | None = None  # ej. trufiq-chat
```

En `app/routers/assistant.py`, actualizar `_get_adapter()`:

- Si `AZURE_OPENAI_API_KEY` está configurado → devuelve `AzureOpenAIAdapter`
- Si no → comportamiento actual con `OPENAI_API_KEY` (fallback limpio)
- El endpoint `/transcribe` sigue usando `OPENAI_API_KEY` sin cambios

Actualizar `.env.example` con las tres nuevas variables y comentarios.

## Fase 4 — Tests

En `tests/test_assistant_router.py`:

- Test `_get_adapter()` con `AZURE_OPENAI_API_KEY` configurado → devuelve `AzureOpenAIAdapter`
- Test sin ninguna clave → 503
- Los tests existentes del contrato `AssistantRequest`/`AssistantResponse` no cambian

## Archivos a modificar

| Archivo | Cambio |
|---|---|
| `app/services/llm_adapter.py` | Añadir `AzureOpenAIAdapter` (~40 líneas) |
| `app/config.py` | 3 nuevas variables opcionales |
| `app/routers/assistant.py` | Actualizar `_get_adapter()` (~10 líneas) |
| `.env.example` | Documentar nuevas variables |
| `tests/test_assistant_router.py` | 2-3 tests nuevos |

## Verificación

1. `pytest` — suite completa en verde
2. Con variables Azure en `.env`, hacer consulta real desde la UI → respuesta coherente
3. Verificar en Azure Portal que el deployment recibe peticiones (métricas de tokens)
4. Comprobar que no hay tráfico a `api.openai.com` durante el chat (solo Whisper si se usa)

## Decisiones de diseño

- **Fallback**: sin `AZURE_OPENAI_API_KEY` en `.env`, el sistema vuelve a OpenAI sin fricción
- **Whisper**: se mantiene en OpenAI — `OPENAI_API_KEY` solo necesario si se usa transcripción de voz
- **Precio**: mismo coste por token que OpenAI directo, sin recargo por Azure
- **GDPR**: región EU garantiza que los datos nunca salen de la UE
