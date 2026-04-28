from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.weather_service import (
    _format_age_label,
    _parse_float,
    _sum_monthly_rain,
    _fetch_current_observation,
    _fetch_forecast,
    _fetch_aemet_monthly_rain,
    _fetch_ibericam_monthly_rain,
    _get_all_aemet_stations,
    _find_aemet_station,
    _get_user_municipios,
    _hour_es,
    _hourly_value,
    get_weather_contexts,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# _parse_float
# ---------------------------------------------------------------------------


def test_parse_float_int() -> None:
    assert _parse_float(11) == pytest.approx(11.0)


def test_parse_float_european_string() -> None:
    assert _parse_float("11,5") == pytest.approx(11.5)


def test_parse_float_dot_string() -> None:
    assert _parse_float("4.2") == pytest.approx(4.2)


def test_parse_float_none() -> None:
    assert _parse_float(None) is None


def test_parse_float_empty_string() -> None:
    assert _parse_float("") is None


def test_parse_float_invalid() -> None:
    assert _parse_float("ip") is None


# ---------------------------------------------------------------------------
# _format_age_label
# ---------------------------------------------------------------------------


def test_format_age_label_minutes() -> None:
    assert _format_age_label(45) == "hace 45 min"


def test_format_age_label_hours() -> None:
    assert _format_age_label(120) == "hace 2h"


def test_format_age_label_zero() -> None:
    assert _format_age_label(0) == "hace 0 min"


# ---------------------------------------------------------------------------
# _hourly_value
# ---------------------------------------------------------------------------


def test_hourly_value_exact_match() -> None:
    items = [{"value": "18", "periodo": "13"}, {"value": "22", "periodo": "14"}]
    assert _hourly_value(items, 14) == pytest.approx(22.0)


def test_hourly_value_closest_fallback() -> None:
    """Si no hay periodo exacto, devuelve el más cercano."""
    items = [{"value": "10", "periodo": "06"}, {"value": "15", "periodo": "09"}]
    # hora 8: "09" está a 1h, "06" a 2h → devuelve el de "09"
    assert _hourly_value(items, 8) == pytest.approx(15.0)


def test_hourly_value_empty_list() -> None:
    assert _hourly_value([], 12) is None


def test_hourly_value_invalid_entries_skipped() -> None:
    """Entradas con periodo no numérico se ignoran."""
    items = [{"value": "20", "periodo": "bad"}, {"value": "18", "periodo": "10"}]
    assert _hourly_value(items, 10) == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# _hour_es
# ---------------------------------------------------------------------------


def test_hour_es_summer() -> None:
    """Abril: UTC+2."""
    with patch("app.services.weather_service.datetime") as mock_dt:
        mock_dt.datetime = MagicMock()
        mock_dt.datetime.now.return_value = MagicMock(hour=12, month=4)
        mock_dt.UTC = datetime.timezone.utc
        mock_dt.date = datetime.date
        hour = _hour_es()
    assert hour == 14


def test_hour_es_winter() -> None:
    """Enero: UTC+1."""
    with patch("app.services.weather_service.datetime") as mock_dt:
        mock_dt.datetime = MagicMock()
        mock_dt.datetime.now.return_value = MagicMock(hour=12, month=1)
        mock_dt.UTC = datetime.timezone.utc
        mock_dt.date = datetime.date
        hour = _hour_es()
    assert hour == 13


# ---------------------------------------------------------------------------
# _sum_monthly_rain
# ---------------------------------------------------------------------------


def test_sum_monthly_rain_basic() -> None:
    today = datetime.date.today().isoformat()
    records = [
        {"fecha": "2026-04-01", "prec": "5,0"},
        {"fecha": "2026-04-10", "prec": "10,0"},
        {"fecha": today, "prec": "3,2"},
    ]
    total, today_val = _sum_monthly_rain(records)
    assert total == pytest.approx(18.2)
    assert today_val == pytest.approx(3.2)


def test_sum_monthly_rain_trace_values() -> None:
    records = [
        {"fecha": "2026-04-01", "prec": "Ip"},
        {"fecha": "2026-04-02", "prec": "0,0"},
    ]
    total, today_val = _sum_monthly_rain(records)
    assert total == pytest.approx(0.0)
    assert today_val is None


def test_sum_monthly_rain_empty() -> None:
    total, today_val = _sum_monthly_rain([])
    assert total == 0.0
    assert today_val is None


def test_sum_monthly_rain_skips_invalid_dates() -> None:
    records = [
        {"fecha": "not-a-date", "prec": "5,0"},
        {"fecha": "2026-04-15", "prec": "2,0"},
    ]
    total, _ = _sum_monthly_rain(records)
    assert total == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# _get_user_municipios — construcción código INE completo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_municipios_builds_full_ine_code() -> None:
    """Combina provincia_cod + municipio_cod local → código INE completo de 5 dígitos."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            all=MagicMock(return_value=[("44", "210"), ("44", "216")])
        )
    )
    result = await _get_user_municipios(db, user_id=1)
    assert result == ["44210", "44216"]


@pytest.mark.asyncio
async def test_get_user_municipios_deduplicates() -> None:
    """Dos parcelas del mismo municipio → un único código en la lista."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            all=MagicMock(return_value=[("44", "210"), ("44", "210")])
        )
    )
    result = await _get_user_municipios(db, user_id=1)
    assert result == ["44210"]


