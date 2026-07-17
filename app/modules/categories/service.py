import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import ConflictException, NotFoundException
from app.modules.categories.models import ChildCategory, ParentCategory
from app.modules.categories.repository import CategoryRepository, ChildCategoryRepository, ParentCategoryRepository
from app.modules.categories.schemas import (
    ChildCategoryCreateRequest,
    ChildCategoryItem,
    ChildCategoryUpdateRequest,
    ParentCategoryCreateRequest,
    ParentCategoryNode,
    ParentCategoryUpdateRequest,
)
from app.modules.filters.repository import FilterValueRepository
from app.modules.products.repository import ProductRepository


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = CategoryRepository(session)

    async def get_tree(self) -> list[ParentCategoryNode]:
        parents = await self.repository.list_parents()
        children = await self.repository.list_children()
        return [
            ParentCategoryNode(
                id=parent.id,
                name=parent.name,
                children=[
                    ChildCategoryItem(id=child.id, name=child.name)
                    for child in children
                    if child.parent_category_id == parent.id
                ],
            )
            for parent in parents
        ]


class ParentCategoryService:
    """Full Add/Edit/Delete + Activate/Deactivate — deliberately more open than
    the reference UI, see docs/06-legacy-site-audit.md §8 and models.py."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = ParentCategoryRepository(session)
        self.child_repository = ChildCategoryRepository(session)

    async def list_parents(
        self, pagination: PaginationParams, sort: SortParams, search: str | None
    ) -> tuple[list[ParentCategory], int]:
        return await self.repository.get_all(
            search=search,
            search_fields=["name"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_parent(self, parent_id: uuid.UUID) -> ParentCategory:
        parent = await self.repository.get_by_id(parent_id)
        if parent is None:
            raise NotFoundException("Parent category")
        return parent

    async def create(self, data: ParentCategoryCreateRequest) -> ParentCategory:
        if await self.repository.name_taken(data.name):
            raise ConflictException("This category name is already in use.")
        parent = await self.repository.create(data.model_dump())
        return await self.get_parent(parent.id)

    async def update(self, parent_id: uuid.UUID, data: ParentCategoryUpdateRequest) -> ParentCategory:
        await self.get_parent(parent_id)
        if await self.repository.name_taken(data.name, exclude_id=parent_id):
            raise ConflictException("This category name is already in use.")
        await self.repository.update(parent_id, data.model_dump())
        return await self.get_parent(parent_id)

    async def set_status(self, parent_id: uuid.UUID, is_active: bool) -> ParentCategory:
        await self.get_parent(parent_id)
        await self.repository.update(parent_id, {"is_active": is_active})
        return await self.get_parent(parent_id)

    async def delete(self, parent_id: uuid.UUID) -> None:
        parent = await self.get_parent(parent_id)
        _, child_count = await self.child_repository.get_all(
            filters={"parent_category_id": parent_id}, limit=1
        )
        if child_count > 0:
            noun = "child category" if child_count == 1 else "child categories"
            raise ConflictException(
                f'"{parent.name}" has {child_count} {noun} assigned to it. Delete those child '
                "categories or reassign them to a different parent category before removing this one."
            )
        await self.repository.soft_delete(parent_id)


class ChildCategoryService:
    """Full Add/Edit + Activate/Deactivate. Still no delete, matching the reference."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = ChildCategoryRepository(session)
        self.parent_repository = ParentCategoryRepository(session)
        self.product_repository = ProductRepository(session)
        self.filter_value_repository = FilterValueRepository(session)

    async def list_children(
        self,
        pagination: PaginationParams,
        sort: SortParams,
        search: str | None,
        parent_category_id: uuid.UUID | None,
    ) -> tuple[list[ChildCategory], int]:
        filters = {"parent_category_id": parent_category_id} if parent_category_id else None
        return await self.repository.get_all(
            filters=filters,
            search=search,
            search_fields=["name"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_child(self, child_id: uuid.UUID) -> ChildCategory:
        child = await self.repository.get_by_id(child_id)
        if child is None:
            raise NotFoundException("Child category")
        return child

    async def _check_parent_exists(self, parent_category_id: uuid.UUID) -> None:
        parent = await self.parent_repository.get_by_id(parent_category_id)
        if parent is None:
            raise NotFoundException("Parent category")

    async def create(self, data: ChildCategoryCreateRequest) -> ChildCategory:
        await self._check_parent_exists(data.parent_category_id)
        if await self.repository.name_taken(data.parent_category_id, data.name):
            raise ConflictException("This category name is already in use under the selected parent category.")
        child = await self.repository.create(data.model_dump())
        return await self.get_child(child.id)

    async def update(self, child_id: uuid.UUID, data: ChildCategoryUpdateRequest) -> ChildCategory:
        await self.get_child(child_id)
        await self._check_parent_exists(data.parent_category_id)
        if await self.repository.name_taken(data.parent_category_id, data.name, exclude_id=child_id):
            raise ConflictException("This category name is already in use under the selected parent category.")
        await self.repository.update(child_id, data.model_dump())
        return await self.get_child(child_id)

    async def set_status(self, child_id: uuid.UUID, is_active: bool) -> ChildCategory:
        await self.get_child(child_id)
        await self.repository.update(child_id, {"is_active": is_active})
        return await self.get_child(child_id)

    async def delete(self, child_id: uuid.UUID) -> None:
        child = await self.get_child(child_id)
        _, product_count = await self.product_repository.get_all(
            filters={"child_category_id": child_id}, limit=1
        )
        if product_count > 0:
            noun = "product" if product_count == 1 else "products"
            raise ConflictException(
                f'"{child.name}" has {product_count} {noun} assigned to it. Move or delete those '
                "products before removing this child category."
            )
        _, filter_value_count = await self.filter_value_repository.get_all(
            filters={"child_category_id": child_id}, limit=1
        )
        if filter_value_count > 0:
            noun = "filter value" if filter_value_count == 1 else "filter values"
            raise ConflictException(
                f'"{child.name}" has {filter_value_count} {noun} assigned to it. Remove or reassign '
                "those filter values before removing this child category."
            )
        await self.repository.soft_delete(child_id)
