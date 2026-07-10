from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class PaginationParams(BaseModel):
    page: Annotated[int | None, Query(ge=1)] = 1
    page_size: Annotated[int | None, Query(ge=1, le=100)] = 10

    @property
    def offset(self) -> int:
        if self.page is None or self.page_size is None:
            return 0
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int | None:
        return self.page_size


class SortParams(BaseModel):
    sort_by: Annotated[str, Query()] = "created_at"
    sort_order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc"


class FilterParams(BaseModel):
    search: Annotated[str | None, Query()] = None
