import asyncio
import logging
import sys

import pytest
from fastapi import Response
from starlette.requests import Request

from app.observability import (
    JsonFormatter,
    configure_logging,
    install_global_exception_hooks,
    metrics_middleware,
    normalize_path,
    render_metrics,
)


def _build_request(path: str = "/health") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


def test_normalize_path() -> None:
    assert normalize_path("") == "/"
    assert normalize_path("/") == "/"
    assert normalize_path("/plots/") == "/plots"
    assert normalize_path("/plots") == "/plots"


def test_json_formatter_includes_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="error message",
            args=(),
            exc_info=sys.exc_info(),
        )
    rendered = formatter.format(record)
    assert '"level": "ERROR"' in rendered
    assert '"exception":' in rendered


def test_configure_logging_works() -> None:
    configure_logging(level="WARNING", json_logs=False)
    root_logger = logging.getLogger()
    assert root_logger.level == logging.WARNING


def test_render_metrics_response() -> None:
    response = render_metrics()
    assert response.status_code == 200
    assert response.media_type.startswith("text/plain")


@pytest.mark.asyncio
async def test_metrics_middleware_success() -> None:
    request = _build_request("/health")
    logger = logging.getLogger("test.metrics")

    async def call_next(_: Request) -> Response:
        return Response(status_code=204)

    response = await metrics_middleware(request, call_next, logger)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_metrics_middleware_exception() -> None:
    request = _build_request("/broken")
    logger = logging.getLogger("test.metrics")

    async def call_next(_: Request) -> Response:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await metrics_middleware(request, call_next, logger)


def test_install_global_exception_hooks_without_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("test.hooks")

    def _raise_runtime_error() -> asyncio.AbstractEventLoop:
        raise RuntimeError("no loop")

    monkeypatch.setattr(asyncio, "get_running_loop", _raise_runtime_error)
    install_global_exception_hooks(logger)
    assert callable(sys.excepthook)
