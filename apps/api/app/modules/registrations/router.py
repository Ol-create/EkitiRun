"""registrations endpoints. Owner: Lead (E4)."""

import uuid

from fastapi import APIRouter, Response

from app.core.deps import SessionDep
from app.core.schemas import error_responses
from app.modules.registrations import service
from app.modules.registrations.schemas import RegistrationIn, RegistrationOut

router = APIRouter(prefix="/registrations", tags=["registrations"])


@router.post("", status_code=201, responses=error_responses(401, 404, 409, 422))
async def register(body: RegistrationIn, session: SessionDep) -> RegistrationOut:
    return await service.register(session, body)


@router.get(
    "/{runner_id}/qr.png",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, **error_responses(404)},
)
async def qr_png(runner_id: uuid.UUID, session: SessionDep) -> Response:
    # The runner id is unguessable, so the link itself is the access check.
    return Response(
        await service.qr_png(session, runner_id),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )
