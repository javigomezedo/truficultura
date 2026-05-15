"""Tests for the onboarding LLM nodes and LangGraph agent.

The LLM is stubbed out — these tests verify the orchestration logic, the
ambiguity threshold, the validation against the entity schema, and the
defensive behaviour when columns are missing or unknown.
"""

from __future__ import annotations

from app.services.onboarding.agent import build_graph
from app.services.onboarding.llm_nodes import (
    ColumnMappingProposal,
    EntityDetection,
    MappingItem,
    detect_entity_node,
    propose_mapping_node,
)


# ---------------------------------------------------------------------------
# Stub LLM machinery
# ---------------------------------------------------------------------------


class _StubStructured:
    def __init__(self, response):
        self._response = response

    def invoke(self, _messages):
        return self._response


class _StubLLM:
    """Minimal stand-in for ``ChatOpenAI`` used in tests."""

    def __init__(self, responses):
        # Map BaseModel class -> response instance.
        self._responses = responses
        self.calls: list = []

    def with_structured_output(self, schema_cls):
        self.calls.append(schema_cls.__name__)
        return _StubStructured(self._responses[schema_cls.__name__])


def _make_factory(responses):
    instance = _StubLLM(responses)

    def _factory():
        return instance

    return _factory, instance


# ---------------------------------------------------------------------------
# detect_entity_node
# ---------------------------------------------------------------------------


def test_detect_entity_returns_entity_and_confidence() -> None:
    factory, _ = _make_factory(
        {
            "EntityDetection": EntityDetection(
                entity_type="gastos", confidence=0.9, reason="Tiene fecha e importe."
            )
        }
    )
    state = {
        "headers": ["Fecha", "Concepto", "Importe"],
        "sample_rows": [["2025-01-01", "Pienso", 21.0]],
    }
    out = detect_entity_node(state, llm_factory=factory)
    assert out["entity_type"] == "gastos"
    assert out["entity_confidence"] == 0.9
    assert out["last_node"] == "detect_entity"


def test_detect_entity_handles_missing_headers() -> None:
    factory, instance = _make_factory({})
    out = detect_entity_node({"headers": []}, llm_factory=factory)
    assert out["entity_type"] == "desconocido"
    assert out["entity_confidence"] == 0.0
    assert "error" in out
    # LLM must not be called
    assert instance.calls == []


# ---------------------------------------------------------------------------
# propose_mapping_node
# ---------------------------------------------------------------------------


def test_propose_mapping_validates_targets_and_flags_low_confidence() -> None:
    factory, _ = _make_factory(
        {
            "ColumnMappingProposal": ColumnMappingProposal(
                items=[
                    MappingItem(
                        source_column="Fecha", target_field="fecha", confidence=0.95
                    ),
                    MappingItem(
                        source_column="Concepto",
                        target_field="concepto",
                        confidence=0.6,
                    ),
                    MappingItem(
                        source_column="Importe",
                        target_field="cantidad",
                        confidence=0.99,
                    ),
                    # Invalid target -> coerced to IGNORE
                    MappingItem(
                        source_column="Notas",
                        target_field="campo_inexistente",
                        confidence=0.4,
                    ),
                ]
            )
        }
    )
    state = {
        "entity_type": "gastos",
        "headers": ["Fecha", "Concepto", "Importe", "Notas"],
        "sample_rows": [],
    }
    out = propose_mapping_node(state, llm_factory=factory)
    mapping = {m["source_column"]: m for m in out["proposed_mapping"]}
    assert mapping["Fecha"]["target_field"] == "fecha"
    assert mapping["Concepto"]["target_field"] == "concepto"
    assert mapping["Importe"]["target_field"] == "cantidad"
    assert mapping["Notas"]["target_field"] == "IGNORE"

    ambiguous_cols = {a["source_column"] for a in out["ambiguities"]}
    # Concepto (low conf) and Notas (IGNORE) must be flagged
    assert "Concepto" in ambiguous_cols
    assert "Notas" in ambiguous_cols
    # High confidence proper mappings must NOT be flagged
    assert "Fecha" not in ambiguous_cols
    assert "Importe" not in ambiguous_cols


