import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import NotFoundException
from app.modules.categories.repository import ChildCategoryRepository
from app.modules.filters.repository import FilterValueRepository
from app.modules.products.models import Product
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreateRequest, ProductUpdateRequest
from app.modules.suppliers.repository import SupplierRepository


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ProductRepository(session)
        self.child_category_repository = ChildCategoryRepository(session)
        self.supplier_repository = SupplierRepository(session)
        self.filter_value_repository = FilterValueRepository(session)

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
        if await self.filter_value_repository.get_by_id(data.shine_fabric_value_id) is None:
            raise NotFoundException("Shine Fabric value")
        if await self.filter_value_repository.get_by_id(data.fabric_transparency_value_id) is None:
            raise NotFoundException("Fabric Transparency value")

    async def create(self, data: ProductCreateRequest) -> Product:
        await self._check_refs(data)
        item = await self.repository.create(data.model_dump())
        return await self.get_product(item.id)

    async def update(self, product_id: uuid.UUID, data: ProductUpdateRequest) -> Product:
        await self.get_product(product_id)
        await self._check_refs(data)
        await self.repository.update(product_id, data.model_dump())
        return await self.get_product(product_id)

    async def set_status(self, product_id: uuid.UUID, is_active: bool) -> Product:
        await self.get_product(product_id)
        await self.repository.update(product_id, {"is_active": is_active})
        return await self.get_product(product_id)

    async def delete(self, product_id: uuid.UUID) -> None:
        await self.get_product(product_id)
        await self.repository.soft_delete(product_id)
