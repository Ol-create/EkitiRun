"""Small geometry helpers on [lng, lat] coordinates (GeoJSON order). Owner: Lead.

E14 replaces route snapping with shapely; these are enough for seeding and stubs.
"""

import itertools
import math
from bisect import bisect_left

EARTH_RADIUS_KM = 6371.0088
Coord = tuple[float, float]  # (lng, lat)


def haversine_km(a: Coord, b: Coord) -> float:
    lng1, lat1, lng2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def cumulative_km(coords: list[Coord]) -> list[float]:
    """Distance from the start to every vertex."""
    out = [0.0]
    for a, b in itertools.pairwise(coords):
        out.append(out[-1] + haversine_km(a, b))
    return out


def point_at_km(coords: list[Coord], cum: list[float], distance_km: float) -> Coord:
    """The point `distance_km` along the line (clamped to the line's ends)."""
    if distance_km <= 0:
        return coords[0]
    if distance_km >= cum[-1]:
        return coords[-1]
    i = bisect_left(cum, distance_km)
    seg = cum[i] - cum[i - 1]
    t = (distance_km - cum[i - 1]) / seg if seg else 0.0
    (lng1, lat1), (lng2, lat2) = coords[i - 1], coords[i]
    return (lng1 + (lng2 - lng1) * t, lat1 + (lat2 - lat1) * t)
