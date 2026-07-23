import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import PRODUCT_UPLOAD_FIXED_COLUMNS
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
from app.modules.products.repository import ProductFilterValueRepository
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

    async def list_active(self) -> list[Filter]:
        """Every active Filter *type* (Color, Material, ...) a supplier can attach
        their own values to — Filters themselves stay admin-only to create."""
        items, _ = await self.repository.get_all(
            filters={"is_active": True}, sort_by="name", sort_order="asc", limit=None
        )
        return items

    @staticmethod
    def _check_not_reserved(name: str) -> None:
        # The bulk product upload template reserves these headers for fixed product fields —
        # a Filter sharing one of these names would make its column ambiguous to the parser.
        if name.strip().lower() in {c.lower() for c in PRODUCT_UPLOAD_FIXED_COLUMNS}:
            raise ConflictException(f'"{name}" is reserved and cannot be used as a filter name.')

    async def create(self, data: FilterCreateRequest) -> Filter:
        self._check_not_reserved(data.name)
        if await self.repository.name_taken(data.name):
            raise ConflictException("This filter name is already in use.")
        item = await self.repository.create(data.model_dump())
        return await self.get_filter(item.id)

    async def update(self, filter_id: uuid.UUID, data: FilterUpdateRequest) -> Filter:
        await self.get_filter(filter_id)
        self._check_not_reserved(data.name)
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
        self.product_filter_value_repository = ProductFilterValueRepository(session)

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

    async def get_own_value(self, value_id: uuid.UUID, supplier_id: uuid.UUID) -> FilterValue:
        """Same 404 either way (missing vs. belongs to someone else) — mirrors
        Product's get_own_product; see products/service.py."""
        item = await self.get_value(value_id)
        if item.supplier_id != supplier_id:
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

    async def _check_refs(
        self,
        data: FilterValueCreateRequest | FilterValueUpdateRequest,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if await self.filter_repository.get_by_id(data.filter_id) is None:
            raise NotFoundException("Filter")
        if await self.child_category_repository.get_by_id(data.child_category_id) is None:
            raise NotFoundException("Child category")
        if await self.supplier_repository.get_by_id(data.supplier_id) is None:
            raise NotFoundException("Supplier")
        if await self.repository.value_taken(
            data.filter_id, data.child_category_id, data.supplier_id, data.value, exclude_id=exclude_id
        ):
            raise ConflictException(
                f'"{data.value}" already exists for this filter, category, and supplier.'
            )

    async def create(self, data: FilterValueCreateRequest) -> FilterValue:
        await self._check_refs(data)
        item = await self.repository.create(data.model_dump())
        return await self.get_value(item.id)

    async def update(self, value_id: uuid.UUID, data: FilterValueUpdateRequest) -> FilterValue:
        await self.get_value(value_id)
        await self._check_refs(data, exclude_id=value_id)
        await self.repository.update(value_id, data.model_dump())
        return await self.get_value(value_id)

    async def set_status(self, value_id: uuid.UUID, is_active: bool) -> FilterValue:
        await self.get_value(value_id)
        await self.repository.update(value_id, {"is_active": is_active})
        return await self.get_value(value_id)

    async def delete(self, value_id: uuid.UUID) -> None:
        value = await self.get_value(value_id)
        product_count = await self.product_filter_value_repository.count_products_using(value_id)
        if product_count > 0:
            noun = "product" if product_count == 1 else "products"
            raise ConflictException(
                f'"{value.value}" is selected on {product_count} {noun}. Update those products before '
                "removing this filter value."
            )
        await self.repository.soft_delete(value_id)
