"""Database and business logic for results. Routers call this; it never imports FastAPI.

STUB(E9, E11): results and the scan stream come from the fake race in
app/stubs/race.py, which moves on a clock, so the leaderboard really changes.
"""

import asyncio
from collections.abc import AsyncIterator

from app.modules.results.schemas import ResultItem, ResultsPage, ScanEvent
from app.stubs import race

STREAM_TICK_S = 3.0


async def get_results(
    category: str | None, gender: str | None, limit: int, offset: int
) -> ResultsPage:
    rows = race.ranked(category.upper() if category else None, gender)
    items = []
    for position, row in enumerate(rows[offset : offset + limit], start=offset + 1):
        r, s, last = row["runner"], row["state"], row["last_split"]
        items.append(
            ResultItem(
                position=position,
                bib_number=r.bib_number,
                full_name=r.full_name,
                gender=r.gender,  # type: ignore[arg-type]
                category_code=r.category_code,
                status=s["status"],
                last_checkpoint=last["checkpoint_name"] if last else None,
                elapsed_seconds=last["elapsed_seconds"] if last else None,
                finish_seconds=s["finish_seconds"],
            )
        )
    return ResultsPage(items=items, total=len(rows))


async def scan_events() -> AsyncIterator[ScanEvent]:
    """Yield a scan event whenever a fake runner passes a checkpoint."""
    previous = race.race_elapsed_s()
    while True:
        await asyncio.sleep(STREAM_TICK_S)
        now = race.race_elapsed_s()
        if now < previous:  # the fake race clock looped back to the start
            previous = 0.0
        for r in race.runners():
            for split in race.runner_state(r, now)["splits"]:
                if previous < split["elapsed_seconds"] <= now:
                    yield ScanEvent(
                        bib_number=r.bib_number,
                        checkpoint_id=split["checkpoint_id"],
                        elapsed_seconds=split["elapsed_seconds"],
                    )
        previous = now
