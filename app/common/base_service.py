import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel as PydanticModel

from app.common.base_repository import BaseRepository
from app.common.pagination import PaginationParams, SortParams
from app.db.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticModel)


class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, repository: BaseRepository[ModelType]) -> None:
        self.repository = repository

    async def get_by_id(self, record_id: uuid.UUID) -> ModelType | None:
        return await self.repository.get_by_id(record_id)

    async def get_all(
        self,
        pagination: PaginationParams,
        sort: SortParams,
        *,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        search_fields: list[str] | None = None,
    ) -> tuple[list[ModelType], int]:
        return await self.repository.get_all(
            filters=filters,
            search=search,
            search_fields=search_fields,
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def create(self, schema: CreateSchemaType) -> ModelType:
        return await self.repository.create(schema.model_dump(exclude_unset=False))

    async def update(self, record_id: uuid.UUID, schema: UpdateSchemaType) -> ModelType | None:
        return await self.repository.update(record_id, schema.model_dump(exclude_unset=True))

    async def delete(self, record_id: uuid.UUID) -> bool:
        if hasattr(self.repository.model, "deleted_at"):
            return await self.repository.soft_delete(record_id)
        return await self.repository.hard_delete(record_id)
