from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse

from api.core.config import settings
from api.core.database import engine, init_db
from api.core.logging import RequestLoggingMiddleware, logger, setup_logging
from api.routers.v1 import v1_router

setup_logging(log_level=settings.log_level, json_format=settings.json_logs)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup and shutdown lifecycle events."""
    logger.info("Starting Cyn's Hub Store API...")
    await init_db()
    yield
    logger.info("Shutting down API and disposing database engine...")
    await engine.dispose()


app: FastAPI = FastAPI(
    title="Cyn's Hub Store API",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.include_router(v1_router)


@app.get("/", include_in_schema=False, response_model=None)
async def root() -> Response | dict[str, str]:
    """Redirects to interactive Swagger docs in dev/debug; returns 200 OK JSON in production."""
    if settings.env == "development" or settings.debug:
        return RedirectResponse(url="/docs")
    return {
        "app": "Cyn's Hub Store API",
        "version": settings.version,
        "status": "online",
        "api_v1": settings.api_v1_prefix,
    }


def dev() -> None:
    """Start the development server with auto-reload."""
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)


def start() -> None:
    """Start the production server without auto-reload."""
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    dev()
