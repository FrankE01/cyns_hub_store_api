import logging
import logging.config
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injects the active request ID into the log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()  # type: ignore[attr-defined]
        return True


def setup_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """Configures centralized logging for the API and server."""
    format_str = (
        '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", '
        '"request_id": "%(request_id)s", "message": "%(message)s"}'
        if json_format
        else "[%(asctime)s] [%(levelname)s] [%(name)s] [%(request_id)s] %(message)s"
    )

    logging_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": RequestIdFilter,
            },
        },
        "formatters": {
            "standard": {
                "format": format_str,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": log_level,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "api": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_config)


logger: logging.Logger = logging.getLogger("api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a Request ID and logs request lifecycle and timing."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        logger.info(f"--> {request.method} {request.url.path}")

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["x-request-id"] = req_id
            logger.info(
                f"<-- {request.method} {request.url.path} {response.status_code} ({duration_ms:.2f}ms)"
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                f"<-- ERROR {request.method} {request.url.path} ({duration_ms:.2f}ms): {exc}"
            )
            raise
        finally:
            request_id_ctx.reset(token)
