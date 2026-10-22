"""File storage. Owner: Lead (E6).

Files live in the `stored_files` table and are served at
`/api/v1/files/<key>`. To move to Cloudinary or S3 later, only this module
changes: callers just save bytes and get back a URL.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import settings
from app.models import StoredFile


def private_key(prefix: str, name: str, extension: str) -> str:
    """A storage key with a random token, so the file's URL can't be guessed."""
    return f"{prefix}/{name}-{secrets.token_urlsafe(16)}.{extension}"


def file_url(key: str) -> str:
    return f"{settings.public_api_url}/api/v1/files/{key}"


async def save_file(session: AsyncSession, key: str, data: bytes, content_type: str) -> str:
    """Store `data` under `key` (replacing any file with that key). Returns its URL.

    Doesn't commit: it is saved together with whatever else the caller commits.
    """
    values = {"content_type": content_type, "size_bytes": len(data), "data": data}
    await session.execute(
        insert(StoredFile)
        .values(key=key, **values)
        .on_conflict_do_update(index_elements=[StoredFile.key], set_=values)
    )
    return file_url(key)


async def load_file(session: AsyncSession, key: str) -> StoredFile | None:
    """The file with its contents, or None."""
    return await session.scalar(
        select(StoredFile).where(StoredFile.key == key).options(undefer(StoredFile.data))
    )
