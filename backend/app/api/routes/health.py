import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.db.session import get_engine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
def health_check(response: Response) -> HealthResponse:
    settings = get_settings()
    checks: dict[str, str] = {"api": "ok"}
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "error"
    try:
        storage = Path(settings.document_storage_path)
        storage.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=storage, prefix=".health-", delete=True):
            pass
        checks["document_storage"] = "ok"
    except OSError:
        checks["document_storage"] = "error"
    overall = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=overall,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        checks=checks,
    )
