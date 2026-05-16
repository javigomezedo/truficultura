from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.incident import Incident
from app.services.incidents_service import (
    create_incident,
    get_all_incidents_admin,
    get_incident_by_id,
    get_incidents_by_tenant,
    resolve_incident,
)
from tests.conftest import result


def _make_incident(**kwargs) -> Incident:
    defaults = dict(
        id=1,
        tenant_id=1,
        user_id=1,
        title="Error en el botón",
        description="El botón de guardar no funciona",
        category="boton_roto",
        severity="alta",
        resolved=False,
        admin_response=None,
    )
    defaults.update(kwargs)
    return Incident(**defaults)


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# create_incident
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_incident_adds_and_commits() -> None:
    db = _fake_db()
    incident = await create_incident(
        db=db,
        tenant_id=1,
        user_id=2,
        title="Error visual",
        description="El color está mal",
        category="error_visual",
        severity="baja",
    )
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()
    assert isinstance(incident, Incident)
    assert incident.title == "Error visual"
    assert incident.category == "error_visual"
    assert incident.severity == "baja"
    assert not incident.resolved


@pytest.mark.asyncio
async def test_create_incident_with_attachment() -> None:
    db = _fake_db()
    raw = b"fake image data"
    incident = await create_incident(
        db=db,
        tenant_id=1,
        user_id=2,
        title="Con adjunto",
        description="Captura adjunta",
        category="error_visual",
        severity="media",
        attachment_filename="captura.png",
        attachment_data=raw,
        attachment_content_type="image/png",
    )
    assert incident.attachment_filename == "captura.png"
    assert incident.attachment_data == raw
    assert incident.attachment_content_type == "image/png"


# ---------------------------------------------------------------------------
# get_incidents_by_tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_incidents_by_tenant_returns_list() -> None:
    inc1 = _make_incident(id=1)
    inc2 = _make_incident(id=2)
    db = _fake_db()
    db.execute.return_value = result([inc1, inc2])

    items = await get_incidents_by_tenant(db, tenant_id=1)

    assert items == [inc1, inc2]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_incidents_by_tenant_returns_empty() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    items = await get_incidents_by_tenant(db, tenant_id=99)

    assert items == []


# ---------------------------------------------------------------------------
# get_incident_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_incident_by_id_found() -> None:
    inc = _make_incident(id=5)
    db = _fake_db()
    db.execute.return_value = result([inc])

    found = await get_incident_by_id(db, incident_id=5)

    assert found is inc


@pytest.mark.asyncio
async def test_get_incident_by_id_not_found() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    found = await get_incident_by_id(db, incident_id=999)

    assert found is None


# ---------------------------------------------------------------------------
# get_all_incidents_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_incidents_admin_no_filters() -> None:
    incidents = [_make_incident(id=1), _make_incident(id=2, resolved=True)]
    db = _fake_db()
    db.execute.return_value = result(incidents)

    items = await get_all_incidents_admin(db)

    assert len(items) == 2


@pytest.mark.asyncio
async def test_get_all_incidents_admin_resolved_true_filter() -> None:
    resolved_inc = _make_incident(id=1, resolved=True)
    db = _fake_db()
    db.execute.return_value = result([resolved_inc])

    items = await get_all_incidents_admin(db, resolved=True)

    assert len(items) == 1
    assert items[0].resolved is True


@pytest.mark.asyncio
async def test_get_all_incidents_admin_resolved_false_filter() -> None:
    open_inc = _make_incident(id=2, resolved=False)
    db = _fake_db()
    db.execute.return_value = result([open_inc])

    items = await get_all_incidents_admin(db, resolved=False)

    assert len(items) == 1
    assert items[0].resolved is False


@pytest.mark.asyncio
async def test_get_all_incidents_admin_category_filter() -> None:
    inc = _make_incident(id=1, category="error_sistema")
    db = _fake_db()
    db.execute.return_value = result([inc])

    items = await get_all_incidents_admin(db, category="error_sistema")

    assert items[0].category == "error_sistema"


@pytest.mark.asyncio
async def test_get_all_incidents_admin_severity_filter() -> None:
    inc = _make_incident(id=1, severity="critica")
    db = _fake_db()
    db.execute.return_value = result([inc])

    items = await get_all_incidents_admin(db, severity="critica")

    assert items[0].severity == "critica"


@pytest.mark.asyncio
async def test_get_all_incidents_admin_tenant_filter() -> None:
    inc = _make_incident(id=1, tenant_id=7)
    db = _fake_db()
    db.execute.return_value = result([inc])

    items = await get_all_incidents_admin(db, tenant_id=7)

    assert items[0].tenant_id == 7


@pytest.mark.asyncio
async def test_get_all_incidents_admin_combined_filters_empty() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    items = await get_all_incidents_admin(
        db, resolved=True, tenant_id=5, category="otro", severity="baja"
    )

    assert items == []


# ---------------------------------------------------------------------------
# resolve_incident
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_incident_sets_resolved_fields() -> None:
    inc = _make_incident(id=3, resolved=False)
    db = _fake_db()

    resolved = await resolve_incident(db, inc, "Se ha corregido el problema.")

    assert resolved.resolved is True
    assert resolved.admin_response == "Se ha corregido el problema."
    assert resolved.resolved_at is not None
    assert isinstance(resolved.resolved_at, datetime.datetime)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_incident_resolved_at_is_timezone_aware() -> None:
    inc = _make_incident(id=4)
    db = _fake_db()

    resolved = await resolve_incident(db, inc, "Arreglado.")

    assert resolved.resolved_at.tzinfo is not None
