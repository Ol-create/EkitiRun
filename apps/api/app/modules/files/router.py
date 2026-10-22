"""Serves stored files (sponsor invoices and receipts). Owner: Lead (E6)."""

from fastapi import APIRouter, Response

from app.core.deps import SessionDep
from app.core.errors import AppError
from app.core.schemas import error_responses
from app.core.storage import load_file

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/{key:path}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, **error_responses(404)},
)
async def get_file(key: str, session: SessionDep) -> Response:
    stored = await load_file(session, key)
    if stored is None:
        raise AppError(404, "FILE_NOT_FOUND", "That file does not exist.")
    filename = key.rsplit("/", 1)[-1]
    return Response(
        stored.data,
        media_type=stored.content_type,
        headers={
            # The random key is the access check, so keep it out of shared caches.
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
