import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.categories.repository import ChildCategoryRepository
from app.modules.filters.repository import FilterValueRepository
from app.modules.products.models import Product
from app.modules.products.repository import ProductFilterValueRepository, ProductRepository
from app.modules.products.schemas import (
    ApplicableFilterGroup,
    ProductCreateRequest,
    ProductFilterOption,
    ProductUpdateRequest,
)
from app.modules.suppliers.repository import SupplierRepository


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ProductRepository(session)
        self.child_category_repository = ChildCategoryRepository(session)
        self.supplier_repository = SupplierRepository(session)
        self.filter_value_repository = FilterValueRepository(session)
        self.product_filter_value_repository = ProductFilterValueRepository(session)

    async def list_products(
        self,
        pagination: PaginationParams,
        sort: SortParams,
        search: str | None,
        child_category_id: uuid.UUID | None,
        supplier_id: uuid.UUID | None,
    ) -> tuple[list[Product], int]:
        filters: dict = {}
        if child_category_id:
            filters["child_category_id"] = child_category_id
        if supplier_id:
            filters["supplier_id"] = supplier_id
        return await self.repository.get_all(
            filters=filters or None,
            search=search,
            search_fields=["catalog_name", "design_no", "bar_code"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_product(self, product_id: uuid.UUID) -> Product:
        item = await self.repository.get_by_id(product_id)
        if item is None:
            raise NotFoundException("Product")
        return item

    async def get_filter_value_ids(self, product_id: uuid.UUID) -> list[uuid.UUID]:
        return await self.product_filter_value_repository.get_filter_value_ids(product_id)

    async def get_applicable_filters(
        self, child_category_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[ApplicableFilterGroup]:
        values = await self.filter_value_repository.list_applicable(child_category_id, supplier_id)
        groups: dict[uuid.UUID, ApplicableFilterGroup] = {}
        for value in values:
            group = groups.setdefault(
                value.filter_id,
                ApplicableFilterGroup(filter_id=value.filter_id, filter_name=value.filter.name, options=[]),
            )
            group.options.append(ProductFilterOption(id=value.id, value=value.value))
        return sorted(groups.values(), key=lambda g: g.filter_name)

    async def list_for_export(
        self,
        search: str | None,
        child_category_id: uuid.UUID | None,
        supplier_id: uuid.UUID | None,
    ) -> list[Product]:
        filters: dict = {}
        if child_category_id:
            filters["child_category_id"] = child_category_id
        if supplier_id:
            filters["supplier_id"] = supplier_id
        return (
            await self.repository.get_all(
                filters=filters or None,
                search=search,
                search_fields=["catalog_name", "design_no", "bar_code"],
                limit=None,
            )
        )[0]

    async def _check_refs(self, data: ProductCreateRequest | ProductUpdateRequest) -> None:
        if await self.child_category_repository.get_by_id(data.child_category_id) is None:
            raise NotFoundException("Child category")
        if await self.supplier_repository.get_by_id(data.supplier_id) is None:
            raise NotFoundException("Supplier")
        unique_ids = list(dict.fromkeys(data.filter_value_ids))
        if not unique_ids:
            return
        _, matched = await self.filter_value_repository.get_all(
            filters={
                "id": unique_ids,
                "child_category_id": data.child_category_id,
                "supplier_id": data.supplier_id,
            },
            limit=len(unique_ids),
        )
        if matched != len(unique_ids):
            raise BadRequestException(
                "One or more filter values do not apply to this product's child category and supplier."
            )

    async def create(self, data: ProductCreateRequest) -> Product:
        await self._check_refs(data)
        payload = data.model_dump(exclude={"filter_value_ids"})
        item = await self.repository.create(payload)
        await self.product_filter_value_repository.replace(item.id, data.filter_value_ids)
        return await self.get_product(item.id)

    async def update(self, product_id: uuid.UUID, data: ProductUpdateRequest) -> Product:
        await self.get_product(product_id)
        await self._check_refs(data)
        payload = data.model_dump(exclude={"filter_value_ids"})
        await self.repository.update(product_id, payload)
        await self.product_filter_value_repository.replace(product_id, data.filter_value_ids)
        return await self.get_product(product_id)

    async def set_status(self, product_id: uuid.UUID, is_active: bool) -> Product:
        await self.get_product(product_id)
        await self.repository.update(product_id, {"is_active": is_active})
        return await self.get_product(product_id)

    async def delete(self, product_id: uuid.UUID) -> None:
        await self.get_product(product_id)
        await self.repository.soft_delete(product_id)
