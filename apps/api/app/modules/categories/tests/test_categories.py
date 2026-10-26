"""Example tests: copy this style. Each test builds the rows it needs, then calls the API.

`db_client` is the HTTP client wired to a rolled-back test transaction, and
`session` is the same transaction, for inserting test data.
"""

from decimal import Decimal

from app.models import Category, Route


async def make_category(session, code="HALF", sort_order=1, **overrides) -> Category:
    route = Route(
        name=f"{code} course",
        geojson={"type": "LineString", "coordinates": [[5.0, 7.0], [5.1, 7.1]]},
        length_km=Decimal("21.0975"),
    )
    session.add(route)
    await session.flush()
    category = Category(
        code=code,
        name=f"{code} race",
        distance_km=Decimal("21.0975"),
        cap=100,
        bib_prefix=code[0],
        route_id=route.id,
        sort_order=sort_order,
        **overrides,
    )
    session.add(category)
    await session.flush()
    return category


async def test_list_categories_is_empty_without_data(db_client):
    response = await db_client.get("/api/v1/categories")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_categories_in_sort_order(db_client, session):
    await make_category(session, "HALF", sort_order=2)
    await make_category(session, "FULL", sort_order=1)

    response = await db_client.get("/api/v1/categories")

    assert response.status_code == 200
    body = response.json()
    assert [c["code"] for c in body] == ["FULL", "HALF"]
    assert body[0] == {
        "id": body[0]["id"],
        "code": "FULL",
        "name": "FULL race",
        "distance_km": 21.0975,
        "cap": 100,
        "slots_left": 100,
        "is_full": False,
        "gun_start_at": None,
    }


async def test_get_category(db_client, session):
    category = await make_category(session)

    response = await db_client.get(f"/api/v1/categories/{category.id}")

    assert response.status_code == 200
    assert response.json()["code"] == "HALF"


async def test_get_unknown_category_is_404(db_client):
    response = await db_client.get("/api/v1/categories/999999")

    assert response.status_code == 404
    assert response.json()["code"] == "CATEGORY_NOT_FOUND"