@pytest.mark.asyncio
async def test_get_user_municipios_passthrough_full_code() -> None:
    """Si ya es un código de 5 dígitos lo devuelve sin modificar."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[("44", "44210")]))
    )
    result = await _get_user_municipios(db, user_id=1)
    assert result == ["44210"]


@pytest.mark.asyncio
async def test_get_user_municipios_no_prov_cod() -> None:
    """Sin provincia_cod usa el municipio_cod tal cual."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[(None, "210")]))
    )
    result = await _get_user_municipios(db, user_id=1)
    assert result == ["210"]


# ---------------------------------------------------------------------------
# get_weather_contexts — sin municipio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_context_no_municipio() -> None:
    import app.services.weather_service as ws

    with patch.object(ws, "_get_user_municipios", AsyncMock(return_value=[])):
        ctx_list = await get_weather_contexts(MagicMock(), user_id=1)

    assert len(ctx_list) == 1
    assert ctx_list[0]["available"] is False
    assert ctx_list[0]["error"] == "no_municipio"


# ---------------------------------------------------------------------------
# get_weather_contexts — sin API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_context_no_api_key() -> None:
    import app.services.weather_service as ws

    ws._weather_cache.clear()
    ws._station_cache.clear()

    with (
        patch.object(ws, "_get_user_municipios", AsyncMock(return_value=["44210"])),
        patch("app.services.weather_service.settings") as mock_settings,
    ):
        mock_settings.AEMET_API_KEY = None

        ctx_list = await get_weather_contexts(MagicMock(), user_id=1)

    assert len(ctx_list) == 1
    assert ctx_list[0]["available"] is False
    assert ctx_list[0]["error"] == "no_api_key"


