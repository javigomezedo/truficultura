"""Unit tests for notifications_service — use FakeExecuteResult, no real DB."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import result as fake_result
from app.models.notification import Notification, SEVERITY_INFO, SEVERITY_WARNING
from app.services import notifications_service as svc


def _session(execute_results: list):
    """Build a fake async session that returns execute_results in order."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    # each call to execute() pops the next result
    db.execute = AsyncMock(side_effect=execute_results)
    return db


# ---------------------------------------------------------------------------
# get_unread_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_unread_count_returns_scalar():
    db = _session([fake_result([5])])
    count = await svc.get_unread_count(1, db)
    assert count == 5


@pytest.mark.asyncio
async def test_get_unread_count_returns_zero_when_none():
    db = _session([fake_result([None])])
    count = await svc.get_unread_count(1, db)
    assert count == 0


# ---------------------------------------------------------------------------
# list_notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_notifications_returns_items():
    n1 = MagicMock(spec=Notification)
    n2 = MagicMock(spec=Notification)
    db = _session([fake_result([n1, n2])])
    items = await svc.list_notifications(1, db)
    assert items == [n1, n2]


# ---------------------------------------------------------------------------
# mark_read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_read_marks_and_returns_true():
    notif = MagicMock(spec=Notification)
    notif.is_read = False
    # first execute → get_notification → scalar_one_or_none
    db = _session([fake_result([notif])])
    result = await svc.mark_read(1, 1, db)
    assert result is True
    assert notif.is_read is True


@pytest.mark.asyncio
async def test_mark_read_returns_false_when_not_found():
    db = _session([fake_result([])])
    result = await svc.mark_read(999, 1, db)
    assert result is False


# ---------------------------------------------------------------------------
# dismiss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_marks_and_returns_true():
    notif = MagicMock(spec=Notification)
    notif.is_dismissed = False
    notif.is_read = False
    db = _session([fake_result([notif])])
    result = await svc.dismiss(1, 1, db)
    assert result is True
    assert notif.is_dismissed is True
    assert notif.is_read is True


@pytest.mark.asyncio
async def test_dismiss_returns_false_when_not_found():
    db = _session([fake_result([])])
    result = await svc.dismiss(999, 1, db)
    assert result is False


# ---------------------------------------------------------------------------
# mark_all_read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_all_read_returns_count():
    n1 = MagicMock(spec=Notification)
    n2 = MagicMock(spec=Notification)
    n1.is_read = False
    n2.is_read = False
    db = _session([fake_result([n1, n2])])
    count = await svc.mark_all_read(1, db)
    assert count == 2
    assert n1.is_read is True
    assert n2.is_read is True


# ---------------------------------------------------------------------------
# get_preferences — with and without existing prefs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_preferences_uses_defaults_when_empty():
    db = _session([fake_result([])])  # no rows in DB
    prefs = await svc.get_preferences(user_id=1, tenant_id=1, db=db)
    # All notification types should have defaults
    from app.models.notification import NOTIFICATION_TYPES

    for ntype in NOTIFICATION_TYPES:
        assert ntype in prefs
        assert "enabled" in prefs[ntype]
        assert "email_enabled" in prefs[ntype]


@pytest.mark.asyncio
async def test_get_preferences_uses_db_values():
    from app.models.notification import NotificationPreference

    pref = MagicMock(spec=NotificationPreference)
    pref.notification_type = "no_truffle_events"
    pref.enabled = False
    pref.email_enabled = False
    pref.threshold_days = 14
    pref.threshold_value = None
    db = _session([fake_result([pref])])
    prefs = await svc.get_preferences(user_id=1, tenant_id=1, db=db)
    assert prefs["no_truffle_events"]["enabled"] is False
    assert prefs["no_truffle_events"]["threshold_days"] == 14


# ---------------------------------------------------------------------------
# upsert_preference
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_preference_creates_new():
    from app.models.notification import NotificationPreference

    db = _session([fake_result([])])  # no existing pref
    db.add = MagicMock()
    result = await svc.upsert_preference(
        user_id=1,
        tenant_id=1,
        notification_type="campaign_start",
        enabled=True,
        email_enabled=False,
        db=db,
    )
    db.add.assert_called_once()
    assert result.enabled is True
    assert result.email_enabled is False


