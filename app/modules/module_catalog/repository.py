import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.module_catalog.models import Module


class ModuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> list[Module]:
        stmt = select(Module).where(Module.is_active.is_(True)).order_by(Module.sort_order)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_ids_for_keys(self, module_keys: list[str]) -> dict[str, uuid.UUID]:
        if not module_keys:
            return {}
        stmt = select(Module.key, Module.id).where(
            Module.key.in_(module_keys), Module.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return {key: module_id for key, module_id in result.all()}
