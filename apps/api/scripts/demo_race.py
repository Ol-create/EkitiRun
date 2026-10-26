"""A realistic demo race on the real database and API. Owner: Lead. Development only.

    python -m scripts.demo_race setup --runners 300 --started-minutes-ago 75
    python -m scripts.demo_race run                  # live: GPS + scans through the API
    python -m scripts.demo_race reset                # remove the demo data

`setup` registers demo runners in every race, gives most of them trackers, records
the gun starts as "N minutes ago" and saves the checkpoint scans they would have
by now, so the leaderboard has data immediately.

`run` then plays the race in real time through the real API, exactly like race
day: GPS from every tracker every 5 s (POST /gps/positions -> Redis stream ->
gps-writer -> live map) and a scan at each checkpoint a runner passes (POST
/scans/batch -> leaderboard -> /stream/results). It needs the API, Redis and the
gps-writer running (`docker compose up`). With --runners 5000 it is also the load
generator for E12.

Every runner's behaviour comes from their bib number, so `run` (in another
terminal, or after a restart) continues the same race `setup` created:
- a steady pace for their race; a few drop out (marked DNF 20 min later),
- some have no tracker, some trackers go flat mid-race,
- GPS noise of about 8 m, and the odd missed scan,
- the 15 km checkpoint phone of each course runs 150 s slow (clock correction and
  the scanner-device flag get exercised).

Demo runners are recognised by their phone numbers (+23480900xxxxx) and demo
trackers by their labels (DMO-xxxx); `reset` removes only those.
"""

import argparse
import asyncio
import hashlib
import math
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.geo import RouteGeometry
from app.core.security import create_qr_token, create_scanner_token
from app.models import (
    Category,
    Checkpoint,
    GpsPosition,
    Route,
    Runner,
    Scan,
    ScannerDevice,
    Tracker,
)
from app.stubs.race import FIRST_NAMES, LAST_NAMES

DEMO_PHONE_PREFIX = "+23480900"  # +23480900 + 5 digits
DEMO_LABEL_PREFIX = "DMO-"
SHARE = {"FULL": 0.2, "HALF": 0.35, "10K": 0.25, "FUN": 0.2}
PACE_S_PER_KM = {"FULL": (200, 420), "HALF": (210, 450), "10K": (220, 480), "FUN": (260, 600)}
DNF_AFTER_S = 20 * 60  # the race office marks a stopped runner DNF after this
SLOW_PHONE_CHECKPOINT = "CP15"
SLOW_PHONE_S = 150
GPS_NOISE_M = 8.0


# ---------------------------------------------------------------- the simulated runner


@dataclass(frozen=True)
class Plan:
    """How one demo runner behaves, derived from their bib (so every process agrees)."""

    pace_s_per_km: float
    start_delay_s: float  # crossing the start line after the gun
    dnf_at_km: float | None
    has_tracker: bool
    tracker_dies_after_s: float | None
    misses: frozenset[str]  # checkpoint codes where the scan is missed

    @staticmethod
    def for_bib(bib: str, category_code: str, total_km: float, codes: list[str]) -> "Plan":
        rng = random.Random(int(hashlib.sha256(bib.encode()).hexdigest()[:12], 16))
        lo, hi = PACE_S_PER_KM[category_code]
        pace = lo + (hi - lo) * rng.betavariate(2.2, 2.8)  # most runners mid-pack
        middle = [c for c in codes if c not in ("START", "FINISH")]
        return Plan(
            pace_s_per_km=pace,
            start_delay_s=rng.uniform(0, 90),
            dnf_at_km=round(rng.uniform(0.25, 0.85) * total_km, 2) if rng.random() < 0.03 else None,
            has_tracker=rng.random() > 0.05,
            tracker_dies_after_s=rng.uniform(1800, 7200) if rng.random() < 0.05 else None,
            misses=frozenset(c for c in middle if rng.random() < 0.02),
        )

    def distance_at(self, elapsed_s: float, total_km: float) -> float:
        """km covered `elapsed_s` after the gun."""
        km = max(0.0, (elapsed_s - self.start_delay_s) / self.pace_s_per_km)
        limit = self.dnf_at_km if self.dnf_at_km is not None else total_km
        return min(km, limit, total_km)

    def time_at_km(self, km: float) -> float:
        """Seconds after the gun when the runner reaches `km`."""
        return self.start_delay_s + km * self.pace_s_per_km


@dataclass
class DemoRunner:
    runner_id: uuid.UUID
    bib: str
    category_code: str
    category_id: int
    route_id: int
    gun: datetime
    plan: Plan
    tracker_device: str | None
    scanned: set[int] = field(default_factory=set)  # checkpoint ids already scanned
    dnf_marked: bool = False


@dataclass
class Course:
    total_km: float
    geometry: RouteGeometry
    checkpoints: list[Checkpoint]


