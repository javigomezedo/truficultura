from __future__ import annotations

import datetime
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.i18n import set_locale
from app.models.expense import Expense
from app.models.income import Income
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.truffle_event import TruffleEvent
from app.models.well import Well
from app.services.import_service import (
    import_all_csv_zip,
    import_expenses_csv,
    import_incomes_csv,
    import_irrigation_csv,
    import_plot_events_csv,
    import_plots_csv,
    import_truffles_csv,
    import_wells_csv,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plot(id=1, name="Bancal Sur", has_irrigation=True):
    return Plot(
        id=id,
        user_id=1,
        name=name,
        planting_date=datetime.date(2020, 3, 15),
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=100,
        area_ha=None,
        production_start=None,
        percentage=100.0,
        has_irrigation=has_irrigation,
    )


def _make_plant(id=1, plot_id=1, label="A1"):
    return Plant(
        id=id,
        user_id=1,
        plot_id=plot_id,
        label=label,
        row_label="A",
        row_order=0,
        col_order=0,
        visual_col=1,
    )


def _plots_csv(rows: list[str]) -> bytes:
    return "\n".join(rows).encode("utf-8")


def _irrigation_csv(rows: list[str]) -> bytes:
    return "\n".join(rows).encode("utf-8")


def _wells_csv(rows: list[str]) -> bytes:
    return "\n".join(rows).encode("utf-8")


def _expenses_csv(rows: list[str]) -> bytes:
    return "\n".join(rows).encode("utf-8")


def _incomes_csv(rows: list[str]) -> bytes:
    return "\n".join(rows).encode("utf-8")


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# import_expenses_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_expenses_csv_success_with_plot():
    plot = _make_plot(id=7, name="Bancal Sur")
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    content = _expenses_csv(["15/11/2025;Poda;Javi;Bancal Sur;1.250,00;Poda"])
    rows, warnings = await import_expenses_csv(db, content, user_id=1)

    assert warnings == []
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, Expense)
    assert row.plot_id == 7
    assert row.amount == pytest.approx(1250.0)
    assert row.category == "Poda"


@pytest.mark.asyncio
async def test_import_expenses_csv_unknown_plot_warns_and_imports_general():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    content = _expenses_csv(["15/11/2025;Poda;Javi;No Existe;10,00;Poda"])
    rows, warnings = await import_expenses_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].plot_id is None
    assert len(warnings) == 1
    assert "No Existe" in warnings[0]


@pytest.mark.asyncio
async def test_import_expenses_csv_too_few_columns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    rows, warnings = await import_expenses_csv(
        db, _expenses_csv(["15/11/2025;Poda"]), user_id=1
    )

    assert rows == []
    assert len(warnings) == 1
    assert "se esperaban 5 columnas" in warnings[0]