# ---------------------------------------------------------------------------
# get_weather_contexts — flujo AEMET completo (mocks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_context_aemet_full() -> None:
    import app.services.weather_service as ws

    ws._weather_cache.clear()
    ws._station_cache.clear()

    forecast_payload = {
        "available": True,
        "municipio_name": "Sarrión",
        "provincia_name": "Teruel",
        "tomorrow_sky": "Cubierto con lluvia",
        "tomorrow_sky_code": "26",
        "tomorrow_t_max": 12,
        "tomorrow_t_min": 4,
        "tomorrow_prob_prec": 80,
    }
    obs_payload = {
        "temperature": 11.0,
        "humidity": 68.0,
        "precipitation_last": 0.2,
        "wind_speed": 3.5,
        "wind_dir_deg": 270.0,
        "updated_at": datetime.datetime(2026, 4, 28, 12, 0, tzinfo=datetime.UTC),
        "updated_ago_minutes": 30,
        "updated_ago_label": "hace 30 min",
    }

    with (
        patch.object(ws, "_fetch_forecast", AsyncMock(return_value=forecast_payload)),
        patch.object(ws, "_find_aemet_station", AsyncMock(return_value="8416")),
        patch.object(
            ws, "_fetch_current_observation", AsyncMock(return_value=obs_payload)
        ),
        patch.object(
            ws, "_fetch_aemet_monthly_rain", AsyncMock(return_value=(38.0, 4.2))
        ),
        patch("app.services.weather_service.settings") as mock_settings,
    ):
        mock_settings.AEMET_API_KEY = "test-key"

        # _get_user_municipios returns ["44210"]
        with patch.object(
            ws, "_get_user_municipios", AsyncMock(return_value=["44210"])
        ):
            ctx_list = await get_weather_contexts(MagicMock(), user_id=1)

    assert len(ctx_list) == 1
    ctx = ctx_list[0]
    assert ctx["available"] is True
    assert ctx["source"] == "aemet"
    assert ctx["display_name"] == "Sarrión, Teruel"
    assert ctx["temperature"] == pytest.approx(11.0)
    assert ctx["humidity"] == pytest.approx(68.0)
    assert ctx["rain_month"] == pytest.approx(38.0)
    assert ctx["precipitation_today"] == pytest.approx(4.2)
    assert ctx["tomorrow_sky"] == "Cubierto con lluvia"
    assert ctx["tomorrow_t_max"] == 12
    assert ctx["tomorrow_prob_prec"] == 80
    assert ctx["freshness"] == "success"


# ---------------------------------------------------------------------------
# get_weather_contexts — multi-municipio en paralelo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_contexts_multi_municipio() -> None:
    """Con dos municipios devuelve una lista de dos contextos."""
    import app.services.weather_service as ws

    ws._weather_cache.clear()
    ws._station_cache.clear()

    data_a = {
        "available": True,
        "source": "aemet",
        "temperature": 10.0,
        "municipio_cod": "44210",
    }
    data_b = {
        "available": True,
        "source": "ibericam",
        "temperature": None,
        "municipio_cod": "44100",
    }

    async def fake_build(municipio_cod: str) -> dict:
        return data_a if municipio_cod == "44210" else data_b

    with (
        patch.object(
            ws, "_get_user_municipios", AsyncMock(return_value=["44210", "44100"])
        ),
        patch.object(ws, "_build_weather_data_for_municipio", side_effect=fake_build),
        patch("app.services.weather_service.settings") as mock_settings,
    ):
        mock_settings.AEMET_API_KEY = "test-key"
        ctx_list = await get_weather_contexts(MagicMock(), user_id=1)

    assert len(ctx_list) == 2
    assert ctx_list[0]["temperature"] == pytest.approx(10.0)
    assert ctx_list[1]["temperature"] is None


# ---------------------------------------------------------------------------
# get_weather_contexts — fallback ibericam
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_context_ibericam_fallback() -> None:
    """Sin estación AEMET → lluvia mensual de ibericam, temperatura/humedad = None."""
    import app.services.weather_service as ws

    ws._weather_cache.clear()
    ws._station_cache.clear()

    forecast_payload = {
        "municipio_name": "Sarrión",
        "provincia_name": "Teruel",
        "tomorrow_sky": "Nuboso",
        "tomorrow_sky_code": "14",
        "tomorrow_t_max": 10,
        "tomorrow_t_min": 2,
        "tomorrow_prob_prec": 20,
    }

    with (
        patch.object(ws, "_fetch_forecast", AsyncMock(return_value=forecast_payload)),
        patch.object(ws, "_find_aemet_station", AsyncMock(return_value=None)),
        patch.object(ws, "_fetch_ibericam_monthly_rain", AsyncMock(return_value=22.5)),
        patch.object(ws, "_fetch_hourly_forecast_obs", AsyncMock(return_value=None)),
        patch.object(ws, "_get_user_municipios", AsyncMock(return_value=["44210"])),
        patch("app.services.weather_service.settings") as mock_settings,
    ):
        mock_settings.AEMET_API_KEY = "test-key"

        ctx_list = await get_weather_contexts(MagicMock(), user_id=1)

    assert len(ctx_list) == 1
    ctx = ctx_list[0]
    assert ctx["available"] is True
    assert ctx["source"] == "ibericam"
    assert ctx["temperature"] is None
    assert ctx["humidity"] is None
    assert ctx["rain_month"] == pytest.approx(22.5)
    assert ctx["station_id"] is None


