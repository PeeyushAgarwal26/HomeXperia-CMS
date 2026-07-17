import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.customers.models import Customer


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Customer, session)

    async def customer_code_taken(self, customer_code: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Customer.customer_code == customer_code)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def phone_number_taken(self, phone_number: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Customer.phone_number == phone_number)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def email_taken(self, email: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Customer.email == email)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None