@pytest.mark.asyncio
async def test_upsert_preference_updates_existing():
    from app.models.notification import NotificationPreference

    existing = MagicMock(spec=NotificationPreference)
    db = _session([fake_result([existing])])
    db.add = MagicMock()
    result = await svc.upsert_preference(
        user_id=1,
        tenant_id=1,
        notification_type="campaign_start",
        enabled=False,
        email_enabled=True,
        threshold_days=7,
        db=db,
    )
    db.add.assert_not_called()
    assert result.enabled is False
    assert result.email_enabled is True
    assert result.threshold_days == 7


# ---------------------------------------------------------------------------
# _create_if_not_exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_if_not_exists_creates_new():
    db = _session([fake_result([])])  # no existing notification
    db.add = MagicMock()
    result = await svc._create_if_not_exists(
        user_id=1,
        tenant_id=1,
        notification_type="campaign_start",
        dedup_key="campaign_start:2025",
        title="Test",
        message="Test message",
        db=db,
    )
    assert result is not None
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_if_not_exists_deduplicates():
    existing = MagicMock(spec=Notification)
    db = _session([fake_result([existing])])
    db.add = MagicMock()
    result = await svc._create_if_not_exists(
        user_id=1,
        tenant_id=1,
        notification_type="campaign_start",
        dedup_key="campaign_start:2025",
        title="Test",
        message="Test message",
        db=db,
    )
    assert result is None
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# _check_campaign_start
# ---------------------------------------------------------------------------


def _make_tenant(id=1):
    t = MagicMock()
    t.id = id
    return t


def _make_user(id=1, email="user@example.com"):
    u = MagicMock()
    u.id = id
    u.email = email
    return u


@pytest.mark.asyncio
async def test_check_campaign_start_wrong_month_returns_zero():
    today = datetime.date(2025, 6, 1)  # June, not May
    db = MagicMock()
    result = await svc._check_campaign_start(today, _make_tenant(), [_make_user()], db)
    assert result == 0


