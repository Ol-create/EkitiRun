"""A fake race for the Phase 0 stub endpoints. Owner: Lead (E2).

The race runs on a looping clock, so splits, results, the live map and the SSE
streams change over time like a real race. Nothing here touches the database.
Delete this package once every stub has been replaced (end of Phase 2).
"""

import random
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

from app.core.geo import cumulative_km, point_at_km
from app.seed_data import CATEGORIES, build_routes

# The fake race starts 100 minutes "ago" when the server boots and restarts every 6.5 h.
_BOOT = time.time()
_HEAD_START_S = 100 * 60
_CYCLE_S = int(6.5 * 3600)
STALE_AFTER_S = 120

FIRST_NAMES = {
    "M": ["Ayodele", "Babatunde", "Chinedu", "Damilola", "Emeka", "Femi", "Gbenga", "Ibrahim",
          "Kehinde", "Musa", "Olumide", "Segun", "Tunde", "Yusuf", "Adewale", "Oluwaseun"],
    "F": ["Adaeze", "Bisola", "Chiamaka", "Folake", "Funmilayo", "Halima", "Ifeoma", "Kemi",
          "Ngozi", "Omolara", "Ronke", "Temitope", "Titilayo", "Yetunde", "Zainab", "Aisha"],
}  # fmt: skip
LAST_NAMES = ["Adebayo", "Afolabi", "Ajayi", "Akinola", "Babalola", "Bello", "Eze", "Fashola",
              "Ibikunle", "Ogunleye", "Ojo", "Okafor", "Oladipo", "Olatunji", "Onyeka", "Adeyemi",
              "Fagbemi", "Ilesanmi", "Oyebanji", "Fayose"]  # fmt: skip

_COUNTS = {"FULL": 50, "HALF": 70, "10K": 60, "FUN": 60}
_PACE_S_PER_KM = {"FULL": (180, 420), "HALF": (190, 450), "10K": (200, 480), "FUN": (240, 600)}


@dataclass(frozen=True)
class FakeRunner:
    runner_id: uuid.UUID
    bib_number: str
    first_name: str
    last_name: str
    gender: str
    category_code: str
    pace_s_per_km: float
    not_started: bool  # registered but never crossed the start
    dnf_at_km: float | None  # drops out before this distance
    has_tracker: bool
    stale_tracker: bool  # tracker stops reporting (flat battery)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@cache
def categories() -> list[dict[str, Any]]:
    """Seed categories with ids 1..n, matching a freshly seeded database."""
    return [{**c, "id": i} for i, c in enumerate(CATEGORIES, start=1)]


def category_by_code(code: str) -> dict[str, Any] | None:
    return next((c for c in categories() if c["code"] == code), None)


@cache
def runners() -> list[FakeRunner]:
    rng = random.Random(2027)
    out = []
    for cat in CATEGORIES:
        code = cat["code"]
        lo, hi = _PACE_S_PER_KM[code]
        for n in range(1, _COUNTS[code] + 1):
            gender = "F" if rng.random() < 0.4 else "M"
            out.append(
                FakeRunner(
                    runner_id=uuid.uuid5(uuid.NAMESPACE_URL, f"ekitirun-stub-{code}-{n}"),
                    bib_number=f"{cat['bib_prefix']}{n:04d}",
                    first_name=rng.choice(FIRST_NAMES[gender]),
                    last_name=rng.choice(LAST_NAMES),
                    gender=gender,
                    category_code=code,
                    pace_s_per_km=rng.uniform(lo, hi),
                    not_started=n % 13 == 0,
                    dnf_at_km=round(cat["distance_km"] * rng.uniform(0.3, 0.8), 1)
                    if n % 17 == 0
                    else None,
                    has_tracker=n % 11 != 0,
                    stale_tracker=n % 9 == 0,
                )
            )
    return out


def runner_by_bib(bib: str) -> FakeRunner | None:
    bib = bib.upper()
    return next((r for r in runners() if r.bib_number == bib), None)


def race_elapsed_s() -> float:
    """Seconds since the gun on the fake race clock."""
    return (time.time() - _BOOT + _HEAD_START_S) % _CYCLE_S


def gun_time() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=race_elapsed_s())


@cache
def _route_geometry(code: str) -> tuple[list[tuple[float, float]], list[float]]:
    coords = [tuple(c) for c in build_routes()[code]["geojson"]["coordinates"]]
    return coords, cumulative_km(coords)  # type: ignore[arg-type]


def runner_state(r: FakeRunner, elapsed: float | None = None) -> dict[str, Any]:
    """Status, splits, finish time and live position of one runner right now."""
    elapsed = race_elapsed_s() if elapsed is None else elapsed
    route = build_routes()[r.category_code]
    total = route["length_km"]
    gun = datetime.now(UTC) - timedelta(seconds=race_elapsed_s())

    if r.not_started:
        return {"status": "registered", "distance_km": 0.0, "splits": [],
                "finish_seconds": None, "live_position": None}  # fmt: skip

    distance = min(elapsed / r.pace_s_per_km, total)
    status = "finished" if distance >= total else "started"
    if r.dnf_at_km is not None and distance >= r.dnf_at_km:
        distance, status = r.dnf_at_km, "dnf"

    splits = []
    for cp in route["checkpoints"]:
        if cp["distance_km"] <= distance + 1e-9:
            split_s = round(cp["distance_km"] * r.pace_s_per_km)
            splits.append(
                {
                    "checkpoint_id": checkpoint_id(r.category_code, cp["code"]),
                    "checkpoint_name": cp["name"],
                    "distance_km": cp["distance_km"],
                    "scanned_at": gun + timedelta(seconds=split_s),
                    "elapsed_seconds": split_s,
                }
            )

    live = None
    if r.has_tracker:
        # A stale tracker stopped reporting 3 minutes ago.
        fix_elapsed = elapsed - 180 if r.stale_tracker and status == "started" else elapsed
        fix_km = min(max(fix_elapsed, 0) / r.pace_s_per_km, distance)
        coords, cum = _route_geometry(r.category_code)
        lng, lat = point_at_km(coords, cum, fix_km)
        recorded_at = gun + timedelta(seconds=max(fix_elapsed, 0))
        age = (datetime.now(UTC) - recorded_at).total_seconds()
        live = {
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "distance_km": round(fix_km, 3),
            "recorded_at": recorded_at,
            "is_stale": status == "started" and age > STALE_AFTER_S,
        }

    return {
        "status": status,
        "distance_km": round(distance, 3),
        "splits": splits,
        "finish_seconds": splits[-1]["elapsed_seconds"] if status == "finished" else None,
        "live_position": live,
    }


@cache
def checkpoint_ids() -> dict[tuple[str, str], int]:
    """Stable ids for every (category, checkpoint code), in seed order."""
    ids, next_id = {}, 1
    for cat in CATEGORIES:
        for cp in build_routes()[cat["code"]]["checkpoints"]:
            ids[(cat["code"], cp["code"])] = next_id
            next_id += 1
    return ids


def checkpoint_id(category_code: str, checkpoint_code: str) -> int:
    return checkpoint_ids()[(category_code, checkpoint_code)]


def ranked(category_code: str | None = None, gender: str | None = None) -> list[dict[str, Any]]:
    """Runners who have started, best first: finishers by time, then furthest along."""
    rows = []
    for r in runners():
        if category_code and r.category_code != category_code:
            continue
        if gender and r.gender != gender:
            continue
        s = runner_state(r)
        if s["status"] == "registered":
            continue
        last = s["splits"][-1] if s["splits"] else None
        rows.append({"runner": r, "state": s, "last_split": last})

    def key(row: dict[str, Any]) -> tuple:
        s, last = row["state"], row["last_split"]
        if s["status"] == "finished":
            return (0, s["finish_seconds"], 0)
        if s["status"] == "started":
            return (
                1,
                -(last["distance_km"] if last else 0),
                last["elapsed_seconds"] if last else 0,
            )
        return (2, -(last["distance_km"] if last else 0), 0)  # DNF last

    rows.sort(key=key)
    return rows


def positions_for(r: FakeRunner) -> tuple[int | None, int | None]:
    """(position in the race, position in the race within the runner's gender), finishers only."""
    s = runner_state(r)
    if s["status"] != "finished":
        return None, None
    overall = [x["runner"].bib_number for x in ranked(r.category_code)]
    by_gender = [x["runner"].bib_number for x in ranked(r.category_code, r.gender)]
    return overall.index(r.bib_number) + 1, by_gender.index(r.bib_number) + 1