@pytest.mark.asyncio
async def test_hourly_forecast_obs_returns_temperature() -> None:
    """_fetch_hourly_forecast_obs extrae temperatura y humedad del día correcto."""
    import datetime
    import app.services.weather_service as ws

    hora_local = 14
    horaria_data = [
        {
            "nombre": "Teruel",
            "prediccion": {
                "dia": [
                    {
                        "fecha": datetime.date.today().isoformat() + "T00:00:00",
                        "temperatura": [
                            {"value": "20", "periodo": "13"},
                            {"value": "22", "periodo": "14"},
                            {"value": "21", "periodo": "15"},
                        ],
                        "humedadRelativa": [
                            {"value": "55", "periodo": "14"},
                        ],
                    }
                ]
            },
        }
    ]

    mock_client = AsyncMock()
    mock_client.fetch_dataset = AsyncMock(return_value=horaria_data)

    with (
        patch("app.services.weather_service.AemetClient", return_value=mock_client),
        patch.object(ws, "_hour_es", return_value=hora_local),
    ):
        result = await ws._fetch_hourly_forecast_obs("44216")

    assert result is not None
    assert result["temperature"] == pytest.approx(22.0)
    assert result["humidity"] == pytest.approx(55.0)
    assert result["is_forecast"] is True
    assert result["updated_ago_minutes"] is None


@pytest.mark.asyncio
async def test_hourly_forecast_obs_returns_none_on_empty_data() -> None:
    """_fetch_hourly_forecast_obs devuelve None si la API no retorna datos."""
    import app.services.weather_service as ws

    mock_client = AsyncMock()
    mock_client.fetch_dataset = AsyncMock(return_value=[])

    with patch("app.services.weather_service.AemetClient", return_value=mock_client):
        result = await ws._fetch_hourly_forecast_obs("44216")

    assert result is None


@pytest.mark.asyncio
async def test_hourly_forecast_obs_returns_none_on_exception() -> None:
    """_fetch_hourly_forecast_obs captura excepciones y devuelve None."""
    import app.services.weather_service as ws

    mock_client = AsyncMock()
    mock_client.fetch_dataset = AsyncMock(side_effect=Exception("API error"))

    with patch("app.services.weather_service.AemetClient", return_value=mock_client):
        result = await ws._fetch_hourly_forecast_obs("44216")

    assert result is None


@pytest.mark.asyncio
async def test_weather_context_uses_forecast_fallback_when_obs_missing() -> None:
    """Con estación pero sin observación real → fallback horario activa freshness='info'."""
    import app.services.weather_service as ws

    ws._weather_cache.clear()
    ws._station_cache.clear()

    forecast_payload = {
        "municipio_name": "Teruel",
        "provincia_name": "Teruel",
        "tomorrow_sky": "Despejado",
        "tomorrow_sky_code": "11",
        "tomorrow_t_max": 24,
        "tomorrow_t_min": 8,
        "tomorrow_prob_prec": 5,
    }
    hourly_fallback = {
        "temperature": 22.0,
        "humidity": 48.0,
        "precipitation_last": None,
        "wind_speed": None,
        "wind_dir_deg": None,
        "updated_at": None,
        "updated_ago_minutes": None,
        "updated_ago_label": None,
        "is_forecast": True,
    }

    with (
        patch.object(ws, "_fetch_forecast", AsyncMock(return_value=forecast_payload)),
        patch.object(ws, "_find_aemet_station", AsyncMock(return_value="8368U")),
        patch.object(ws, "_fetch_current_observation", AsyncMock(return_value=None)),
        patch.object(
            ws, "_fetch_aemet_monthly_rain", AsyncMock(return_value=(15.0, 2.0))
        ),
        patch.object(
            ws, "_fetch_hourly_forecast_obs", AsyncMock(return_value=hourly_fallback)
        ),
        patch.object(ws, "_get_user_municipios", AsyncMock(return_value=["44216"])),
        patch("app.services.weather_service.settings") as mock_settings,
    ):
        mock_settings.AEMET_API_KEY = "test-key"
        ctx_list = await get_weather_contexts(MagicMock(), user_id=1)

    assert len(ctx_list) == 1
    ctx = ctx_list[0]
    assert ctx["available"] is True
    assert ctx["temperature"] == pytest.approx(22.0)
    assert ctx["humidity"] == pytest.approx(48.0)
    assert ctx["freshness"] == "info"
    assert ctx["source"] == "aemet_forecast"


