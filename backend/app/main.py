import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging_config import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_path, settings.log_max_bytes, settings.log_backup_count)
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.include_router(api_router, prefix="/api")
    application.include_router(api_router, prefix="/abel/api")

    @application.middleware("http")
    async def request_log(request: Request, call_next):
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            logging.getLogger("abel").exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logging.getLogger("abel").info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @application.get("/abel.html", include_in_schema=False)
    @application.get("/abel/", include_in_schema=False)
    def abel_frontend() -> FileResponse:
        return FileResponse("frontend/index.html")

    application.mount(
        "/abel/assets", StaticFiles(directory="frontend"), name="abel-assets"
    )
    application.mount("/assets", StaticFiles(directory="frontend"), name="assets")
    application.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
    return application


app = create_app()
