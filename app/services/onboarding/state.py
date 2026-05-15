"""Graph state for the onboarding LangGraph workflow.

The state is a plain TypedDict so it can be JSON-serialised and stored in the
``onboarding_sessions.state_json`` column between HTTP requests.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

EntityType = Literal["parcelas", "gastos", "ingresos", "desconocido"]


class ColumnMappingEntry(TypedDict):
    """One row of the LLM-proposed mapping between a source column and a target field."""

    source_column: str
    target_field: str  # field id in entity_schemas, or "MISSING" / "IGNORE"
    confidence: float
    reason: NotRequired[str]
    transformation_hint: NotRequired[str]  # e.g. "date_dmy", "number_eu"


class AmbiguityEntry(TypedDict):
    """A column whose mapping the user must resolve manually."""

    source_column: str
    proposed_target: str
    confidence: float
    candidate_targets: list[str]
    reason: NotRequired[str]


class ValidationError(TypedDict):
    row_index: int
    column: NotRequired[str]
    message: str


class OnboardingState(TypedDict, total=False):
    """Full state of an onboarding session.

    All fields are optional (total=False) because the state grows as the
    LangGraph nodes execute.
    """

    session_id: int
    tenant_id: int

    # --- Fase 0: Excel parsing ---
    original_filename: str
    sheet_name: str
    headers: list[str]
    sample_rows: list[list[Any]]  # first N data rows, JSON-safe
    total_rows: int
    header_row_index: int  # 1-based row in the worksheet where headers live

    # When the workbook has multiple data sheets (one per campaign, plot, ...)
    # we keep a per-sheet summary here. ``sheet_name`` / ``headers`` still
    # point at the reference sheet (first one) used for the LLM mapping.
    parsed_sheets: list[dict[str, Any]]

    # --- Fase 1: LLM detection / mapping ---
    entity_type: EntityType
    entity_confidence: float
    proposed_mapping: list[ColumnMappingEntry]
    ambiguities: list[AmbiguityEntry]

    # --- Fase 2: human-in-the-loop ---
    resolved_mapping: dict[str, str]  # source_column -> target_field (or "IGNORE")

    # --- Fase 3: transformation / validation ---
    transformed_rows: list[dict[str, Any]]
    validation_errors: list[ValidationError]
    csv_output: str  # final CSV ready for import_service

    # --- Bookkeeping ---
    last_node: str
    error: str
