"""route endpoints. Owner: Lead (E10)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.schemas import error_responses
from app.modules.route import service
from app.modules.route.schemas import RouteOut

router = APIRouter(prefix="/route", tags=["route"])


@router.get("", responses=error_responses(404))
async def get_route(
    category: Annotated[str, Query(description="Category code, e.g. FULL")] = "FULL",
) -> RouteOut:
    return await service.get_route(category)
