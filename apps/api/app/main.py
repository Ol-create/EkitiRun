from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.auth.router import router as auth_router
from app.modules.categories.router import router as categories_router
from app.modules.payments.router import router as payments_router
from app.modules.registrations.router import router as registrations_router
from app.modules.results.router import router as results_router
from app.modules.route.router import router as route_router
from app.modules.runners.router import router as runners_router
from app.modules.scans.router import router as scans_router
from app.modules.sponsors.router import router as sponsors_router

app = FastAPI(title="EkitiRun API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth_router,
    registrations_router,
    categories_router,
    runners_router,
    sponsors_router,
    payments_router,
    route_router,
    results_router,
    scans_router,
):
    app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
