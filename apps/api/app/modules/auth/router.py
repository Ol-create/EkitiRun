"""auth endpoints. Owner: Lead (E3)."""

from fastapi import APIRouter, Response

from app.core.schemas import error_responses
from app.modules.auth import service
from app.modules.auth.schemas import OtpRequestIn, OtpVerifyIn, OtpVerifyOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", status_code=204, responses=error_responses(429))
async def request_otp(body: OtpRequestIn) -> Response:
    await service.request_otp(body.phone)
    return Response(status_code=204)


@router.post("/otp/verify", responses=error_responses(400))
async def verify_otp(body: OtpVerifyIn) -> OtpVerifyOut:
    token = await service.verify_otp(body.phone, body.code)
    return OtpVerifyOut(verification_token=token)
