"""Database and business logic for categories. Routers call this; it never imports FastAPI.

This is the EXAMPLE MODULE: copy its layout for new modules.
- router.py: HTTP only (paths, status codes, dependencies). No queries.
- schemas.py: request and response models.
- service.py: queries and rules. Takes a session, returns schemas or raises AppError.
- tests/: one test file per endpoint group.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Category
from app.modules.categories.schemas import CategoryOut


def _to_out(category: Category, registered: int) -> CategoryOut:
    slots_left = max(category.cap - registered, 0)
    return CategoryOut(
        id=category.id,
        code=category.code,
        name=category.name,
        distance_km=float(category.distance_km),
        cap=category.cap,
        slots_left=slots_left,
        is_full=slots_left == 0,
    )


async def list_categories(session: AsyncSession) -> list[CategoryOut]:
    result = await session.scalars(select(Category).order_by(Category.sort_order, Category.id))
    # TODO(B3): count registered runners per category in the same query
    # (outer join runners + GROUP BY), instead of assuming 0.
    return [_to_out(c, registered=0) for c in result]


async def get_category(session: AsyncSession, category_id: int) -> CategoryOut:
    category = await session.get(Category, category_id)
    if category is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", "That category does not exist.")
    return _to_out(category, registered=0)
