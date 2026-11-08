import uvicorn
from fastapi import FastAPI

from api import router as health_router
from api.core.config import settings

app: FastAPI = FastAPI(title="Cyn's Hub Store API", version=settings.version)

app.include_router(health_router)


def dev() -> None:
    """Start the development server with auto-reload."""
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)


def start() -> None:
    """Start the production server without auto-reload."""
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    dev()
