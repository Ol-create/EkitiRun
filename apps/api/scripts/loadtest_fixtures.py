"""Write the data the load test needs. Owner: Lead (E12). Not for production.

Run it where the target API's settings are (same DATABASE_URL and secrets), after
`python -m scripts.demo_race setup --runners 5000`:

    python -m scripts.loadtest_fixtures > loadtest/fixtures.json

The file holds 24-hour scanner logins, runner QR codes, tracker device ids and
course shapes. It is a set of credentials for that environment: keep it out of
git (it is ignored) and delete it after the test.
"""

import asyncio
import json
import random
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_qr_token, create_scanner_token
from app.models import Category, Checkpoint, Route, Runner, Tracker

MAX_QR_PER_COURSE = 2000
COURSE_POINTS = 200


async def build() -> dict:
    from app.core.database import SessionLocal

    rng = random.Random(1)
    async with SessionLocal() as session:
        categories = list(await session.scalars(select(Category)))
        routes = {r.id: r for r in await session.scalars(select(Route))}
        courses = {}
        for route in routes.values():
            coords = route.geojson["coordinates"]
            step = max(1, len(coords) // COURSE_POINTS)
            courses[str(route.id)] = coords[::step]
        scanners = [
            {
                "checkpoint_id": cp.id,
                "route_id": cp.route_id,
                "token": create_scanner_token(f"loadtest-cp-{cp.id}", cp.id),
            }
            for cp in await session.scalars(select(Checkpoint).order_by(Checkpoint.id))
        ]
        runners_by_route: dict[str, list[dict]] = {}
        bibs = []
        for runner, route_id in await session.execute(
            select(Runner, Category.route_id).join(Category, Category.id == Runner.category_id)
        ):
            bibs.append(runner.bib_number)
            runners_by_route.setdefault(str(route_id), []).append(
                {"bib": runner.bib_number, "qr": create_qr_token(runner.bib_number, runner.id)}
            )
        for key, rows in runners_by_route.items():
            rng.shuffle(rows)
            runners_by_route[key] = rows[:MAX_QR_PER_COURSE]
        devices = [
            {"device_id": device_id, "route_id": str(route_id)}
            for device_id, route_id in await session.execute(
                select(Tracker.device_id, Category.route_id)
                .join(Runner, Runner.id == Tracker.runner_id)
                .join(Category, Category.id == Runner.category_id)
                .where(Tracker.status == "assigned")
            )
        ]
    return {
        "gateway_secret": settings.gateway_secret,
        "categories": [c.code for c in categories],
        "bibs": rng.sample(bibs, min(len(bibs), 500)),
        "scanners": scanners,
        "runners_by_route": runners_by_route,
        "devices": devices,
        "courses": courses,
    }


if __name__ == "__main__":
    if settings.environment == "production":
        sys.exit("Run the load test against a staging copy, not production.")
    json.dump(asyncio.run(build()), sys.stdout)
