import math
from typing import Any

from fastapi import HTTPException, status

from app.common.response import APIResponse, PaginationMeta


class BaseController:
    def success(self, data: Any = None, message: str = "Success", meta: dict[str, Any] | None = None) -> APIResponse:
        return APIResponse.ok(data=data, message=message, meta=meta)

    def paginated(
        self,
        data: list[Any],
        total: int,
        page: int | None,
        page_size: int | None,
        message: str = "Success",
    ) -> APIResponse:
        total_pages = math.ceil(total / page_size) if page_size else None
        meta = PaginationMeta(total=total, page=page, page_size=page_size, total_pages=total_pages).model_dump()
        return APIResponse.ok(data=data, message=message, meta=meta)

    def not_found(self, resource: str = "Resource") -> HTTPException:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found.")

    def require_exists(self, obj: Any, resource: str = "Resource") -> Any:
        if obj is None:
            raise self.not_found(resource)
        return obj

    def bad_request(self, message: str) -> HTTPException:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    def forbidden(self, message: str = "Forbidden") -> HTTPException:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)
