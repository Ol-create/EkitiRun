"""Small geometry helpers on [lng, lat] coordinates (GeoJSON order). Owner: Lead.

`RouteGeometry` places GPS points on a course (E13, E14) using shapely in a flat,
metre-based projection centred on the course: accurate to well under a metre over
a 42 km route in one city.
"""

import itertools
import math
from bisect import bisect_left
from dataclasses import dataclass

from shapely.geometry import LineString, Point
from shapely.ops import substring

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


@dataclass(frozen=True)
class PlacedPoint:
    distance_km: float  # how far along the course the nearest course point is
    off_route_m: float  # how far the GPS point is from the course


class RouteGeometry:
    """A course as a shapely line in metres, for placing GPS points on it."""

    def __init__(self, coords: list[Coord]) -> None:
        if len(coords) < 2:
            raise ValueError("A course needs at least two points")
        self.lng0, self.lat0 = coords[len(coords) // 2]
        self.m_per_deg_lat = math.radians(1) * EARTH_RADIUS_KM * 1000
        self.m_per_deg_lng = self.m_per_deg_lat * math.cos(math.radians(self.lat0))
        self.line = LineString([self._xy(lng, lat) for lng, lat in coords])
        self.length_km = self.line.length / 1000

    def _xy(self, lng: float, lat: float) -> tuple[float, float]:
        return (lng - self.lng0) * self.m_per_deg_lng, (lat - self.lat0) * self.m_per_deg_lat

    def place(self, lat: float, lng: float) -> PlacedPoint:
        point = Point(self._xy(lng, lat))
        return PlacedPoint(
            distance_km=self.line.project(point) / 1000,
            off_route_m=self.line.distance(point),
        )

    def place_between(self, lat: float, lng: float, start_km: float, end_km: float) -> PlacedPoint:
        """Like `place`, but only searching the course between `start_km` and `end_km`.

        Needed where the course passes the same spot twice (a loop's start and
        finish, an out-and-back road): searching near the runner's last known
        distance picks the right pass.
        """
        start_m = max(0.0, start_km * 1000)
        end_m = min(self.line.length, end_km * 1000)
        if end_m - start_m < 1:
            return self.place(lat, lng)
        part = substring(self.line, start_m, end_m)
        point = Point(self._xy(lng, lat))
        return PlacedPoint(
            distance_km=(start_m + part.project(point)) / 1000,
            off_route_m=part.distance(point),
        )

    def point_at(self, distance_km: float) -> tuple[float, float]:
        """(lat, lng) of the course point `distance_km` from the start."""
        p = self.line.interpolate(max(0.0, min(distance_km * 1000, self.line.length)))
        return self.lat0 + p.y / self.m_per_deg_lat, self.lng0 + p.x / self.m_per_deg_lng
