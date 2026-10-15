"""Database and business logic for runners. Routers call this; it never imports FastAPI.

STUB(B3): answers from the fake race in app/stubs/race.py. B3 replaces search
with a database query, and gets splits and positions from the timing service (E9).
"""

import re

from app.core.errors import AppError
from app.core.schemas import CategorySummary
from app.modules.runners.schemas import RunnerDetail, RunnerSearchItem, Split
from app.stubs import race

BIB_PATTERN = re.compile(r"^[A-Z]\d{1,4}$", re.IGNORECASE)


async def search(q: str) -> list[RunnerSearchItem]:
    q = q.strip()
    if BIB_PATTERN.match(q):
        matches = [r for r in race.runners() if r.bib_number == q.upper()]
    else:
        matches = [r for r in race.runners() if q.lower() in r.full_name.lower()]
    return [
        RunnerSearchItem(
            bib_number=r.bib_number, full_name=r.full_name, category_code=r.category_code
        )
        for r in matches[:20]
    ]


async def get_runner(bib_number: str) -> RunnerDetail:
    r = race.runner_by_bib(bib_number)
    if r is None:
        raise AppError(404, "RUNNER_NOT_FOUND", f"No runner with bib {bib_number.upper()}.")
    state = race.runner_state(r)
    cat = race.category_by_code(r.category_code)
    assert cat is not None
    position_overall, position_category = race.positions_for(r)
    return RunnerDetail(
        bib_number=r.bib_number,
        full_name=r.full_name,
        gender=r.gender,  # type: ignore[arg-type]
        category=CategorySummary(id=cat["id"], code=cat["code"], name=cat["name"]),
        status=state["status"],
        splits=[Split(**s) for s in state["splits"]],
        finish_seconds=state["finish_seconds"],
        position_overall=position_overall,
        position_category=position_category,
        live_position=state["live_position"],
    )
