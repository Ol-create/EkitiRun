"""categories endpoints. Owner: Lead (example module) + Backend (B3)."""

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.schemas import error_responses
from app.modules.categories import service
from app.modules.categories.schemas import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(session: SessionDep) -> list[CategoryOut]:
    return await service.list_categories(session)


@router.get("/{category_id}", responses=error_responses(404))
async def get_category(category_id: int, session: SessionDep) -> CategoryOut:
    return await service.get_category(session, category_id)
