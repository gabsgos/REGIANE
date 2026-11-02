from fastapi import APIRouter

from backend.app.api.routes.admin_reports import router as admin_reports_router
from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.clinical import router as clinical_router
from backend.app.api.routes.documents import router as documents_router
from backend.app.api.routes.finance import router as finance_router
from backend.app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(admin_reports_router)
api_router.include_router(clinical_router)
api_router.include_router(documents_router)
api_router.include_router(finance_router)
