import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.module_catalog.models import Module
from app.modules.module_catalog.repository import ModuleRepository
from app.modules.module_catalog.schemas import ModuleTreeNode


class ModuleCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ModuleRepository(session)

    async def get_tree(self) -> list[ModuleTreeNode]:
        modules = await self.repository.list_active()
        return _build_tree(modules, parent_id=None)


def _build_tree(modules: list[Module], parent_id: uuid.UUID | None) -> list[ModuleTreeNode]:
    return [
        ModuleTreeNode(
            key=module.key,
            name=module.name,
            is_buildable=module.is_buildable,
            children=_build_tree(modules, parent_id=module.id),
        )
        for module in modules
        if module.parent_id == parent_id
    ]
