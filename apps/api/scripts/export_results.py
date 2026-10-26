"""Export results as CSV, one file per race. Owner: Lead (E12).

    python -m scripts.export_results                 # writes results/<CODE>.csv
    python -m scripts.export_results --out /tmp/res  # somewhere else

Straight from the timing engine (the same ranking as GET /results), so it works
even if Redis or the website is down. Use it to publish results, for the prize
committee, and as the manual fallback in docs/runbook.md.
"""

import argparse
import asyncio
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category
from app.modules.timing.service import compute_standings

COLUMNS = [
    "position",
    "position_gender",
    "bib_number",
    "full_name",
    "gender",
    "status",
    "finish_time",
    "last_checkpoint",
    "time_at_last_checkpoint",
]


def hms(seconds: int | None) -> str:
    if seconds is None:
        return ""
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


async def export(session: AsyncSession, out: Path) -> dict[str, int]:
    """Write one CSV per category. Returns rows written per category code."""
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for category in await session.scalars(select(Category).order_by(Category.sort_order)):
        standings = await compute_standings(session, category)
        path = out / f"{category.code}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            for s in standings:
                writer.writerow(
                    [
                        s.position,
                        s.position_gender,
                        s.bib_number,
                        s.full_name,
                        s.gender,
                        s.status,
                        hms(s.finish_seconds),
                        s.last_checkpoint or "",
                        hms(s.elapsed_seconds),
                    ]
                )
        written[category.code] = len(standings)
    return written


async def main(out: Path) -> None:
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        written = await export(session, out)
    for code, rows in written.items():
        print(f"{out / (code + '.csv')}: {rows} runners")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("results"))
    asyncio.run(main(parser.parse_args().out))
