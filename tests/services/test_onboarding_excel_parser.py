"""Unit tests for the onboarding Excel parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.onboarding.excel_parser import parse_excel, parse_workbook

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "onboarding"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_clean_parcelas() -> None:
    parsed = parse_excel(_read("parcelas_limpio.xlsx"))
    assert parsed.sheet_name == "Parcelas"
    assert parsed.header_row_index == 1
    assert parsed.headers[:4] == ["Nombre", "Fecha plantación", "Polígono", "Parcela"]
    assert parsed.total_data_rows == 3
    assert len(parsed.sample_rows) == 3
    # First row, first column
    assert parsed.sample_rows[0][0] == "Via Minera Javi"
    # Date should be ISO-serialised (JSON-safe)
    assert parsed.sample_rows[0][1].startswith("2019-11-01")


def test_parse_gastos_with_title_rows() -> None:
    parsed = parse_excel(_read("gastos_cabeceras_irregulares.xlsx"))
    # Header is on row 4, after title + blank + title rows
    assert parsed.header_row_index == 4
    assert parsed.headers == [
        "Fecha",
        "Descripción",
        "Proveedor",
        "Finca",
        "Importe (€)",
        "Categoría",
    ]
    assert parsed.total_data_rows == 4
    # Empty cell in 'Finca' must come back as None
    assert parsed.sample_rows[0][3] is None


def test_parse_ingresos_with_merged_title() -> None:
    parsed = parse_excel(_read("ingresos_celdas_fusionadas.xlsx"))
    # The merged title spans 5 columns on row 1 — heuristic must skip it and
    # find the real header on row 3.
    assert parsed.header_row_index == 3
    assert parsed.headers == ["Fecha", "Bancal", "Kg", "Calidad", "€/Kg"]
    assert parsed.total_data_rows == 4


def test_parse_invalid_bytes() -> None:
    with pytest.raises(ValueError):
        parse_excel(b"not an excel file")


def test_parse_real_world_two_tables_with_summary() -> None:
    """Two side-by-side campaigns + TOTAL/GASTOS/SUMA footer rows.

    The parser must (a) detect the real header on row 3 (not the banner on
    row 1), (b) dedupe duplicate column names, and (c) stop reading when it
    hits the ``TOTAL`` summary row so the GASTOS section below is ignored.
    """
    parsed = parse_excel(_read("ingresos_real_world.xlsx"))
    assert parsed.header_row_index == 3
    # Duplicate "Fecha" / "Tip" / "Kg" / "Precio" / "Factura" must be deduped.
    assert "Fecha" in parsed.headers
    assert "Fecha (2)" in parsed.headers
    assert "Precio (2)" in parsed.headers
    # Only the 4 real data rows — TOTAL/GASTOS/SUMA/SALDO must be excluded.
    assert parsed.total_data_rows == 4


def test_parse_workbook_multi_sheet_keeps_data_sheets_only() -> None:
    """Workbook with multiple Ingresos sheets + RESUMEN + Hoja3.

    ``parse_workbook`` must keep only the sheets where a tabular structure
    (>=3 columns, >=1 data row) was detected and discard summary / empty
    sheets.
    """
    wb = parse_workbook(_read("ingresos_multi_sheet.xlsx"))
    sheet_names = [s.sheet_name for s in wb.sheets]
    assert sheet_names == [
        "Ingresos CERRELLAR 25-26",
        "Ingresos CERRELLAR 24-25",
    ]
    first = wb.sheets[0]
    assert first.headers == ["Fecha", "Cliente", "Kg", "€/kg", "Importe"]
    assert first.total_data_rows == 2
    assert wb.sheets[1].total_data_rows == 3


def test_parse_workbook_invalid_bytes() -> None:
    with pytest.raises(ValueError):
        parse_workbook(b"not an excel file")
