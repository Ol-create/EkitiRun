"""Database and business logic for route. Routers call this; it never imports FastAPI.

STUB(E10): serves the placeholder course from app/seed_data.py. Later it reads
the routes and checkpoints tables, which hold the same data after seeding.
"""

from app.core.errors import AppError
from app.modules.route.schemas import CheckpointOut, LineString, RouteOut
from app.seed_data import build_routes
from app.stubs import race


async def get_route(category_code: str) -> RouteOut:
    code = category_code.upper()
    route = build_routes().get(code)
    if route is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", f"No route for category {code}.")
    return RouteOut(
        category_code=code,
        length_km=route["length_km"],
        route=LineString(coordinates=route["geojson"]["coordinates"]),
        checkpoints=[
            CheckpointOut(
                id=race.checkpoint_id(code, cp["code"]),
                name=cp["name"],
                distance_km=cp["distance_km"],
                lat=cp["lat"],
                lng=cp["lng"],
            )
            for cp in route["checkpoints"]
        ],
    )
