from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.context import get_request_context
from app.common.logging import get_logger
from app.common.response import ErrorDetail, ErrorResponse

logger = get_logger(__name__)

# Add one entry per unique constraint as modules introduce them, e.g.
# "admin_users_username_key": "This username is already taken."
_UNIQUE_CONSTRAINT_MESSAGES: dict[str, str] = {}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        trace_id = get_request_context().trace_id
        constraint_name = getattr(getattr(exc, "orig", None), "constraint_name", None)
        message = _UNIQUE_CONSTRAINT_MESSAGES.get(constraint_name, None)
        if message:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(message=message, trace_id=trace_id).model_dump(),
            )
        logger.exception("unmapped_integrity_error", constraint_name=constraint_name)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message="A database error occurred.", trace_id=trace_id).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = get_request_context().trace_id
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(message=str(exc.detail), trace_id=trace_id).model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = get_request_context().trace_id
        errors = [
            ErrorDetail(field=".".join(str(part) for part in error["loc"]), message=error["msg"])
            for error in exc.errors()
        ]
        message = f"{errors[0].field}: {errors[0].message}" if len(errors) == 1 else "Validation error."
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(message=message, errors=errors, trace_id=trace_id).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = get_request_context().trace_id
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message="An unexpected error occurred.", trace_id=trace_id).model_dump(),
        )
