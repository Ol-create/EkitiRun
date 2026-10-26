"""auth endpoints. Owner: Lead (E3)."""

from fastapi import APIRouter, Request, Response

from app.core.deps import SessionDep
from app.core.redis import RedisDep
from app.core.schemas import error_responses
from app.core.sms import SmsSenderDep
from app.modules.auth import service
from app.modules.auth.schemas import OtpRequestIn, OtpVerifyIn, OtpVerifyOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", status_code=204, responses=error_responses(429, 502))
async def request_otp(
    body: OtpRequestIn,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    sms: SmsSenderDep,
) -> Response:
    # Behind the hosting load balancer, uvicorn runs with --proxy-headers (Dockerfile),
    # so this is the runner's IP, not the balancer's.
    client_ip = request.client.host if request.client else "unknown"
    await service.request_otp(session, redis, sms, body.phone, client_ip)
    return Response(status_code=204)


@router.post("/otp/verify", responses=error_responses(400, 429))
async def verify_otp(body: OtpVerifyIn, session: SessionDep) -> OtpVerifyOut:
    token = await service.verify_otp(session, body.phone, body.code)
    return OtpVerifyOut(verification_token=token)