@pytest.mark.asyncio
async def test_import_expenses_csv_parse_error_warns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    rows, warnings = await import_expenses_csv(
        db,
        _expenses_csv(["fecha-mal;Poda;Javi;;10,00;Poda"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "error al parsear" in warnings[0]


@pytest.mark.asyncio
async def test_import_expenses_csv_warning_is_translated_in_english():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    set_locale("en")
    try:
        rows, warnings = await import_expenses_csv(
            db, _expenses_csv(["15/11/2025;Poda"]), user_id=1
        )
    finally:
        set_locale("es")

    assert rows == []
    assert warnings == ["Line 1: expected 5 columns, found 2 — skipped"]


# ---------------------------------------------------------------------------
# import_incomes_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_incomes_csv_success_with_plot():
    plot = _make_plot(id=8, name="Bancal Norte")
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    rows, warnings = await import_incomes_csv(
        db,
        _incomes_csv(["05/12/2025;Bancal Norte;2,500;Extra;120,00"]),
        user_id=1,
    )

    assert warnings == []
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, Income)
    assert row.plot_id == 8
    assert row.amount_kg == pytest.approx(2.5)
    assert row.euros_per_kg == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_import_incomes_csv_unknown_plot_warns_and_imports_without_plot():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    rows, warnings = await import_incomes_csv(
        db,
        _incomes_csv(["05/12/2025;Desconocido;2,500;Extra;120,00"]),
        user_id=1,
    )

    assert len(rows) == 1
    assert rows[0].plot_id is None
    assert len(warnings) == 1
    assert "Desconocido" in warnings[0]


@pytest.mark.asyncio
async def test_import_incomes_csv_too_few_columns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    rows, warnings = await import_incomes_csv(
        db, _incomes_csv(["05/12/2025;SoloDos"]), user_id=1
    )

    assert rows == []
    assert len(warnings) == 1
    assert "se esperaban 5 columnas" in warnings[0]


@pytest.mark.asyncio
async def test_import_incomes_csv_parse_error_warns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    rows, warnings = await import_incomes_csv(
        db,
        _incomes_csv(["fecha-mal;;2,500;Extra;120,00"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "error al parsear" in warnings[0]


# ---------------------------------------------------------------------------
# import_plots_csv — has_irrigation column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_plots_csv_has_irrigation_true():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    # has_irrigation=True (column 11 = "1"), mock _recalculate_percentages
    content = _plots_csv(["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;1"])

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].has_irrigation is True
    assert warnings == []


@pytest.mark.asyncio
async def test_import_plots_csv_has_irrigation_false():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    content = _plots_csv(["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;0"])

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert rows[0].has_irrigation is False


@pytest.mark.asyncio
async def test_import_plots_csv_has_irrigation_missing():
    """Old 10-column CSV without tiene_riego → has_irrigation defaults to False."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    content = _plots_csv(["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023"])

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert rows[0].has_irrigation is False
    assert warnings == []


@pytest.mark.asyncio
async def test_import_plots_csv_too_few_columns_warns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(
            db, _plots_csv(["SoloNombre"]), user_id=1
        )

    assert rows == []
    assert len(warnings) == 1
    assert "al menos 2 columnas" in warnings[0]


@pytest.mark.asyncio
async def test_import_plots_csv_parse_error_warns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(
            db,
            _plots_csv(["Bancal Sur;fecha-mal;;;;;;;;"]),
            user_id=1,
        )

    assert rows == []
    assert len(warnings) == 1
    assert "error al parsear" in warnings[0]


@pytest.mark.asyncio
async def test_import_plots_csv_with_map_config_calls_configure_map():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    from unittest.mock import AsyncMock as AM, patch

    mock_configure = AM(return_value=[])
    with (
        patch(
            "app.services.plants_service.configure_plot_map",
            new=mock_configure,
        ),
        patch(
            "app.services.plots_service._recalculate_percentages",
            new=AM(return_value=None),
        ),
    ):
        rows, warnings = await import_plots_csv(
            db,
            _plots_csv(
                ["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;1;A:1-2; B:3"]
            ),
            user_id=1,
        )

    assert len(rows) == 1
    assert warnings == []
    mock_configure.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_plots_csv_with_recinto_and_caudal_riego():
    """Columns 12 and 13 are recinto and caudal_riego."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    # nombre;fecha;pol;par;ref;hidrante;sector;plantas;ha;inicio;riego;mapa;recinto;caudal
    content = _plots_csv(["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;0;;3;7,50"])

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].recinto == "3"
    assert rows[0].caudal_riego == pytest.approx(7.5)
    assert warnings == []


@pytest.mark.asyncio
async def test_import_plots_csv_recinto_caudal_backwards_compat():
    """Old CSV with 11 columns (no recinto/caudal_riego) → defaults applied."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    content = _plots_csv(["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;0"])

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].recinto == "1"  # default
    assert rows[0].caudal_riego is None  # default
    assert warnings == []


@pytest.mark.asyncio
async def test_import_plots_csv_with_provincia_municipio():
    """Columns 14 and 15 are provincia_cod and municipio_cod."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    # nombre;fecha;pol;par;ref;hidrante;sector;plantas;ha;inicio;riego;mapa;recinto;caudal;prov;mun
    content = _plots_csv(
        ["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;0;;1;;44;223"]
    )

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].provincia_cod == "44"
    assert rows[0].municipio_cod == "223"
    assert warnings == []


@pytest.mark.asyncio
async def test_import_plots_csv_provincia_municipio_backwards_compat():
    """Old CSV without provincia/municipio columns → both default to None."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    content = _plots_csv(["Bancal Sur;01/01/2020;20;100;;;S1;50;;01/01/2023;0"])

    from unittest.mock import patch, AsyncMock as AM

    with patch(
        "app.services.plots_service._recalculate_percentages",
        new=AM(return_value=None),
    ):
        rows, warnings = await import_plots_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].provincia_cod is None
    assert rows[0].municipio_cod is None
    assert warnings == []
    plot = _make_plot(id=1, name="Bancal Sur", has_irrigation=True)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;Bancal Sur;10,500;Primera pasada"])
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert warnings == []
    r = rows[0]
    assert r.plot_id == 1
    assert r.water_m3 == pytest.approx(10.5)
    assert r.notes == "Primera pasada"
    assert r.expense_id is None
    assert r.date == datetime.date(2025, 6, 15)


@pytest.mark.asyncio
async def test_import_irrigation_csv_missing_notas():
    plot = _make_plot(id=1, name="Bancal Sur", has_irrigation=True)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;Bancal Sur;5,000"])
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert rows[0].notes is None
    assert warnings == []


@pytest.mark.asyncio
async def test_import_irrigation_csv_plot_not_found():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))  # no plots
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;Parcela Inexistente;5,000"])
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert rows == []
    assert len(warnings) == 1
    assert "Parcela Inexistente" in warnings[0]
    assert "no encontrado" in warnings[0]


@pytest.mark.asyncio
async def test_import_irrigation_csv_plot_no_irrigation():
    plot = _make_plot(id=1, name="Bancal Seco", has_irrigation=False)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;Bancal Seco;5,000"])
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert rows == []
    assert len(warnings) == 1
    assert "no tiene riego habilitado" in warnings[0]


@pytest.mark.asyncio
async def test_import_irrigation_csv_empty_bancal_skipped():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;;5,000"])
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert rows == []
    assert len(warnings) == 1
    assert "bancal vacío" in warnings[0]


@pytest.mark.asyncio
async def test_import_irrigation_csv_too_few_columns():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;Bancal Sur"])  # only 2 cols
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert rows == []
    assert len(warnings) == 1
    assert "omitida" in warnings[0]


@pytest.mark.asyncio
async def test_import_irrigation_csv_case_insensitive_bancal():
    plot = _make_plot(id=1, name="Bancal Sur", has_irrigation=True)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    content = _irrigation_csv(["15/06/2025;BANCAL SUR;3,000"])
    rows, warnings = await import_irrigation_csv(db, content, user_id=1)

    assert len(rows) == 1
    assert warnings == []


@pytest.mark.asyncio
async def test_import_wells_csv_parse_error_warns():
    plot = _make_plot(id=1, name="Bancal Sur")
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add_all = MagicMock()

    rows, warnings = await import_wells_csv(
        db,
        _wells_csv(["fecha-mal;Bancal Sur;3"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "error al parsear" in warnings[0]


# ---------------------------------------------------------------------------
# import_truffles_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_truffles_csv_success():
    plot = _make_plot(id=10, name="Bancal Sur")
    plant = _make_plant(id=20, plot_id=10, label="A3")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([plot]), result([plant])])
    db.add_all = MagicMock()

    rows, warnings = await import_truffles_csv(
        db,
        _plots_csv(["10/12/2025 08:15:00;Bancal Sur;A3;45,5;manual"]),
        user_id=1,
    )

    assert warnings == []
    assert len(rows) == 1
    event = rows[0]
    assert isinstance(event, TruffleEvent)
    assert event.plot_id == 10
    assert event.plant_id == 20
    assert event.estimated_weight_grams == pytest.approx(45.5)
    assert event.source == "manual"


@pytest.mark.asyncio
async def test_import_truffles_csv_unknown_plot_warns():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([])])
    db.add_all = MagicMock()

    rows, warnings = await import_truffles_csv(
        db,
        _plots_csv(["10/12/2025 08:15:00;NoExiste;A3;45,5;manual"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "NoExiste" in warnings[0]


@pytest.mark.asyncio
async def test_import_truffles_csv_unknown_plant_warns():
    plot = _make_plot(id=10, name="Bancal Sur")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([plot]), result([])])
    db.add_all = MagicMock()

    rows, warnings = await import_truffles_csv(
        db,
        _plots_csv(["10/12/2025 08:15:00;Bancal Sur;A99;45,5;manual"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "A99" in warnings[0]


# ---------------------------------------------------------------------------
# import_plot_events_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_plot_events_csv_success_and_defaults_recurring():
    plot = _make_plot(id=10, name="Bancal Sur")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([plot]), result([])])
    db.add_all = MagicMock()

    rows, warnings = await import_plot_events_csv(
        db,
        _plots_csv(["15/03/2025;Bancal Sur;poda;Primera pasada"]),
        user_id=1,
    )

    assert warnings == []
    assert len(rows) == 1
    event = rows[0]
    assert isinstance(event, PlotEvent)
    assert event.plot_id == 10
    assert event.event_type == "poda"
    assert event.notes == "Primera pasada"
    assert event.is_recurring is True


@pytest.mark.asyncio
async def test_import_plot_events_csv_unknown_plot_warns():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([])])
    db.add_all = MagicMock()

    rows, warnings = await import_plot_events_csv(
        db,
        _plots_csv(["15/03/2025;NoExiste;poda;Primera pasada;1"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "NoExiste" in warnings[0]


@pytest.mark.asyncio
async def test_import_plot_events_csv_invalid_event_type_warns():
    plot = _make_plot(id=10, name="Bancal Sur")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([plot]), result([])])
    db.add_all = MagicMock()

    rows, warnings = await import_plot_events_csv(
        db,
        _plots_csv(["15/03/2025;Bancal Sur;no_valido;Primera pasada;1"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "no_valido" in warnings[0]


@pytest.mark.asyncio
async def test_import_plot_events_csv_one_time_duplicate_warns():
    plot = _make_plot(id=10, name="Bancal Sur")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([plot]), result([(10, "vallado")])])
    db.add_all = MagicMock()

    rows, warnings = await import_plot_events_csv(
        db,
        _plots_csv(["15/03/2025;Bancal Sur;vallado;Cerrado perimetral;0"]),
        user_id=1,
    )

    assert rows == []
    assert len(warnings) == 1
    assert "ya existe" in warnings[0]


# ---------------------------------------------------------------------------
# import_all_csv_zip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_all_csv_zip_imports_supported_files(monkeypatch):
    async def fake_import_plots_csv(db, content: bytes, user_id: int):
        return [object(), object()], []

    async def fake_import_expenses_csv(db, content: bytes, user_id: int):
        return [object()], ["aviso gastos"]

    async def fake_import_plot_events_csv(db, content: bytes, user_id: int):
        return [object(), object(), object()], []

    monkeypatch.setattr(
        "app.services.import_service.import_plots_csv", fake_import_plots_csv
    )
    monkeypatch.setattr(
        "app.services.import_service.import_expenses_csv", fake_import_expenses_csv
    )
    monkeypatch.setattr(
        "app.services.import_service.import_plot_events_csv",
        fake_import_plot_events_csv,
    )

    db = MagicMock()
    zip_content = _zip_bytes(
        {
            "parcelas.csv": b"p",
            "gastos.csv": b"e",
            "labores.csv": b"l",
            "README.txt": b"ignored",
        }
    )

    imported_by_file, warnings = await import_all_csv_zip(db, zip_content, user_id=1)

    assert imported_by_file == {
        "parcelas.csv": 2,
        "gastos.csv": 1,
        "labores.csv": 3,
    }
    assert len(warnings) == 1
    assert warnings[0].startswith("gastos.csv:")


@pytest.mark.asyncio
async def test_import_all_csv_zip_invalid_zip_returns_warning():
    db = MagicMock()

    imported_by_file, warnings = await import_all_csv_zip(db, b"not-a-zip", user_id=1)

    assert imported_by_file == {}
    assert len(warnings) == 1
    assert "ZIP no es válido" in warnings[0]


@pytest.mark.asyncio
async def test_import_all_csv_zip_without_supported_files_warns():
    db = MagicMock()
    zip_content = _zip_bytes({"foo.txt": b"bar"})

    imported_by_file, warnings = await import_all_csv_zip(db, zip_content, user_id=1)

    assert imported_by_file == {}
    assert len(warnings) == 1
    assert "no contiene archivos CSV compatibles" in warnings[0]
