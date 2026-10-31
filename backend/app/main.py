from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.include_router(api_router, prefix="/api")
    return application


app = create_app()
