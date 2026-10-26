from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.schemas import ErrorResponse
from app.modules.auth.router import router as auth_router
from app.modules.categories.router import router as categories_router
from app.modules.files.router import router as files_router
from app.modules.gps.router import router as gps_router
from app.modules.kit.router import router as kit_router
from app.modules.payments.router import router as payments_router
from app.modules.registrations.router import router as registrations_router
from app.modules.results.router import router as results_router
from app.modules.route.router import router as route_router
from app.modules.runners.router import router as runners_router
from app.modules.scanner.router import router as scanner_router
from app.modules.scans.router import router as scans_router
from app.modules.sponsors.router import router as sponsors_router
from app.modules.timing.router import router as timing_router
from app.modules.trackers.router import router as trackers_router
from app.stubs.router import router as stub_files_router

app = FastAPI(
    title="EkitiRun API",
    version="0.1.0",
    # Document our real error shape (app/core/errors.py) instead of FastAPI's default 422.
    responses={422: {"model": ErrorResponse, "description": "Validation error"}},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

for router in (
    auth_router,
    registrations_router,
    categories_router,
    runners_router,
    sponsors_router,
    payments_router,
    route_router,
    results_router,
    scanner_router,
    scans_router,
    gps_router,
    trackers_router,
    kit_router,
    files_router,
    timing_router,
):
    app.include_router(router, prefix="/api/v1")

if settings.environment != "production":
    # Placeholder PDFs that the stub sponsor endpoints link to (Phase 0 only).
    app.include_router(stub_files_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
