"""LangGraph nodes that call an LLM to detect entity type and propose a
column mapping.

The graph is intentionally tiny:

    detect_entity ─► propose_mapping ─► (END / awaiting_user)

Both nodes use ``ChatOpenAI`` with structured output so we never have to parse
free-form JSON. Sample rows are anonymised before leaving the server.

The factory ``build_llm()`` is the single entry point that creates the LLM —
tests inject a stub via ``llm_factory`` parameters on the node functions.
"""

from __future__ import annotations

from typing import Callable, Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.services.onboarding.entity_schemas import ENTITY_SCHEMAS, get_schema
from app.services.onboarding.privacy import anonymize_sample
from app.services.onboarding.state import (
    AmbiguityEntry,
    ColumnMappingEntry,
    OnboardingState,
)

# ---------------------------------------------------------------------------
# Pydantic schemas for structured output
# ---------------------------------------------------------------------------

EntityLiteral = Literal["parcelas", "gastos", "ingresos", "desconocido"]


class EntityDetection(BaseModel):
    """LLM verdict about which Trufiq entity the sheet most likely represents."""

    entity_type: EntityLiteral = Field(
        description=(
            "El tipo de entidad detectado: 'parcelas' (datos catastrales y "
            "geográficos de fincas), 'gastos' (costes con fecha + importe), "
            "'ingresos' (ventas con fecha + kg + €/kg) o 'desconocido' si "
            "no encaja con ninguno."
        )
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confianza entre 0 y 1.")
    reason: str = Field(
        description="Una frase corta en español explicando la decisión.",
        max_length=400,
    )


class MappingItem(BaseModel):
    source_column: str = Field(description="Nombre exacto de la columna en el Excel.")
    target_field: str = Field(
        description=(
            "Identificador del campo destino del esquema Trufiq, o "
            "'IGNORE' si la columna no se debe importar."
        )
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=240)
    transformation_hint: str = Field(
        default="",
        description=(
            "Pista opcional de transformación: 'date_dmy', 'date_iso', "
            "'number_eu' (1.234,56), 'number_us' (1,234.56), 'trim', etc."
        ),
        max_length=80,
    )


class ColumnMappingProposal(BaseModel):
    items: list[MappingItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

LLMFactory = Callable[[], object]
"""Callable returning a LangChain chat model (typed loosely for testability)."""


def build_llm() -> object:
    """Construct the default chat model used by onboarding nodes.

    Returns ``langchain_openai.ChatOpenAI`` configured with the project's
    OpenAI key. Tests should pass their own factory instead of calling this.
    """
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY no está configurado; el agente de onboarding "
            "requiere un proveedor LLM."
        )
    # Imported lazily so the project still boots without langchain installed
    # in unusual environments (e.g. tooling-only checks).
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model="gpt-4o-mini",
        temperature=0.0,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def _entity_catalog() -> str:
    lines = []
    for schema in ENTITY_SCHEMAS.values():
        required = ", ".join(schema.required_field_ids())
        lines.append(
            f"- {schema.id}: {schema.description_es} Campos obligatorios: {required}."
        )
    return "\n".join(lines)


_DETECT_SYSTEM = (
    "Eres un asistente experto en datos agrícolas para Trufiq, una aplicación "
    "de gestión de truficultura. Recibirás las cabeceras y unas pocas filas "
    "de muestra (anonimizadas) de una hoja Excel y debes decidir a qué tipo "
    "de entidad de Trufiq corresponde:\n"
    "{catalog}\n"
    "Si los datos no encajan con ninguna o son ambiguos, responde "
    "'desconocido' con baja confianza."
)


def _build_detect_messages(
    headers: list[str], anon_sample: list[list[str]]
) -> list[dict]:
    headers_line = " | ".join(headers)
    sample_lines = "\n".join(" | ".join(row) for row in anon_sample[:5])
    return [
        {
            "role": "system",
            "content": _DETECT_SYSTEM.format(catalog=_entity_catalog()),
        },
        {
            "role": "user",
            "content": (
                f"Cabeceras: {headers_line}\n\n"
                f"Muestra (tipos de datos):\n{sample_lines}"
            ),
        },
    ]


_MAPPING_SYSTEM = (
    "Eres un asistente que mapea columnas de un Excel del usuario a los "
    "campos del esquema Trufiq de la entidad '{entity}'. Para cada columna "
    "del Excel decide a qué campo destino corresponde, o usa 'IGNORE' si no "
    "debe importarse. No inventes campos que no aparezcan en el catálogo."
)


def _schema_catalog(entity_type: str) -> str:
    schema = get_schema(entity_type)
    if not schema:
        return ""
    lines = []
    for f in schema.fields:
        req = " (obligatorio)" if f.required else ""
        aliases = f", alias: {', '.join(f.aliases)}" if f.aliases else ""
        lines.append(
            f"- {f.id}: {f.label_es} [{f.type}]{req}. {f.description}{aliases}"
        )
    return "\n".join(lines)


def _build_mapping_messages(
    entity_type: str, headers: list[str], anon_sample: list[list[str]]
) -> list[dict]:
    headers_line = " | ".join(headers)
    sample_lines = "\n".join(" | ".join(row) for row in anon_sample[:5])
    return [
        {
            "role": "system",
            "content": _MAPPING_SYSTEM.format(entity=entity_type)
            + "\n\nCatálogo de campos destino:\n"
            + _schema_catalog(entity_type),
        },
        {
            "role": "user",
            "content": (
                f"Cabeceras del Excel: {headers_line}\n\n"
                f"Muestra (tipos):\n{sample_lines}\n\n"
                "Devuelve un mapeo para CADA cabecera, exactamente una vez."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

_AMBIGUITY_THRESHOLD = 0.7


def detect_entity_node(
    state: OnboardingState,
    *,
    llm_factory: LLMFactory = build_llm,
) -> OnboardingState:
    """Decide which Trufiq entity the uploaded sheet represents."""
    headers = list(state.get("headers") or [])
    sample = list(state.get("sample_rows") or [])
    if not headers:
        return {
            **state,
            "entity_type": "desconocido",
            "entity_confidence": 0.0,
            "last_node": "detect_entity",
            "error": "El fichero no tiene cabeceras detectables.",
        }

    anon = anonymize_sample(sample)
    llm = llm_factory()
    structured = llm.with_structured_output(EntityDetection)  # type: ignore[attr-defined]
    result: EntityDetection = structured.invoke(_build_detect_messages(headers, anon))

    return {
        **state,
        "entity_type": result.entity_type,
        "entity_confidence": float(result.confidence),
        "last_node": "detect_entity",
    }


def propose_mapping_node(
    state: OnboardingState,
    *,
    llm_factory: LLMFactory = build_llm,
) -> OnboardingState:
    """Ask the LLM to map each Excel column to a target schema field."""
    entity_type = state.get("entity_type") or "desconocido"
    if entity_type == "desconocido":
        return {**state, "last_node": "propose_mapping"}

    schema = get_schema(entity_type)
    if not schema:
        return {**state, "last_node": "propose_mapping"}

    headers = list(state.get("headers") or [])
    sample = list(state.get("sample_rows") or [])
    anon = anonymize_sample(sample)
    valid_targets = set(schema.field_ids()) | {"IGNORE"}

    llm = llm_factory()
    structured = llm.with_structured_output(ColumnMappingProposal)  # type: ignore[attr-defined]
    result: ColumnMappingProposal = structured.invoke(
        _build_mapping_messages(entity_type, headers, anon)
    )

    proposed: list[ColumnMappingEntry] = []
    ambiguities: list[AmbiguityEntry] = []
    seen_headers: set[str] = set()

    for item in result.items:
        if item.source_column not in headers:
            continue
        seen_headers.add(item.source_column)
        target = item.target_field if item.target_field in valid_targets else "IGNORE"
        entry: ColumnMappingEntry = {
            "source_column": item.source_column,
            "target_field": target,
            "confidence": float(item.confidence),
        }
        if item.reason:
            entry["reason"] = item.reason
        if item.transformation_hint:
            entry["transformation_hint"] = item.transformation_hint
        proposed.append(entry)

        if item.confidence < _AMBIGUITY_THRESHOLD or target == "IGNORE":
            ambiguities.append(
                {
                    "source_column": item.source_column,
                    "proposed_target": target,
                    "confidence": float(item.confidence),
                    "candidate_targets": list(schema.field_ids()),
                    **({"reason": item.reason} if item.reason else {}),
                }
            )

    # Any header the LLM forgot becomes an ambiguity to resolve manually.
    for header in headers:
        if header not in seen_headers:
            proposed.append(
                {
                    "source_column": header,
                    "target_field": "IGNORE",
                    "confidence": 0.0,
                }
            )
            ambiguities.append(
                {
                    "source_column": header,
                    "proposed_target": "IGNORE",
                    "confidence": 0.0,
                    "candidate_targets": list(schema.field_ids()),
                }
            )

    return {
        **state,
        "proposed_mapping": proposed,
        "ambiguities": ambiguities,
        "last_node": "propose_mapping",
    }