# ---------------------------------------------------------------- setup / reset


def _guard() -> None:
    if settings.environment == "production":
        sys.exit("demo_race refuses to run in production.")


async def _delete(session: AsyncSession, statement: Any) -> int:
    result = await session.execute(statement)
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def reset(session: AsyncSession) -> dict[str, int]:
    """Remove demo runners, their scans, positions and trackers. Commits."""
    demo = select(Runner.id).where(Runner.phone.like(f"{DEMO_PHONE_PREFIX}%"))
    counts = {
        "gps_positions": await _delete(
            session, delete(GpsPosition).where(GpsPosition.runner_id.in_(demo))
        ),
        "scans": await _delete(session, delete(Scan).where(Scan.runner_id.in_(demo))),
        "trackers": await _delete(
            session, delete(Tracker).where(Tracker.label.like(f"{DEMO_LABEL_PREFIX}%"))
        ),
        "scanner_devices": await _delete(
            session, delete(ScannerDevice).where(ScannerDevice.device_id.like("demo-%"))
        ),
        "runners": await _delete(
            session, delete(Runner).where(Runner.phone.like(f"{DEMO_PHONE_PREFIX}%"))
        ),
    }
    await session.commit()
    return counts


async def _courses(session: AsyncSession) -> dict[int, Course]:
    courses = {}
    for route in await session.scalars(select(Route)):
        coords = [(float(x), float(y)) for x, y in route.geojson["coordinates"]]
        checkpoints = list(
            await session.scalars(
                select(Checkpoint)
                .where(Checkpoint.route_id == route.id)
                .order_by(Checkpoint.distance_km)
            )
        )
        courses[route.id] = Course(float(route.length_km), RouteGeometry(coords), checkpoints)
    return courses


async def setup(
    session: AsyncSession, runners: int, started_minutes_ago: float, seed: int = 2027
) -> dict[str, Any]:
    """Create the demo race and backfill scans up to now. Commits."""
    await reset(session)
    rng = random.Random(seed)
    categories = list(await session.scalars(select(Category).order_by(Category.sort_order)))
    if not categories:
        sys.exit("No categories: run `python -m scripts.seed` first.")
    courses = await _courses(session)
    now = datetime.now(UTC)
    gun = now - timedelta(minutes=started_minutes_ago)

    runner_rows, tracker_rows, scan_rows = [], [], []
    n = 0
    for category in categories:
        category.gun_start_at = gun
        course = courses[category.route_id]
        codes = [cp.code for cp in course.checkpoints]
        count = round(runners * SHARE.get(category.code, 0.25))
        for _ in range(count):
            n += 1
            bib = f"{category.bib_prefix}{category.next_bib:04d}"
            category.next_bib += 1
            gender = "F" if rng.random() < 0.42 else "M"
            runner_id = uuid.uuid4()
            runner_rows.append(
                {
                    "id": runner_id,
                    "category_id": category.id,
                    "bib_number": bib,
                    "first_name": rng.choice(FIRST_NAMES[gender]),
                    "last_name": rng.choice(LAST_NAMES),
                    "gender": gender,
                    "date_of_birth": date(1960 + rng.randrange(45), rng.randrange(1, 13), 1),
                    "phone": f"{DEMO_PHONE_PREFIX}{n:05d}",
                    "emergency_contact_name": "Demo Contact",
                    "emergency_contact_phone": "+2348090099999",
                    "tracking_consent_at": now,
                    "kit_collected_at": now,
                }
            )
            plan = Plan.for_bib(bib, category.code, course.total_km, codes)
            if plan.has_tracker:
                tracker_rows.append(
                    {
                        "device_id": f"demo-{bib}",
                        "label": f"{DEMO_LABEL_PREFIX}{n:04d}",
                        "status": "assigned",
                        "runner_id": runner_id,
                        "assigned_at": now,
                    }
                )
            elapsed = (now - gun).total_seconds()
            reached = plan.distance_at(elapsed, course.total_km)
            for cp in course.checkpoints:
                if float(cp.distance_km) <= reached + 1e-9 and cp.code not in plan.misses:
                    at = gun + timedelta(seconds=plan.time_at_km(float(cp.distance_km)))
                    scan_rows.append(
                        {
                            "id": uuid.uuid4(),
                            "client_id": uuid.uuid4(),
                            "runner_id": runner_id,
                            "checkpoint_id": cp.id,
                            "device_id": f"demo-cp-{cp.id}",
                            "scanned_at": at,
                            "clock_offset_ms": 0,
                        }
                    )
            if (
                plan.dnf_at_km is not None
                and elapsed > plan.time_at_km(plan.dnf_at_km) + DNF_AFTER_S
            ):
                runner_rows[-1]["status"] = "dnf"

    if runner_rows:
        await session.execute(insert(Runner), runner_rows)
    if tracker_rows:
        await session.execute(insert(Tracker), tracker_rows)
    for i in range(0, len(scan_rows), 5000):
        await session.execute(insert(Scan), scan_rows[i : i + 5000])
    await session.commit()
    return {
        "runners": len(runner_rows),
        "trackers": len(tracker_rows),
        "scans": len(scan_rows),
        "gun_start": gun.isoformat(timespec="seconds"),
    }