def test_propose_mapping_fills_in_missing_headers() -> None:
    factory, _ = _make_factory(
        {
            "ColumnMappingProposal": ColumnMappingProposal(
                items=[
                    MappingItem(
                        source_column="Fecha", target_field="fecha", confidence=0.9
                    ),
                    # The LLM forgot about "Concepto" and "Importe"
                ]
            )
        }
    )
    state = {
        "entity_type": "gastos",
        "headers": ["Fecha", "Concepto", "Importe"],
        "sample_rows": [],
    }
    out = propose_mapping_node(state, llm_factory=factory)
    sources = [m["source_column"] for m in out["proposed_mapping"]]
    assert sources == ["Fecha", "Concepto", "Importe"]
    # Forgotten columns end up as IGNORE + ambiguous
    forgotten = {a["source_column"] for a in out["ambiguities"]}
    assert "Concepto" in forgotten
    assert "Importe" in forgotten


def test_propose_mapping_skips_when_entity_unknown() -> None:
    factory, instance = _make_factory({})
    state = {"entity_type": "desconocido", "headers": ["A"], "sample_rows": []}
    out = propose_mapping_node(state, llm_factory=factory)
    assert "proposed_mapping" not in out
    assert instance.calls == []


# ---------------------------------------------------------------------------
# Full graph (stubbed)
# ---------------------------------------------------------------------------


def test_build_graph_runs_both_nodes_with_stub_llm() -> None:
    factory, _ = _make_factory(
        {
            "EntityDetection": EntityDetection(
                entity_type="ingresos", confidence=0.92, reason="Kg + €/Kg"
            ),
            "ColumnMappingProposal": ColumnMappingProposal(
                items=[
                    MappingItem(
                        source_column="Fecha", target_field="fecha", confidence=0.95
                    ),
                    MappingItem(
                        source_column="Bancal", target_field="bancal", confidence=0.9
                    ),
                    MappingItem(source_column="Kg", target_field="kg", confidence=0.95),
                    MappingItem(
                        source_column="€/Kg", target_field="euros_kg", confidence=0.93
                    ),
                ]
            ),
        }
    )
    run = build_graph(llm_factory=factory)
    out = run(
        {
            "headers": ["Fecha", "Bancal", "Kg", "€/Kg"],
            "sample_rows": [["2026-01-14", "Via Minera", 1.25, 320.0]],
        }
    )
    assert out["entity_type"] == "ingresos"
    assert len(out["proposed_mapping"]) == 4
    # All high confidence -> no ambiguities
    assert out["ambiguities"] == []


def test_build_graph_preserves_header_row_index() -> None:
    """Regression: `header_row_index` must survive LangGraph state filtering.

    The transformer relies on this value to skip header/banner rows in the
    worksheet; if it gets stripped it falls back to 1 and the header row is
    treated as data, producing "No se pudo convertir 'Fecha' a date" errors.
    """
    factory, _ = _make_factory(
        {
            "EntityDetection": EntityDetection(
                entity_type="ingresos", confidence=0.9, reason="ok"
            ),
            "ColumnMappingProposal": ColumnMappingProposal(items=[]),
        }
    )
    run = build_graph(llm_factory=factory)
    out = run(
        {
            "headers": ["Fecha", "Bancal", "Kg", "€/Kg"],
            "sample_rows": [],
            "header_row_index": 3,
            "parsed_sheets": [
                {
                    "sheet_name": "Ventas",
                    "header_row_index": 3,
                    "headers": ["Fecha", "Bancal", "Kg", "€/Kg"],
                }
            ],
        }
    )
    assert out["header_row_index"] == 3
    assert out["parsed_sheets"][0]["header_row_index"] == 3
