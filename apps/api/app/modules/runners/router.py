"""runners endpoints. Owner: Backend (B3)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.schemas import error_responses
from app.modules.runners import service
from app.modules.runners.schemas import RunnerDetail, RunnerSearchItem

router = APIRouter(prefix="/runners", tags=["runners"])


@router.get("/search", responses=error_responses(422))
async def search(
    q: Annotated[str, Query(min_length=2, description="A name or a bib number")],
) -> list[RunnerSearchItem]:
    return await service.search(q)


@router.get("/{bib_number}", responses=error_responses(404))
async def get_runner(bib_number: str) -> RunnerDetail:
    return await service.get_runner(bib_number)