async def load(session: AsyncSession) -> tuple[list[DemoRunner], dict[int, Course]]:
    """The demo race as stored, with each runner's plan and the scans they already have."""
    courses = await _courses(session)
    rows = await session.execute(
        select(Runner, Category, Tracker.device_id)
        .join(Category, Category.id == Runner.category_id)
        .outerjoin(Tracker, Tracker.runner_id == Runner.id)
        .where(Runner.phone.like(f"{DEMO_PHONE_PREFIX}%"))
    )
    scanned: dict[uuid.UUID, set[int]] = {}
    for runner_id, checkpoint_id in await session.execute(
        select(Scan.runner_id, Scan.checkpoint_id)
        .join(Runner, Runner.id == Scan.runner_id)
        .where(Runner.phone.like(f"{DEMO_PHONE_PREFIX}%"))
    ):
        scanned.setdefault(runner_id, set()).add(checkpoint_id)
    demo = []
    for runner, category, device in rows:
        course = courses[category.route_id]
        codes = [cp.code for cp in course.checkpoints]
        demo.append(
            DemoRunner(
                runner_id=runner.id,
                bib=runner.bib_number,
                category_code=category.code,
                category_id=category.id,
                route_id=category.route_id,
                gun=category.gun_start_at or datetime.now(UTC),
                plan=Plan.for_bib(runner.bib_number, category.code, course.total_km, codes),
                tracker_device=device,
                scanned=scanned.get(runner.id, set()),
                dnf_marked=runner.status == "dnf",
            )
        )
    return demo, courses


# ---------------------------------------------------------------- live play


@dataclass
class TickReport:
    gps_sent: int = 0
    scans_sent: int = 0
    scans_accepted: int = 0
    dnf_marked: int = 0
    running: int = 0
    finished: int = 0


def _noisy(lat: float, lng: float, rng: random.Random, course: Course) -> tuple[float, float]:
    angle, metres = rng.uniform(0, 2 * math.pi), abs(rng.gauss(0, GPS_NOISE_M))
    return (
        lat + metres * math.sin(angle) / course.geometry.m_per_deg_lat,
        lng + metres * math.cos(angle) / course.geometry.m_per_deg_lng,
    )


async def tick(
    client: httpx.AsyncClient,
    runners: list[DemoRunner],
    courses: dict[int, Course],
    now: datetime,
    rng: random.Random,
) -> TickReport:
    """One moment of the race: GPS from every live tracker, scans for checkpoints passed."""
    report = TickReport()
    gps: list[dict[str, Any]] = []
    scans_by_checkpoint: dict[int, list[dict[str, Any]]] = {}
    to_mark_dnf: list[DemoRunner] = []

    for r in runners:
        course = courses[r.route_id]
        elapsed = (now - r.gun).total_seconds()
        km = r.plan.distance_at(elapsed, course.total_km)
        finished = km >= course.total_km - 1e-9
        stopped = r.plan.dnf_at_km is not None and km >= r.plan.dnf_at_km
        report.finished += finished
        report.running += (not finished) and (not stopped) and elapsed > r.plan.start_delay_s

        tracker_alive = r.tracker_device and (
            r.plan.tracker_dies_after_s is None or elapsed < r.plan.tracker_dies_after_s
        )
        if tracker_alive and elapsed > r.plan.start_delay_s and not finished and not r.dnf_marked:
            lat, lng = _noisy(*course.geometry.point_at(km), rng, course)
            gps.append({"device_id": r.tracker_device, "lat": lat, "lng": lng, "accuracy_m": 6.0,
                        "battery_pct": max(5, 100 - int(elapsed / 300)),
                        "recorded_at": now.isoformat()})  # fmt: skip

        for cp in course.checkpoints:
            if cp.id in r.scanned or float(cp.distance_km) > km + 1e-9:
                continue
            r.scanned.add(cp.id)
            if cp.code in r.plan.misses:
                continue
            at = r.gun + timedelta(seconds=r.plan.time_at_km(float(cp.distance_km)))
            scans_by_checkpoint.setdefault(cp.id, []).append(
                {
                    "client_id": str(uuid.uuid4()),
                    "qr_token": create_qr_token(r.bib, r.runner_id),
                    "scanned_at": at.isoformat(),
                }
            )

        if stopped and not r.dnf_marked and r.plan.dnf_at_km is not None:
            if elapsed > r.plan.time_at_km(r.plan.dnf_at_km) + DNF_AFTER_S:
                to_mark_dnf.append(r)

    secret = {"X-Gateway-Secret": settings.gateway_secret}
    for i in range(0, len(gps), 1000):
        response = await client.post("/api/v1/gps/positions", json={"positions": gps[i : i + 1000]},
                                      headers=secret)  # fmt: skip
        response.raise_for_status()
        report.gps_sent += response.json()["accepted"]

    for checkpoint_id, scans in scans_by_checkpoint.items():
        checkpoint = next(
            cp for c in courses.values() for cp in c.checkpoints if cp.id == checkpoint_id
        )
        device = f"demo-cp-{checkpoint_id}"
        slow = timedelta(seconds=SLOW_PHONE_S if checkpoint.code == SLOW_PHONE_CHECKPOINT else 0)
        for s in scans:  # what that phone's clock said
            s["scanned_at"] = (datetime.fromisoformat(s["scanned_at"]) - slow).isoformat()
        body = {"device_id": device, "checkpoint_id": checkpoint_id, "scans": scans,
                "sent_at": (now - slow).isoformat()}  # fmt: skip
        token = create_scanner_token(device, checkpoint_id)
        response = await client.post("/api/v1/scans/batch", json=body,
                                      headers={"Authorization": f"Bearer {token}"})  # fmt: skip
        response.raise_for_status()
        report.scans_sent += len(scans)
        report.scans_accepted += sum(r["status"] == "accepted" for r in response.json()["results"])

    admin = {"Authorization": f"Bearer {settings.admin_dev_token}"}
    for r in to_mark_dnf:
        response = await client.post(f"/api/v1/admin/runners/{r.bib}/dnf", headers=admin)
        if response.status_code == 200:
            r.dnf_marked = True
            report.dnf_marked += 1
    return report


