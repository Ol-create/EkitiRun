"""One error shape for the whole API: `{"detail": "...", "code": "MACHINE_CODE"}`. Owner: Lead.

Raise `AppError` from services for expected failures:

    raise AppError(409, "CATEGORY_FULL", "This category is full")
"""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def error_body(code: str, detail: str, **extra: object) -> dict[str, object]:
    return {"detail": detail, "code": code, **extra}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.detail), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
        detail = f"{field}: {first.get('msg', 'Invalid request')}"
        # `errors` keeps the per-field list so forms can show messages under each field.
        body = error_body("VALIDATION_ERROR", detail, errors=jsonable_errors(errors))
        return JSONResponse(body, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            error_body(f"HTTP_{exc.status_code}", str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )


def jsonable_errors(errors: Sequence[Any]) -> list[dict[str, object]]:
    return [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in errors
    ]
