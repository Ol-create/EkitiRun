"""Reference data for seeding and for the Phase 0 stubs. Owner: Lead (E2).

PLACEHOLDER COURSE: the routes below are generated loops around Ado-Ekiti so
the maps have something realistic to draw. Replace them with the organisers'
real GPX course before race day (keep the same category codes).
"""

import math
from functools import cache
from typing import Any

from app.core.geo import Coord, cumulative_km, point_at_km

# Start/finish: near Oluyemi Kayode Stadium, Ado-Ekiti (approximate).
START: Coord = (5.2281, 7.6262)

CATEGORIES: list[dict[str, Any]] = [
    {"code": "FULL", "name": "Full Marathon", "distance_km": 42.195, "cap": 1000,
     "bib_prefix": "F", "min_age": 18, "sort_order": 1},
    {"code": "HALF", "name": "Half Marathon", "distance_km": 21.0975, "cap": 2000,
     "bib_prefix": "H", "min_age": 18, "sort_order": 2},
    {"code": "10K", "name": "10 km Run", "distance_km": 10.0, "cap": 2000,
     "bib_prefix": "T", "min_age": 12, "sort_order": 3},
    {"code": "FUN", "name": "5 km Fun Run", "distance_km": 5.0, "cap": 3000,
     "bib_prefix": "R", "min_age": 0, "sort_order": 4},
]  # fmt: skip

# Intermediate checkpoints (km) per category, besides START and FINISH.
CHECKPOINT_KM: dict[str, list[float]] = {
    "FULL": [5, 10, 15, 20, 25, 30, 35, 40],
    "HALF": [5, 10, 15, 20],
    "10K": [5],
    "FUN": [],
}

# Loop shape per category: (wobble amplitude, wobble frequency, start angle).
_SHAPES = {
    "FULL": (0.30, 3, 0.0),
    "HALF": (0.25, 4, 1.2),
    "10K": (0.2, 2, 2.4),
    "FUN": (0.15, 3, 3.6),
}


def _loop(target_km: float, amp: float, freq: int, theta0: float, points: int = 360) -> list[Coord]:
    """A closed, wobbly loop that starts and ends at START and is `target_km` long."""
    lng0, lat0 = START
    km_per_deg_lat = 111.32
    km_per_deg_lng = 111.32 * math.cos(math.radians(lat0))

    def build(radius_km: float) -> list[Coord]:
        def offset(theta: float) -> tuple[float, float]:
            r = radius_km * (1 + amp * math.sin(freq * (theta - theta0)))
            return r * math.cos(theta), r * math.sin(theta)

        cx, cy = offset(theta0)
        coords = []
        for i in range(points + 1):
            x, y = offset(theta0 + 2 * math.pi * i / points)
            coords.append(
                (
                    round(lng0 + (x - cx) / km_per_deg_lng, 6),
                    round(lat0 + (y - cy) / km_per_deg_lat, 6),
                )
            )
        return coords

    unit_length = cumulative_km(build(1.0))[-1]
    return build(target_km / unit_length)


@cache
def build_routes() -> dict[str, dict[str, Any]]:
    """Route and checkpoints for every category code."""
    routes = {}
    for cat in CATEGORIES:
        code, total = cat["code"], cat["distance_km"]
        coords = _loop(total, *_SHAPES[code])
        cum = cumulative_km(coords)
        stops = [("START", "Start", 0.0)]
        stops += [(f"CP{int(km)}", f"{int(km)} km", float(km)) for km in CHECKPOINT_KM[code]]
        stops.append(("FINISH", "Finish", total))
        checkpoints = []
        for order, (cp_code, name, km) in enumerate(stops, start=1):
            lng, lat = point_at_km(coords, cum, km)
            checkpoints.append(
                {
                    "code": cp_code,
                    "name": name,
                    "distance_km": km,
                    "lat": lat,
                    "lng": lng,
                    "is_start": cp_code == "START",
                    "is_finish": cp_code == "FINISH",
                    "sort_order": order,
                }
            )
        routes[code] = {
            "name": f"{cat['name']} course",
            "geojson": {"type": "LineString", "coordinates": [list(c) for c in coords]},
            "length_km": round(cum[-1], 3),
            "checkpoints": checkpoints,
        }
    return routes
