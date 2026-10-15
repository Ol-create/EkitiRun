"""Sending SMS. Owner: Lead (E3).

- `ConsoleSmsSender` (development): prints the message to the API log
  (`docker compose logs -f api`) instead of sending it.
- `TermiiSmsSender` (production): sends through Termii's SMS API on the DND
  route, which reaches numbers that block promotional SMS.
"""

from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from app.core.config import settings


class SmsSendError(Exception):
    pass


class SmsSender(Protocol):
    async def send(self, phone: str, message: str) -> None: ...


class ConsoleSmsSender:
    async def send(self, phone: str, message: str) -> None:
        print(f"[sms:console] to {phone}: {message}", flush=True)


class TermiiSmsSender:
    def __init__(
        self,
        api_key: str,
        sender_id: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.sender_id = sender_id
        self.base_url = base_url.rstrip("/")
        self.transport = transport  # tests pass httpx.MockTransport

    async def send(self, phone: str, message: str) -> None:
        payload = {
            "api_key": self.api_key,
            "to": phone.removeprefix("+"),  # Termii wants 2348031234567
            "from": self.sender_id,
            "sms": message,
            "type": "plain",
            "channel": "dnd",
        }
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10) as client:
                response = await client.post(f"{self.base_url}/api/sms/send", json=payload)
        except httpx.HTTPError as exc:
            raise SmsSendError(f"Termii unreachable: {exc}") from exc
        if response.status_code != 200 or "message_id" not in response.text:
            raise SmsSendError(f"Termii rejected the SMS ({response.status_code}): {response.text}")


def get_sms_sender() -> SmsSender:
    if settings.sms_provider == "termii":
        return TermiiSmsSender(
            settings.termii_api_key, settings.termii_sender_id, settings.termii_base_url
        )
    return ConsoleSmsSender()


SmsSenderDep = Annotated[SmsSender, Depends(get_sms_sender)]
