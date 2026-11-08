from pydantic import BaseModel, Field

from api.core.config import settings


class Health(BaseModel):
    status: str = "ok"
    version: str = Field(default=settings.version)
    database: str = "not_checked"