# ---------------------------------------------------------------------------
# Cache hit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_context_returns_cached_data() -> None:
    """Segunda llamada con caché válido no llama a _build_weather_data_for_municipio."""
    import app.services.weather_service as ws

    ws._weather_cache.clear()
    # Pre-load a valid cache entry
    cached_data = {"available": True, "temperature": 15.0, "source": "aemet"}
    ws._weather_cache["44210"] = {
        "data": cached_data,
        "fetched_at": datetime.datetime.now(datetime.UTC),
    }

    with (
        patch.object(ws, "_get_user_municipios", AsyncMock(return_value=["44210"])),
        patch.object(
            ws, "_build_weather_data_for_municipio", AsyncMock()
        ) as mock_build,
        patch("app.services.weather_service.settings") as mock_settings,
    ):
        mock_settings.AEMET_API_KEY = "test-key"
        ctx_list = await get_weather_contexts(MagicMock(), user_id=1)
        mock_build.assert_not_called()

    assert ctx_list[0]["temperature"] == pytest.approx(15.0)

    # Cleanup
    ws._weather_cache.clear()


# ---------------------------------------------------------------------------
# _fetch_current_observation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_current_observation_parses_fields() -> None:
    """Parsea correctamente temperatura, humedad y timestamp de AEMET."""
    fint = "2026-04-28T12:00:00"
    fake_payload = [
        {
            "ta": "11,5",
            "hr": 68,
            "prec": "0,2",
            "vv": 3.5,
            "dv": 270.0,
            "fint": fint,
        }
    ]

    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(return_value=fake_payload)

        obs = await _fetch_current_observation("8416")

    assert obs is not None
    assert obs["temperature"] == pytest.approx(11.5)
    assert obs["humidity"] == pytest.approx(68.0)
    assert obs["precipitation_last"] == pytest.approx(0.2)
    assert obs["wind_speed"] == pytest.approx(3.5)
    assert obs["updated_ago_minutes"] is not None
    assert obs["updated_ago_label"] is not None


@pytest.mark.asyncio
async def test_fetch_current_observation_returns_none_on_empty() -> None:
    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(return_value=[])

        obs = await _fetch_current_observation("8416")

    assert obs is None


@pytest.mark.asyncio
async def test_fetch_current_observation_returns_none_on_exception() -> None:
    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(side_effect=RuntimeError("AEMET down"))

        obs = await _fetch_current_observation("8416")

    assert obs is None


# ---------------------------------------------------------------------------
# _fetch_forecast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_forecast_parses_tomorrow() -> None:
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    fake_payload = [
        {
            "nombre": "Sarrión",
            "provincia": "Teruel",
            "prediccion": {
                "dia": [
                    {
                        "fecha": datetime.date.today().isoformat() + "T00:00:00",
                        "estadoCielo": [
                            {
                                "value": "11",
                                "periodo": "00-24",
                                "descripcion": "Despejado",
                            }
                        ],
                        "temperatura": {"maxima": 14, "minima": 5},
                        "probPrecipitacion": [{"value": "5", "periodo": "00-24"}],
                    },
                    {
                        "fecha": tomorrow + "T00:00:00",
                        "estadoCielo": [
                            {
                                "value": "26",
                                "periodo": "00-24",
                                "descripcion": "Cubierto con lluvia",
                            }
                        ],
                        "temperatura": {"maxima": 12, "minima": 4},
                        "probPrecipitacion": [{"value": "80", "periodo": "00-24"}],
                    },
                ]
            },
        }
    ]

    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(return_value=fake_payload)

        fc = await _fetch_forecast("44210")

    assert fc is not None
    assert fc["municipio_name"] == "Sarrión"
    assert fc["provincia_name"] == "Teruel"
    assert fc["tomorrow_sky"] == "Cubierto con lluvia"
    assert fc["tomorrow_t_max"] == 12
    assert fc["tomorrow_t_min"] == 4
    assert fc["tomorrow_prob_prec"] == 80


