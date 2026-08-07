import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import BadRequestException, ConflictException, NotFoundException
from app.modules.categories.repository import ChildCategoryRepository
from app.modules.customers.models import Customer
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.filters.repository import FilterValueRepository
from app.modules.products.models import Product
from app.modules.products.repository import ProductFilterValueRepository, ProductRepository
from app.modules.products.schemas import (
    ApplicableFilterGroup,
    ProductCreateRequest,
    ProductCustomerItem,
    ProductFilterOption,
    ProductFilterValueDetail,
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
        self.customer_supplier_repository = CustomerSupplierRepository(session)

    async def _resolve_visible_supplier_ids(self, customer: Customer | None) -> list[uuid.UUID] | None:
        """None = unscoped (anonymous/Shopify-embed caller — no customer
        identity to scope by, unchanged from today). A real customer sees
        only the suppliers they're mapped to (Map Suppliers) plus their own,
        if they're themselves a linked supplier identity — an empty list here
        correctly yields zero products, not everything."""
        if customer is None:
            return None
        supplier_ids = list(await self.customer_supplier_repository.get_supplier_ids(customer.id))
        if customer.linked_supplier_id is not None:
            supplier_ids.append(customer.linked_supplier_id)
        return supplier_ids

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

    async def get_own_product(self, product_id: uuid.UUID, supplier_id: uuid.UUID) -> Product:
        """Same 404 either way (missing vs. belongs to someone else) — a
        supplier probing another supplier's product id shouldn't be able to
        tell the difference from a typo."""
        item = await self.get_product(product_id)
        if item.supplier_id != supplier_id:
            raise NotFoundException("Product")
        return item

    async def get_filter_value_ids(self, product_id: uuid.UUID) -> list[uuid.UUID]:
        return await self.product_filter_value_repository.get_filter_value_ids(product_id)

    async def get_filter_value_details(
        self, filter_value_ids: list[uuid.UUID]
    ) -> list[ProductFilterValueDetail]:
        """Names, not just ids — for the read-only Product Details view, which
        shows "Color: Red" rather than a raw FilterValue id."""
        if not filter_value_ids:
            return []
        values, _ = await self.filter_value_repository.get_all(
            filters={"id": filter_value_ids}, limit=len(filter_value_ids)
        )
        details = [
            ProductFilterValueDetail(
                filter_id=v.filter_id, filter_name=v.filter.name, value_id=v.id, value=v.value
            )
            for v in values
        ]
        return sorted(details, key=lambda d: d.filter_name)

    async def get_applicable_filters(
        self, child_category_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[ApplicableFilterGroup]:
        values = await self.filter_value_repository.list_applicable(child_category_id, supplier_id)
        return self._group_filter_values(values)

    async def get_customer_applicable_filters(
        self, child_category_id: uuid.UUID, customer: Customer | None
    ) -> list[ApplicableFilterGroup]:
        visible_supplier_ids = await self._resolve_visible_supplier_ids(customer)
        values = await self.filter_value_repository.list_applicable_for_category(
            child_category_id, visible_supplier_ids
        )
        return self._group_filter_values(values)

    @staticmethod
    def _group_filter_values(values: list) -> list[ApplicableFilterGroup]:
        groups: dict[uuid.UUID, ApplicableFilterGroup] = {}
        for value in values:
            group = groups.setdefault(
                value.filter_id,
                ApplicableFilterGroup(filter_id=value.filter_id, filter_name=value.filter.name, options=[]),
            )
            group.options.append(ProductFilterOption(id=value.id, value=value.value))
        return sorted(groups.values(), key=lambda g: g.filter_name)

    async def list_customer_products(
        self,
        child_category_id: uuid.UUID | None,
        search: str | None,
        min_price: float | None,
        max_price: float | None,
        filter_value_ids: list[uuid.UUID],
        offset: int,
        limit: int | None,
        customer: Customer | None,
    ) -> tuple[list[ProductCustomerItem], int]:
        visible_supplier_ids = await self._resolve_visible_supplier_ids(customer)
        items, total = await self.repository.list_for_customer(
            child_category_id, search, min_price, max_price, filter_value_ids, offset, limit, visible_supplier_ids
        )
        data = [
            ProductCustomerItem(
                product_id=item.id,
                product_name=item.catalog_name,
                catalog_name=item.catalog_name,
                design_no=item.design_no,
                product_image=item.image_url,
                thumbnail=item.image_url,
                rate=item.rate,
                width=item.width,
                length=item.length,
                child_category_id=item.child_category_id,
            )
            for item in items
        ]
        return data, total

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

    async def _check_refs(
        self, data: ProductCreateRequest | ProductUpdateRequest, exclude_id: uuid.UUID | None = None
    ) -> None:
        if await self.child_category_repository.get_by_id(data.child_category_id) is None:
            raise NotFoundException("Child category")
        if await self.supplier_repository.get_by_id(data.supplier_id) is None:
            raise NotFoundException("Supplier")
        existing = await self.repository.get_by_supplier_and_bar_code(data.supplier_id, data.bar_code)
        if existing is not None and existing.id != exclude_id:
            raise ConflictException(
                f'A product with Bar Code "{data.bar_code}" already exists for this supplier.'
            )
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
        await self._check_refs(data, exclude_id=product_id)
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
