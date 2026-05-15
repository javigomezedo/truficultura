"""Tests for the onboarding transformer (Fase 3)."""

from __future__ import annotations

from pathlib import Path

from app.services.onboarding.transformer import transform_to_csv

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "onboarding"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_transform_gastos_emits_expected_csv() -> None:
    content = _read("gastos_cabeceras_irregulares.xlsx")
    csv_text, errors = transform_to_csv(
        content=content,
        sheet_name="Gastos 2025",
        headers=[
            "Fecha",
            "Descripción",
            "Proveedor",
            "Finca",
            "Importe (€)",
            "Categoría",
        ],
        header_row_index=4,
        entity_type="gastos",
        resolved_mapping=[
            {"source_column": "Fecha", "target_field": "fecha"},
            {"source_column": "Descripción", "target_field": "concepto"},
            {"source_column": "Proveedor", "target_field": "persona"},
            {"source_column": "Finca", "target_field": "bancal"},
            {"source_column": "Importe (€)", "target_field": "cantidad"},
            {"source_column": "Categoría", "target_field": "categoria"},
        ],
    )
    assert errors == []
    lines = [ln for ln in csv_text.strip().split("\n") if ln]
    assert len(lines) == 4
    # Format: fecha;concepto;persona;bancal;cantidad;categoria;<grupo_prorrateo blank>
    first = lines[0].split(";")
    assert first[0] == "14/11/2025"
    assert first[1] == "Pienso perros"
    assert first[2] == "Cooperativa"
    assert first[3] == ""
    assert first[4] == "21"
    assert first[5] == "Perros"
    # grupo_prorrateo column appended (empty)
    assert first[6] == ""


def test_transform_skips_rows_missing_required_fields() -> None:
    # Build a tiny in-memory xlsx with one row missing the date.
    from openpyxl import Workbook
    from io import BytesIO

    wb = Workbook()
    ws = wb.active
    ws.append(["Fecha", "Concepto", "Importe"])
    ws.append([None, "Sin fecha", 10])
    ws.append(["2025-01-15", "Con fecha", 20])
    buf = BytesIO()
    wb.save(buf)

    csv_text, errors = transform_to_csv(
        content=buf.getvalue(),
        sheet_name=None,
        headers=["Fecha", "Concepto", "Importe"],
        header_row_index=1,
        entity_type="gastos",
        resolved_mapping=[
            {"source_column": "Fecha", "target_field": "fecha"},
            {"source_column": "Concepto", "target_field": "concepto"},
            {"source_column": "Importe", "target_field": "cantidad"},
        ],
    )
    lines = [ln for ln in csv_text.strip().split("\n") if ln]
    assert len(lines) == 1  # only the valid row survived
    assert "Con fecha" in lines[0]
    assert len(errors) == 1
    assert errors[0]["column"] == "fecha"


def test_transform_ingresos_handles_eu_numbers() -> None:
    content = _read("ingresos_celdas_fusionadas.xlsx")
    csv_text, errors = transform_to_csv(
        content=content,
        sheet_name="Ventas",
        headers=["Fecha", "Bancal", "Kg", "Calidad", "€/Kg"],
        header_row_index=3,
        entity_type="ingresos",
        resolved_mapping=[
            {"source_column": "Fecha", "target_field": "fecha"},
            {"source_column": "Bancal", "target_field": "bancal"},
            {"source_column": "Kg", "target_field": "kg"},
            {"source_column": "Calidad", "target_field": "categoria"},
            {"source_column": "€/Kg", "target_field": "euros_kg"},
        ],
    )
    assert errors == []
    lines = [ln for ln in csv_text.strip().split("\n") if ln]
    assert len(lines) == 4
    # Format: fecha;bancal;kg;categoria;euros_kg
    fields = lines[0].split(";")
    assert fields[0] == "13/11/2025"
    assert fields[1] == "Santa Cruz Mar"
    assert fields[2] == "0,9"
    assert fields[4] == "45"


def test_transform_uses_constants_when_column_unmapped() -> None:
    """``constants`` should fill in target fields with no source column.

    Mirrors the multi-sheet workflow where ``bancal`` is derived from the
    sheet name instead of an Excel column.
    """
    content = _read("ingresos_multi_sheet.xlsx")
    csv_text, errors = transform_to_csv(
        content=content,
        sheet_name="Ingresos CERRELLAR 25-26",
        headers=["Fecha", "Cliente", "Kg", "€/kg", "Importe"],
        header_row_index=1,
        entity_type="ingresos",
        resolved_mapping=[
            {"source_column": "Fecha", "target_field": "fecha"},
            {"source_column": "Kg", "target_field": "kg"},
            {"source_column": "€/kg", "target_field": "euros_kg"},
        ],
        constants={"bancal": "Cerrellar"},
    )
    assert errors == []
    lines = [ln for ln in csv_text.strip().split("\n") if ln]
    assert len(lines) == 2
    for line in lines:
        fields = line.split(";")
        assert fields[1] == "Cerrellar"
