from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import State


class StateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[State]:
        stmt = select(State).order_by(State.sort_order)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def exists(self, code: str) -> bool:
        stmt = select(State.code).where(State.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
