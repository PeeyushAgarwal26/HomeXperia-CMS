import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import ConflictException, NotFoundException
from app.modules.categories.repository import ChildCategoryRepository
from app.modules.filters.models import Filter, FilterValue
from app.modules.filters.repository import FilterRepository, FilterValueRepository
from app.modules.filters.schemas import (
    FilterCreateRequest,
    FilterUpdateRequest,
    FilterValueCreateRequest,
    FilterValueUpdateRequest,
)
from app.modules.products.repository import ProductRepository
from app.modules.suppliers.repository import SupplierRepository


class FilterService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = FilterRepository(session)
        self.value_repository = FilterValueRepository(session)

    async def list_filters(
        self, pagination: PaginationParams, sort: SortParams, search: str | None
    ) -> tuple[list[Filter], int]:
        return await self.repository.get_all(
            search=search,
            search_fields=["name"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_filter(self, filter_id: uuid.UUID) -> Filter:
        item = await self.repository.get_by_id(filter_id)
        if item is None:
            raise NotFoundException("Filter")
        return item

    async def create(self, data: FilterCreateRequest) -> Filter:
        if await self.repository.name_taken(data.name):
            raise ConflictException("This filter name is already in use.")
        item = await self.repository.create(data.model_dump())
        return await self.get_filter(item.id)

    async def update(self, filter_id: uuid.UUID, data: FilterUpdateRequest) -> Filter:
        await self.get_filter(filter_id)
        if await self.repository.name_taken(data.name, exclude_id=filter_id):
            raise ConflictException("This filter name is already in use.")
        await self.repository.update(filter_id, data.model_dump())
        return await self.get_filter(filter_id)

    async def set_status(self, filter_id: uuid.UUID, is_active: bool) -> Filter:
        await self.get_filter(filter_id)
        await self.repository.update(filter_id, {"is_active": is_active})
        return await self.get_filter(filter_id)

    async def delete(self, filter_id: uuid.UUID) -> None:
        await self.get_filter(filter_id)
        _, value_count = await self.value_repository.get_all(filters={"filter_id": filter_id}, limit=1)
        if value_count > 0:
            raise ConflictException("This filter still has values — remove or reassign them first.")
        await self.repository.soft_delete(filter_id)


class FilterValueService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = FilterValueRepository(session)
        self.filter_repository = FilterRepository(session)
        self.child_category_repository = ChildCategoryRepository(session)
        self.supplier_repository = SupplierRepository(session)
        self.product_repository = ProductRepository(session)

    async def list_values(
        self,
        pagination: PaginationParams,
        sort: SortParams,
        search: str | None,
        filter_id: uuid.UUID | None,
        child_category_id: uuid.UUID | None,
        supplier_id: uuid.UUID | None,
    ) -> tuple[list[FilterValue], int]:
        filters: dict = {}
        if filter_id:
            filters["filter_id"] = filter_id
        if child_category_id:
            filters["child_category_id"] = child_category_id
        if supplier_id:
            filters["supplier_id"] = supplier_id
        return await self.repository.get_all(
            filters=filters or None,
            search=search,
            search_fields=["value"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_value(self, value_id: uuid.UUID) -> FilterValue:
        item = await self.repository.get_by_id(value_id)
        if item is None:
            raise NotFoundException("Filter value")
        return item

    async def list_for_export(
        self,
        search: str | None,
        filter_id: uuid.UUID | None,
        child_category_id: uuid.UUID | None,
        supplier_id: uuid.UUID | None,
    ) -> list[FilterValue]:
        filters: dict = {}
        if filter_id:
            filters["filter_id"] = filter_id
        if child_category_id:
            filters["child_category_id"] = child_category_id
        if supplier_id:
            filters["supplier_id"] = supplier_id
        return (
            await self.repository.get_all(
                filters=filters or None, search=search, search_fields=["value"], limit=None
            )
        )[0]

    async def _check_refs(self, data: FilterValueCreateRequest | FilterValueUpdateRequest) -> None:
        if await self.filter_repository.get_by_id(data.filter_id) is None:
            raise NotFoundException("Filter")
        if await self.child_category_repository.get_by_id(data.child_category_id) is None:
            raise NotFoundException("Child category")
        if await self.supplier_repository.get_by_id(data.supplier_id) is None:
            raise NotFoundException("Supplier")

    async def create(self, data: FilterValueCreateRequest) -> FilterValue:
        await self._check_refs(data)
        item = await self.repository.create(data.model_dump())
        return await self.get_value(item.id)

    async def update(self, value_id: uuid.UUID, data: FilterValueUpdateRequest) -> FilterValue:
        await self.get_value(value_id)
        await self._check_refs(data)
        await self.repository.update(value_id, data.model_dump())
        return await self.get_value(value_id)

    async def set_status(self, value_id: uuid.UUID, is_active: bool) -> FilterValue:
        await self.get_value(value_id)
        await self.repository.update(value_id, {"is_active": is_active})
        return await self.get_value(value_id)

    async def delete(self, value_id: uuid.UUID) -> None:
        value = await self.get_value(value_id)
        _, shine_count = await self.product_repository.get_all(
            filters={"shine_fabric_value_id": value_id}, limit=1
        )
        _, transparency_count = await self.product_repository.get_all(
            filters={"fabric_transparency_value_id": value_id}, limit=1
        )
        product_count = shine_count + transparency_count
        if product_count > 0:
            noun = "product" if product_count == 1 else "products"
            raise ConflictException(
                f'"{value.value}" is used as the Shine Fabric or Fabric Transparency value on '
                f"{product_count} {noun}. Update those products before removing this filter value."
            )
        await self.repository.soft_delete(value_id)
