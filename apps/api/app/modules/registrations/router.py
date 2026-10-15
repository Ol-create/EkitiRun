"""registrations endpoints. Owner: Lead (E4)."""

import uuid

from fastapi import APIRouter, Response

from app.core.schemas import error_responses
from app.modules.registrations import service
from app.modules.registrations.schemas import RegistrationIn, RegistrationOut

router = APIRouter(prefix="/registrations", tags=["registrations"])


@router.post("", status_code=201, responses=error_responses(401, 404, 409, 422))
async def register(body: RegistrationIn) -> RegistrationOut:
    return await service.register(body)


@router.get(
    "/{runner_id}/qr.png",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def qr_png(runner_id: uuid.UUID) -> Response:
    return Response(service.qr_png(runner_id), media_type="image/png")
