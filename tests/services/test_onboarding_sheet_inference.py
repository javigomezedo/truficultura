"""Tests for the sheet-name → metadata inference."""

from __future__ import annotations

import pytest

from app.services.onboarding.sheet_inference import (
    SheetMetadata,
    infer_sheet_metadata,
)


@pytest.mark.parametrize(
    ("sheet_name", "expected_plot", "expected_year", "expected_label"),
    [
        ("Ingresos CERRELLAR 25-26", "Cerrellar", 2025, "2025/26"),
        ("Ingresos Cerrellar 25-26", "Cerrellar", 2025, "2025/26"),
        ("INGRESOS CERRELLAR 20-21", "Cerrellar", 2020, "2020/21"),
        ("Gastos 2024-2025", None, 2024, "2024/25"),
        ("Gastos 2025", None, None, None),
        ("Gastos 25", None, None, None),
        ("Ventas Loma Alta 2023/2024", "Loma Alta", 2023, "2023/24"),
        ("Ingresos parcela_norte 22/23", "Parcela Norte", 2022, "2022/23"),
        ("RESUMEN", None, None, None),
        ("Hoja3", "Hoja3", None, None),  # noise filter doesn't strip "Hoja3" (digits attached)
        ("", None, None, None),
    ],
)
def test_infer_sheet_metadata(
    sheet_name: str,
    expected_plot: str | None,
    expected_year: int | None,
    expected_label: str | None,
) -> None:
    meta = infer_sheet_metadata(sheet_name)
    assert isinstance(meta, SheetMetadata)
    assert meta.sheet_name == sheet_name
    assert meta.plot_name == expected_plot
    assert meta.campaign_year_start == expected_year
    assert meta.campaign_label == expected_label


def test_infer_sheet_metadata_preserves_mixed_case() -> None:
    """When the input is mixed-case, the plot name is not re-cased."""
    meta = infer_sheet_metadata("Ingresos LaSerna 25-26")
    assert meta.plot_name == "LaSerna"
    assert meta.campaign_year_start == 2025
