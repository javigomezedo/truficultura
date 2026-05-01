import asyncio
import importlib
import json
import logging
import logging.config
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNTER = Counter(
    "trufiq_http_requests_total",
    "Total de peticiones HTTP",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "trufiq_http_request_duration_seconds",
    "Duracion de peticiones HTTP en segundos",
    ["method", "path"],
)
UNHANDLED_EXCEPTIONS_COUNTER = Counter(
    "trufiq_unhandled_exceptions_total",
    "Total de excepciones no controladas",
    ["source"],
)
EMAIL_BACKEND_FAILURES_COUNTER = Counter(
    "trufiq_email_backend_failures_total",
    "Fallos de backend de email por proveedor",
    ["backend"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            message["exception"] = self.formatException(record.exc_info)
        return json.dumps(message, ensure_ascii=True)


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    formatter = "json" if json_logs else "text"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "text": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
                "json": {
                    "()": "app.observability.JsonFormatter",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "level": level.upper(),
                "handlers": ["console"],
            },
        }
    )


def record_unhandled_exception(
    logger: logging.Logger, source: str, message: str
) -> None:
    UNHANDLED_EXCEPTIONS_COUNTER.labels(source=source).inc()
    logger.exception(message)


def install_global_exception_hooks(logger: logging.Logger) -> None:
    old_excepthook = sys.excepthook

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: Any,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            old_excepthook(exc_type, exc_value, exc_traceback)
            return
        UNHANDLED_EXCEPTIONS_COUNTER.labels(source="sys").inc()
        logger.error(
            "Excepcion no controlada a nivel de proceso",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        old_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        UNHANDLED_EXCEPTIONS_COUNTER.labels(source="thread").inc()
        logger.error(
            "Excepcion no controlada en hilo",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = handle_thread_exception

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    old_loop_handler = loop.get_exception_handler()

    def loop_exception_handler(
        current_loop: asyncio.AbstractEventLoop, context: dict[str, Any]
    ) -> None:
        UNHANDLED_EXCEPTIONS_COUNTER.labels(source="asyncio").inc()
        exception = context.get("exception")
        if exception is not None:
            logger.error(
                "Excepcion no controlada en loop asyncio",
                exc_info=(type(exception), exception, exception.__traceback__),
            )
        else:
            logger.error(
                "Excepcion no controlada en loop asyncio: %s", context.get("message")
            )

        if old_loop_handler is not None:
            old_loop_handler(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(loop_exception_handler)


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Any], logger: logging.Logger
) -> Response:
    method = request.method
    path = normalize_path(request.url.path)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start
        REQUEST_COUNTER.labels(method=method, path=path, status="500").inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
        record_unhandled_exception(
            logger=logger, source="http", message="Excepcion HTTP no controlada"
        )
        raise

    duration = time.perf_counter() - start
    status = str(response.status_code)
    REQUEST_COUNTER.labels(method=method, path=path, status=status).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
    return response


def render_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def configure_sentry(
    *,
    dsn: str | None,
    environment: str,
    service_name: str,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
    logger: logging.Logger | None = None,
) -> bool:
    """Initialize Sentry when DSN is configured.

    Returns True when Sentry was initialized successfully, False otherwise.
    """
    if not dsn:
        return False

    active_logger = logger or logging.getLogger(__name__)

    try:
        sentry_sdk = importlib.import_module("sentry_sdk")
        sentry_logging = importlib.import_module("sentry_sdk.integrations.logging")
    except Exception:
        active_logger.warning("Sentry DSN definido pero sentry-sdk no esta disponible.")
        return False

    logging_integration = sentry_logging.LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR,
    )

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[logging_integration],
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", service_name)
    active_logger.info(
        "Sentry inicializado para service=%s env=%s",
        service_name,
        environment,
    )
    return True
