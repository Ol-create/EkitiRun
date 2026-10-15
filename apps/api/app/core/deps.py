"""Shared FastAPI dependencies. Owner: Lead.

Newbies import from here (e.g. `require_admin`) but don't change it.
"""

from fastapi import HTTPException, status


async def require_admin() -> None:
    # TODO(Lead, E3): verify the admin JWT.
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin auth not implemented yet")