@pytest.mark.asyncio
async def test_check_campaign_start_may_creates_notification():
    today = datetime.date(2025, 5, 1)
    user = _make_user()
    tenant = _make_tenant()

    prefs_result = {
        ntype: {
            "enabled": True,
            "email_enabled": False,
            "threshold_days": None,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())
        ) as mock_create:
            db = MagicMock()
            count = await svc._check_campaign_start(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()
    call_kwargs = mock_create.call_args
    assert "campaign_start:2025" in str(call_kwargs)


@pytest.mark.asyncio
async def test_check_campaign_start_disabled_pref_skips():
    today = datetime.date(2025, 5, 1)
    user = _make_user()
    tenant = _make_tenant()

    prefs_result = {
        ntype: {
            "enabled": False,
            "email_enabled": False,
            "threshold_days": None,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        db = MagicMock()
        count = await svc._check_campaign_start(today, tenant, [user], db)

    assert count == 0


# ---------------------------------------------------------------------------
# _check_campaign_end_reminder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_campaign_end_reminder_wrong_month():
    today = datetime.date(2025, 3, 1)
    db = MagicMock()
    result = await svc._check_campaign_end_reminder(
        today, _make_tenant(), [_make_user()], db
    )
    assert result == 0


@pytest.mark.asyncio
async def test_check_campaign_end_reminder_april_creates():
    today = datetime.date(2025, 4, 10)
    user = _make_user()
    tenant = _make_tenant()

    prefs_result = {
        ntype: {
            "enabled": True,
            "email_enabled": False,
            "threshold_days": None,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())
        ) as mock_create:
            db = MagicMock()
            count = await svc._check_campaign_end_reminder(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()


# ---------------------------------------------------------------------------
# _check_user_inactive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_user_inactive_active_user_skips():
    today = datetime.date(2025, 6, 15)
    user = _make_user()
    # last_seen_at = 5 days ago (threshold default is 30)
    user.last_seen_at = datetime.datetime(2025, 6, 10, tzinfo=datetime.timezone.utc)

    prefs_result = {
        ntype: {
            "enabled": True,
            "email_enabled": False,
            "threshold_days": 30,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=None)
        ) as mock_create:
            db = MagicMock()
            count = await svc._check_user_inactive(today, user, tenant_id=1, db=db)

    assert count == 0
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_user_inactive_inactive_user_creates():
    today = datetime.date(2025, 6, 15)
    user = _make_user()
    # last_seen_at = 45 days ago (threshold default is 30)
    user.last_seen_at = datetime.datetime(2025, 5, 1, tzinfo=datetime.timezone.utc)

    prefs_result = {
        ntype: {
            "enabled": True,
            "email_enabled": False,
            "threshold_days": 30,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())
        ) as mock_create:
            db = MagicMock()
            count = await svc._check_user_inactive(today, user, tenant_id=1, db=db)

    assert count == 1
    mock_create.assert_awaited_once()


# ---------------------------------------------------------------------------
# _check_no_truffle_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_truffle_events_wrong_month_returns_zero():
    """Outside Dec-Mar season → returns 0 immediately."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    db = MagicMock()
    count = await svc._check_no_truffle_events(today, tenant, [user], db)
    assert count == 0


@pytest.mark.asyncio
async def test_check_no_truffle_events_in_season_no_events_creates():
    """In season (January), no events → creates notification."""
    today = datetime.date(2025, 1, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {
            "enabled": True,
            "email_enabled": False,
            "threshold_days": 7,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    fake_count_result = MagicMock()
    fake_count_result.scalar.return_value = 0

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())
        ) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(return_value=fake_count_result)
            count = await svc._check_no_truffle_events(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_no_truffle_events_in_season_with_events_skips():
    """In season, has recent events → does not create notification."""
    today = datetime.date(2025, 1, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {
            "enabled": True,
            "email_enabled": False,
            "threshold_days": 7,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    fake_count_result = MagicMock()
    fake_count_result.scalar.return_value = 5  # has recent events

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=None)
        ) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(return_value=fake_count_result)
            count = await svc._check_no_truffle_events(today, tenant, [user], db)

    assert count == 0
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_no_truffle_events_disabled_pref_skips():
    """In season, pref disabled → returns 0."""
    today = datetime.date(2025, 1, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {
            "enabled": False,
            "email_enabled": False,
            "threshold_days": 7,
            "threshold_value": None,
        }
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(
            svc, "_create_if_not_exists", AsyncMock(return_value=None)
        ) as mock_create:
            db = MagicMock()
            count = await svc._check_no_truffle_events(today, tenant, [user], db)

    assert count == 0
    mock_create.assert_not_awaited()


# ---------------------------------------------------------------------------
# check_and_create_notifications (cron entry point)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_and_create_notifications_no_tenants():
    """No tenants → returns 0."""
    fake_tenants = MagicMock()
    fake_tenants.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=fake_tenants)

    total = await svc.check_and_create_notifications(db)
    assert total == 0


@pytest.mark.asyncio
async def test_check_and_create_notifications_no_members():
    """Tenant with no active members → skips."""
    tenant = _make_tenant()

    fake_tenants = MagicMock()
    fake_tenants.scalars.return_value.all.return_value = [tenant]
    fake_members = MagicMock()
    fake_members.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[fake_tenants, fake_members])

    total = await svc.check_and_create_notifications(db)
    assert total == 0


@pytest.mark.asyncio
async def test_check_and_create_notifications_calls_checkers():
    """With one tenant and one member, all checkers are called."""
    tenant = _make_tenant()
    user = _make_user()

    fake_tenants = MagicMock()
    fake_tenants.scalars.return_value.all.return_value = [tenant]
    fake_members = MagicMock()
    fake_members.scalars.return_value.all.return_value = [user]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[fake_tenants, fake_members])

    checker_patches = {
        name: patch.object(svc, name, AsyncMock(return_value=1))
        for name in [
            "_check_campaign_start",
            "_check_campaign_end_reminder",
            "_check_no_truffle_events",
            "_check_low_water_balance",
            "_check_no_rainfall_data",
            "_check_stressed_plants",
            "_check_no_irrigation_summer",
            "_check_no_brule_measurement",
            "_check_low_harvest",
            "_check_user_inactive",
        ]
    }

    with (
        checker_patches["_check_campaign_start"],
        checker_patches["_check_campaign_end_reminder"],
        checker_patches["_check_no_truffle_events"],
        checker_patches["_check_low_water_balance"],
        checker_patches["_check_no_rainfall_data"],
        checker_patches["_check_stressed_plants"],
        checker_patches["_check_no_irrigation_summer"],
        checker_patches["_check_no_brule_measurement"],
        checker_patches["_check_low_harvest"],
        checker_patches["_check_user_inactive"],
    ):
        total = await svc.check_and_create_notifications(db)

    # 9 tenant-level checkers + 1 per-user checker = 10 calls total
    assert total == 10


# ---------------------------------------------------------------------------
# _check_low_water_balance — early returns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_low_water_balance_no_members():
    """No members → returns 0 immediately."""
    tenant = _make_tenant()
    db = MagicMock()
    count = await svc._check_low_water_balance(datetime.date(2025, 6, 15), tenant, [], db)
    assert count == 0


@pytest.mark.asyncio
async def test_check_low_water_balance_no_plots():
    """No irrigated plots → returns 0."""
    tenant = _make_tenant()
    user = _make_user()

    fake_plots = MagicMock()
    fake_plots.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=fake_plots)

    count = await svc._check_low_water_balance(datetime.date(2025, 6, 15), tenant, [user], db)
    assert count == 0


# ---------------------------------------------------------------------------
# _check_no_rainfall_data — early return
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_rainfall_data_no_municipios():
    """No plots with municipio_cod → returns 0."""
    tenant = _make_tenant()
    user = _make_user()

    fake_plots = MagicMock()
    fake_plots.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=fake_plots)

    count = await svc._check_no_rainfall_data(datetime.date(2025, 6, 15), tenant, [user], db)
    assert count == 0


# ---------------------------------------------------------------------------
# _check_stressed_plants — disabled pref skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_stressed_plants_disabled_pref_skips():
    """Pref disabled → returns 0."""
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": False, "email_enabled": False, "threshold_days": 30, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        db = MagicMock()
        count = await svc._check_stressed_plants(datetime.date(2025, 6, 15), tenant, [user], db)

    assert count == 0


# ---------------------------------------------------------------------------
# _check_no_irrigation_summer — wrong month returns zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_irrigation_summer_wrong_month():
    """Outside Jul-Sep → returns 0 immediately."""
    tenant = _make_tenant()
    user = _make_user()
    db = MagicMock()
    count = await svc._check_no_irrigation_summer(datetime.date(2025, 3, 15), tenant, [user], db)
    assert count == 0


@pytest.mark.asyncio
async def test_check_no_irrigation_summer_no_plots():
    """In season, no irrigated plots → returns 0."""
    tenant = _make_tenant()
    user = _make_user()

    fake_plots = MagicMock()
    fake_plots.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=fake_plots)

    count = await svc._check_no_irrigation_summer(datetime.date(2025, 8, 1), tenant, [user], db)
    assert count == 0


# ---------------------------------------------------------------------------
# _check_no_brule_measurement — disabled pref skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_brule_measurement_disabled_pref_skips():
    """Pref disabled → returns 0."""
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": False, "email_enabled": False, "threshold_days": 28, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        db = MagicMock()
        count = await svc._check_no_brule_measurement(datetime.date(2025, 6, 15), tenant, [user], db)

    assert count == 0


# ---------------------------------------------------------------------------
# _check_low_harvest — wrong month returns zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_low_harvest_wrong_month():
    """Outside Dec-Mar → returns 0 immediately."""
    tenant = _make_tenant()
    user = _make_user()
    db = MagicMock()
    count = await svc._check_low_harvest(datetime.date(2025, 6, 15), tenant, [user], db)
    assert count == 0


# ---------------------------------------------------------------------------
# _check_no_rainfall_data — inner loop (has municipio, no rain → creates)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_rainfall_data_no_rain_creates():
    """Municipio found, no recent rainfall → creates notification."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": 14, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    fake_plot = MagicMock()
    fake_plot.municipio_cod = "001"
    fake_plot.provincia_cod = "30"

    fake_municipios = MagicMock()
    fake_municipios.scalars.return_value.all.return_value = [fake_plot]

    fake_count = MagicMock()
    fake_count.scalar.return_value = 0  # no rainfall records

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[fake_municipios, fake_count])
            count = await svc._check_no_rainfall_data(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_no_rainfall_data_with_rain_skips():
    """Municipio found, has recent rainfall → no notification."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": 14, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    fake_plot = MagicMock()
    fake_plot.municipio_cod = "001"
    fake_plot.provincia_cod = "30"

    fake_municipios = MagicMock()
    fake_municipios.scalars.return_value.all.return_value = [fake_plot]

    fake_count = MagicMock()
    fake_count.scalar.return_value = 5  # has rainfall records

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=None)) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[fake_municipios, fake_count])
            count = await svc._check_no_rainfall_data(today, tenant, [user], db)

    assert count == 0
    mock_create.assert_not_awaited()


# ---------------------------------------------------------------------------
# _check_stressed_plants — pref enabled, stressed plants found → creates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_stressed_plants_with_stressed_plants_creates():
    """Pref enabled, stressed plants found → creates notification."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": 30, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    fake_count = MagicMock()
    fake_count.scalar.return_value = 3  # 3 stressed plants

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(return_value=fake_count)
            count = await svc._check_stressed_plants(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_stressed_plants_no_stressed_plants_skips():
    """Pref enabled, no stressed plants → no notification."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": 30, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    fake_count = MagicMock()
    fake_count.scalar.return_value = 0

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=None)) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(return_value=fake_count)
            count = await svc._check_stressed_plants(today, tenant, [user], db)

    assert count == 0
    mock_create.assert_not_awaited()


# ---------------------------------------------------------------------------
# _check_no_brule_measurement — pref enabled, no recent brule → creates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_brule_measurement_no_recent_creates():
    """Pref enabled, no recent brule, has historical → creates notification."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": 28, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    fake_recent = MagicMock()
    fake_recent.scalar.return_value = 0  # no recent brule

    fake_historical = MagicMock()
    fake_historical.scalar.return_value = 5  # has historical data

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[fake_recent, fake_historical])
            count = await svc._check_no_brule_measurement(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_no_brule_measurement_no_historical_skips():
    """No historical brule data at all → skip notification."""
    today = datetime.date(2025, 6, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": 28, "threshold_value": None}
        for ntype in svc._DEFAULTS.keys()
    }

    fake_recent = MagicMock()
    fake_recent.scalar.return_value = 0  # no recent

    fake_historical = MagicMock()
    fake_historical.scalar.return_value = 0  # no historical either

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=None)) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[fake_recent, fake_historical])
            count = await svc._check_no_brule_measurement(today, tenant, [user], db)

    assert count == 0
    mock_create.assert_not_awaited()


# ---------------------------------------------------------------------------
# _check_low_harvest — in season with low harvest → creates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_low_harvest_no_current_data_returns_zero():
    """In season (December), no current campaign data → returns 0."""
    today = datetime.date(2025, 12, 15)
    tenant = _make_tenant()
    user = _make_user()

    # current_g = 0.0 → early return
    fake_current = MagicMock()
    fake_current.scalar.return_value = 0.0

    db = AsyncMock()
    db.execute = AsyncMock(return_value=fake_current)

    count = await svc._check_low_harvest(today, tenant, [user], db)
    assert count == 0


@pytest.mark.asyncio
async def test_check_low_harvest_no_historical_returns_zero():
    """In season, has current data but no historical → returns 0."""
    today = datetime.date(2025, 12, 15)
    tenant = _make_tenant()
    user = _make_user()

    fake_current = MagicMock()
    fake_current.scalar.return_value = 1000.0  # 1 kg

    fake_historical = MagicMock()
    fake_historical.scalar.return_value = 0.0  # no history

    fake_campaigns = MagicMock()
    fake_campaigns.all.return_value = []  # no past dates

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[fake_current, fake_historical, fake_campaigns])

    count = await svc._check_low_harvest(today, tenant, [user], db)
    assert count == 0


@pytest.mark.asyncio
async def test_check_low_harvest_low_harvest_creates():
    """In season, low harvest vs historical → creates notification."""
    today = datetime.date(2025, 12, 15)
    tenant = _make_tenant()
    user = _make_user()

    prefs_result = {
        ntype: {"enabled": True, "email_enabled": False, "threshold_days": None, "threshold_value": 50.0}
        for ntype in svc._DEFAULTS.keys()
    }

    # Current campaign: 200g (very low)
    fake_current = MagicMock()
    fake_current.scalar.return_value = 200.0

    # Historical total: 10000g
    fake_historical = MagicMock()
    fake_historical.scalar.return_value = 10000.0

    # 2 past campaign years worth of data
    fake_campaigns = MagicMock()
    past_date_1 = datetime.date(2023, 11, 1)  # campaign 2023
    past_date_2 = datetime.date(2022, 11, 1)  # campaign 2022
    fake_campaigns.all.return_value = [(past_date_1,), (past_date_2,)]

    with patch.object(svc, "get_preferences", AsyncMock(return_value=prefs_result)):
        with patch.object(svc, "_create_if_not_exists", AsyncMock(return_value=MagicMock())) as mock_create:
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[fake_current, fake_historical, fake_campaigns])
            count = await svc._check_low_harvest(today, tenant, [user], db)

    assert count == 1
    mock_create.assert_awaited_once()