@pytest.mark.asyncio
async def test_fetch_forecast_returns_none_on_exception() -> None:
    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(side_effect=RuntimeError("error"))

        fc = await _fetch_forecast("44210")

    assert fc is None


# ---------------------------------------------------------------------------
# _fetch_aemet_monthly_rain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_aemet_monthly_rain_sums_correctly() -> None:
    today = datetime.date.today().isoformat()
    fake_records = [
        {"fecha": "2026-04-01", "prec": "5,0"},
        {"fecha": "2026-04-10", "prec": "10,0"},
        {"fecha": today, "prec": "3,0"},
    ]

    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(return_value=fake_records)

        total, today_val = await _fetch_aemet_monthly_rain("8416")

    assert total == pytest.approx(18.0)
    assert today_val == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_fetch_aemet_monthly_rain_returns_none_on_exception() -> None:
    with patch("app.services.weather_service.AemetClient") as MockClient:
        instance = MockClient.return_value
        instance.fetch_dataset = AsyncMock(side_effect=RuntimeError("error"))

        total, today_val = await _fetch_aemet_monthly_rain("8416")

    assert total is None
    assert today_val is None


# ---------------------------------------------------------------------------
# _fetch_ibericam_monthly_rain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_ibericam_monthly_rain_sums_records() -> None:
    today = datetime.date.today()
    fake_records = [
        (datetime.date(today.year, today.month, 1), 5.0),
        (datetime.date(today.year, today.month, 2), 12.0),
        (today, 2.5),
    ]

    with patch(
        "app.services.weather_service.get_daily_precipitation",
        AsyncMock(return_value=fake_records),
    ):
        total = await _fetch_ibericam_monthly_rain("sarrion")

    assert total == pytest.approx(19.5)


@pytest.mark.asyncio
async def test_fetch_ibericam_monthly_rain_returns_none_on_exception() -> None:
    with patch(
        "app.services.weather_service.get_daily_precipitation",
        AsyncMock(side_effect=RuntimeError("ibericam down")),
    ):
        total = await _fetch_ibericam_monthly_rain("sarrion")

    assert total is None


# ---------------------------------------------------------------------------
# _get_all_aemet_stations — cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_aemet_stations_returns_cached() -> None:
    import app.services.weather_service as ws

    ws._all_stations = [
        {"indicativo": "8416", "nombre": "TERUEL", "provincia": "TERUEL"}
    ]
    ws._all_stations_fetched_at = datetime.datetime.now(datetime.UTC)

    stations = await _get_all_aemet_stations()

    assert len(stations) == 1
    assert stations[0]["indicativo"] == "8416"

    # Cleanup
    ws._all_stations = None
    ws._all_stations_fetched_at = None


# ---------------------------------------------------------------------------
# _find_aemet_station — delegates to find_aemet_station_for_municipio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_aemet_station_caches_result() -> None:
    import app.services.weather_service as ws

    ws._station_cache.clear()
    ws._all_stations = [
        {"indicativo": "8416", "nombre": "SARRI N", "provincia": "TERUEL"}
    ]
    ws._all_stations_fetched_at = datetime.datetime.now(datetime.UTC)

    with patch(
        "app.services.weather_service.find_aemet_station_for_municipio",
        return_value="8416",
    ):
        station1 = await _find_aemet_station("44210", "Sarrión")
        station2 = await _find_aemet_station("44210", "Sarrión")  # from cache

    assert station1 == "8416"
    assert station2 == "8416"

    # Cleanup
    ws._station_cache.clear()
    ws._all_stations = None
    ws._all_stations_fetched_at = None
