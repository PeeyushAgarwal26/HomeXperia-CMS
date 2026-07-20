import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    def _base_select(self) -> Select:
        stmt = select(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    async def get_by_id(self, record_id: uuid.UUID, *, populate_existing: bool = False) -> ModelType | None:
        stmt = self._base_select().where(self.model.id == record_id)
        if populate_existing:
            stmt = stmt.execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        filters: dict[str, Any] | None = None,
        search_fields: list[str] | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[ModelType], int]:
        stmt = self._base_select()

        if filters:
            for field_name, value in filters.items():
                column = getattr(self.model, field_name)
                stmt = stmt.where(column.in_(value) if isinstance(value, list) else column == value)

        if search and search_fields:
            column_matches = [getattr(self.model, field_name).ilike(f"%{search}%") for field_name in search_fields]
            stmt = stmt.where(or_(*column_matches))

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))

        sort_column = getattr(self.model, sort_by, None) or self.model.created_at
        stmt = stmt.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0

    async def create(self, data: dict[str, Any]) -> ModelType:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, record_id: uuid.UUID, data: dict[str, Any]) -> ModelType | None:
        payload = {**data, "updated_at": datetime.now(timezone.utc)}
        stmt = (
            update(self.model)
            .where(self.model.id == record_id)
            .values(**payload)
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)
        # synchronize_session=False means a bulk UPDATE never touches an
        # already-identity-mapped instance's in-memory attributes — without
        # populate_existing, this refetch would silently hand back the
        # pre-update object whenever the row was already loaded earlier in
        # the same request (e.g. a permission check that fetched it first).
        return await self.get_by_id(record_id, populate_existing=True)

    async def soft_delete(self, record_id: uuid.UUID) -> bool:
        if not hasattr(self.model, "deleted_at"):
            raise TypeError(f"{self.model.__name__} has no deleted_at column")
        stmt = (
            update(self.model)
            .where(self.model.id == record_id, self.model.deleted_at.is_(None))
            .values(deleted_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def hard_delete(self, record_id: uuid.UUID) -> bool:
        instance = await self.get_by_id(record_id)
        if instance is None:
            return False
        await self.session.delete(instance)
        return True

    async def exists(self, **kwargs: Any) -> bool:
        stmt = self._base_select()
        for field_name, value in kwargs.items():
            stmt = stmt.where(getattr(self.model, field_name) == value)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None
