from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    page: int | None
    page_size: int | None
    total_pages: int | None


class APIResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: T | None = None
    meta: dict[str, Any] | None = None

    @classmethod
    def ok(cls, data: T | None = None, message: str = "Success", meta: dict[str, Any] | None = None) -> "APIResponse[T]":
        return cls(success=True, message=message, data=data, meta=meta)


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: list[ErrorDetail] | None = None
    trace_id: str | None = None
