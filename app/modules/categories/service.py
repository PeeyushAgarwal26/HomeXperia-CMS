from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import ChildCategoryItem, ParentCategoryNode


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
