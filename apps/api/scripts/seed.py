"""Seed routes, categories and checkpoints. Owner: Lead (E2).

Run after migrations, from apps/api:

    python -m scripts.seed                      # outside Docker (DATABASE_URL on localhost)
    docker compose exec api python -m scripts.seed

Safe to run again: existing rows (matched by name/code) are updated, not duplicated.
Sponsor tiers are seeded by Backend in B1.
"""

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import Category, Checkpoint, Route
from app.seed_data import CATEGORIES, build_routes


async def upsert(session: AsyncSession, model: type, where: dict[str, Any], values: dict[str, Any]):
    row = await session.scalar(select(model).filter_by(**where))
    if row is None:
        row = model(**where, **values)
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    await session.flush()
    return row


async def seed(session: AsyncSession) -> dict[str, int]:
    counts = {"routes": 0, "categories": 0, "checkpoints": 0}
    routes = build_routes()
    for cat in CATEGORIES:
        data = routes[cat["code"]]
        route = await upsert(
            session,
            Route,
            {"name": data["name"]},
            {"geojson": data["geojson"], "length_km": data["length_km"]},
        )
        counts["routes"] += 1
        await upsert(
            session,
            Category,
            {"code": cat["code"]},
            {k: v for k, v in cat.items() if k != "code"} | {"route_id": route.id},
        )
        counts["categories"] += 1
        for cp in data["checkpoints"]:
            await upsert(
                session,
                Checkpoint,
                {"route_id": route.id, "code": cp["code"]},
                {k: v for k, v in cp.items() if k != "code"},
            )
            counts["checkpoints"] += 1
    await session.commit()
    return counts


async def main() -> None:
    async with SessionLocal() as session:
        counts = await seed(session)
    print("Seeded:", ", ".join(f"{n} {name}" for name, n in counts.items()))


if __name__ == "__main__":
    asyncio.run(main())
