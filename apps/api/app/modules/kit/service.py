"""Database and business logic for kit collection. Routers call this; it never imports FastAPI.

STUB(E15): checks against the fake runners and tracker inventory; nothing is saved.
TRK-0001..0030 are already assigned, TRK-0031..0039 are free, TRK-0040 is lost.
"""

from app.core.errors import AppError
from app.modules.kit.schemas import KitAssignIn, KitAssignOut, KitReturnIn, KitReturnOut
from app.modules.trackers.service import find_by_label, list_trackers
from app.stubs import race


def _runner_for_token(token: str) -> race.FakeRunner:
    if token.startswith("STUB:"):
        rid = token.removeprefix("STUB:")
        runner = next((r for r in race.runners() if str(r.runner_id) == rid), None)
    else:
        runner = race.runner_by_bib(token)
    if runner is None:
        raise AppError(404, "RUNNER_NOT_FOUND", "That QR code does not belong to a runner.")
    return runner


def _tracker(label: str):
    tracker = find_by_label(label)
    if tracker is None:
        raise AppError(404, "TRACKER_NOT_FOUND", f"No tracker labelled {label.upper()}.")
    return tracker


async def assign(body: KitAssignIn) -> KitAssignOut:
    runner = _runner_for_token(body.qr_token)
    tracker = _tracker(body.tracker_label)
    assigned = {t.bib_number for t in await list_trackers("assigned")}
    if runner.bib_number in assigned:
        raise AppError(409, "RUNNER_HAS_TRACKER", f"{runner.bib_number} already has a tracker.")
    if tracker.status != "available":
        raise AppError(409, "TRACKER_IN_USE", f"{tracker.label} is {tracker.status}.")
    return KitAssignOut(
        bib_number=runner.bib_number, full_name=runner.full_name, tracker_label=tracker.label
    )


async def return_tracker(body: KitReturnIn) -> KitReturnOut:
    tracker = _tracker(body.tracker_label)
    if tracker.status != "assigned" or tracker.bib_number is None:
        raise AppError(409, "TRACKER_NOT_ASSIGNED", f"{tracker.label} is not out with a runner.")
    return KitReturnOut(bib_number=tracker.bib_number, tracker_label=tracker.label)
