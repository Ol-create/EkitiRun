"""sponsors endpoints. Owner: Backend (B1, B2)."""

from fastapi import APIRouter, Response

from app.core.deps import AdminDep
from app.core.schemas import error_responses
from app.modules.sponsors import service
from app.modules.sponsors.schemas import (
    PledgeCreated,
    PledgeIn,
    PledgeStatusOut,
    SponsorTierIn,
    SponsorTierOut,
    SponsorTierPatch,
)

router = APIRouter(tags=["sponsors"])


@router.get("/sponsor-tiers")
async def list_tiers() -> list[SponsorTierOut]:
    return await service.list_tiers()


@router.post(
    "/admin/sponsor-tiers",
    status_code=201,
    dependencies=[AdminDep],
    responses=error_responses(401),
)
async def create_tier(body: SponsorTierIn) -> SponsorTierOut:
    return await service.create_tier(body)


@router.patch(
    "/admin/sponsor-tiers/{tier_id}",
    dependencies=[AdminDep],
    responses=error_responses(401, 404),
)
async def update_tier(tier_id: int, body: SponsorTierPatch) -> SponsorTierOut:
    return await service.update_tier(tier_id, body)


@router.delete(
    "/admin/sponsor-tiers/{tier_id}",
    status_code=204,
    dependencies=[AdminDep],
    responses=error_responses(401, 404),
)
async def delete_tier(tier_id: int) -> Response:
    await service.delete_tier(tier_id)
    return Response(status_code=204)


@router.post("/sponsors/pledges", status_code=201, responses=error_responses(404, 422))
async def create_pledge(body: PledgeIn) -> PledgeCreated:
    return await service.create_pledge(body)


@router.get("/sponsors/pledges/{reference}", responses=error_responses(404))
async def get_pledge(reference: str) -> PledgeStatusOut:
    return await service.get_pledge(reference)