async def run(api_url: str, every_s: float, duration_s: float | None, seed: int = 7) -> None:
    async with SessionLocal() as session:
        runners, courses = await load(session)
    if not runners:
        sys.exit("No demo race: run `python -m scripts.demo_race setup` first.")
    rng = random.Random(seed)
    started = time.monotonic()
    print(
        f"Playing {len(runners)} demo runners against {api_url} every {every_s:g} s (Ctrl+C stops)"
    )
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        while True:
            t0 = time.monotonic()
            report = await tick(client, runners, courses, datetime.now(UTC), rng)
            took = time.monotonic() - t0
            scans = f"{report.scans_accepted:>3}/{report.scans_sent:<3}"
            print(
                f"{datetime.now():%H:%M:%S}  on course {report.running:>5}  "
                f"finished {report.finished:>5}  GPS {report.gps_sent:>5}  scans {scans} "
                f"DNF+{report.dnf_marked}  ({took:.1f}s)"
            )
            if report.running == 0 and report.finished:
                print("Everyone has finished or dropped out.")
                return
            if duration_s is not None and time.monotonic() - started >= duration_s:
                return
            await asyncio.sleep(max(0.0, every_s - took))


# ---------------------------------------------------------------- CLI


async def _main(args: argparse.Namespace) -> None:
    _guard()
    if args.command == "run":
        await run(args.api, args.every, args.duration)
        return
    async with SessionLocal() as session:
        if args.command == "setup":
            summary = await setup(session, args.runners, args.started_minutes_ago)
            total = await session.scalar(select(func.count()).select_from(Runner))
            print(f"Demo race ready: {summary} ({total} runners in the database)")
            print("Leaderboards refresh on the next scan upload; start the live part with:"
                  "  python -m scripts.demo_race run")  # fmt: skip
        else:
            print("Removed:", await reset(session))
    if args.command == "setup":
        # Make the leaderboard rebuild now rather than after the first live scan.
        try:
            from redis.asyncio import Redis

            from app.modules.timing.service import mark_changed

            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            async with SessionLocal() as session:
                ids = set(await session.scalars(select(Category.id)))
            await mark_changed(redis, ids)
            await redis.aclose()
        except Exception as exc:  # Redis not running: the first live scan refreshes it anyway
            print(f"(Couldn't refresh the leaderboard cache: {exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo race on the real database and API.")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup", help="create demo runners, trackers, gun starts and past scans")
    s.add_argument("--runners", type=int, default=300)
    s.add_argument("--started-minutes-ago", type=float, default=75)
    r = sub.add_parser("run", help="play the race live through the API")
    r.add_argument("--api", default=settings.public_api_url)
    r.add_argument("--every", type=float, default=5.0, help="seconds between GPS rounds")
    r.add_argument("--duration", type=float, default=None, help="stop after this many seconds")
    sub.add_parser("reset", help="remove the demo data")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
