"""PDF jobs. Owner: Lead (E6). Templates live in app/templates/pdf (Backend, B4)."""


async def render_invoice(ctx: dict, pledge_id: str) -> None:
    raise NotImplementedError


async def render_receipt(ctx: dict, pledge_id: str) -> None:
    raise NotImplementedError
