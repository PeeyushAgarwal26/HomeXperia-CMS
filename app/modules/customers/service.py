import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.core.security import hash_password
from app.exceptions.http_exceptions import BadRequestException, ConflictException, NotFoundException
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import CustomerCreateRequest, CustomerUpdateRequest
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.suppliers.repository import SupplierRepository


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CustomerRepository(session)
        self.supplier_map_repository = CustomerSupplierRepository(session)
        self.supplier_repository = SupplierRepository(session)

    async def list_customers(
        self, pagination: PaginationParams, sort: SortParams, search: str | None, supplier_id: uuid.UUID | None
    ) -> tuple[list[Customer], int]:
        if supplier_id is not None:
            return await self._list_for_supplier(pagination, sort, search, supplier_id)
        return await self.repository.get_all(
            search=search,
            search_fields=["name", "customer_code", "phone_number", "email"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def _list_for_supplier(
        self, pagination: PaginationParams, sort: SortParams, search: str | None, supplier_id: uuid.UUID
    ) -> tuple[list[Customer], int]:
        customer_ids = await self.supplier_map_repository.get_customer_ids(supplier_id)
        if not customer_ids:
            return [], 0
        return await self.repository.get_all(
            filters={"id": customer_ids},
            search=search,
            search_fields=["name", "customer_code", "phone_number", "email"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def list_for_export(self, search: str | None, supplier_id: uuid.UUID | None) -> list[Customer]:
        if supplier_id is not None:
            customer_ids = await self.supplier_map_repository.get_customer_ids(supplier_id)
            if not customer_ids:
                return []
            return (
                await self.repository.get_all(
                    filters={"id": customer_ids},
                    search=search,
                    search_fields=["name", "customer_code", "phone_number", "email"],
                    limit=None,
                )
            )[0]
        return (
            await self.repository.get_all(
                search=search, search_fields=["name", "customer_code", "phone_number", "email"], limit=None
            )
        )[0]

    async def list_supplier_mappings_for_export(self) -> list[tuple[str, str, str]]:
        return await self.supplier_map_repository.get_all_mappings()

    async def get_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.repository.get_by_id(customer_id)
        if customer is None:
            raise NotFoundException("Customer")
        return customer

    async def get_supplier_names_map(self, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        return await self.supplier_map_repository.get_supplier_names_map(customer_ids)

    async def _check_uniqueness(
        self,
        customer_code: str,
        phone_number: str,
        email: str | None,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if await self.repository.customer_code_taken(customer_code, exclude_id):
            raise ConflictException("This customer code is already in use.")
        if await self.repository.phone_number_taken(phone_number, exclude_id):
            raise ConflictException("This phone number is already in use.")
        if email and await self.repository.email_taken(email, exclude_id):
            raise ConflictException("This email is already in use.")

    async def create(self, data: CustomerCreateRequest, created_by: uuid.UUID) -> Customer:
        await self._check_uniqueness(data.customer_code, data.phone_number, data.email)

        payload = data.model_dump(exclude={"password", "confirm_password"})
        payload["password_hash"] = hash_password(data.password)
        payload["created_by"] = created_by

        customer = await self.repository.create(payload)
        return await self.get_customer(customer.id)

    async def update(self, customer_id: uuid.UUID, data: CustomerUpdateRequest) -> Customer:
        await self.get_customer(customer_id)
        await self._check_uniqueness(data.customer_code, data.phone_number, data.email, exclude_id=customer_id)

        payload = data.model_dump(exclude={"password", "confirm_password"})
        if data.password:
            payload["password_hash"] = hash_password(data.password)

        await self.repository.update(customer_id, payload)
        return await self.get_customer(customer_id)

    async def delete(self, customer_id: uuid.UUID) -> None:
        await self.get_customer(customer_id)
        await self.repository.soft_delete(customer_id)

    async def set_status(self, customer_id: uuid.UUID, is_active: bool) -> Customer:
        await self.get_customer(customer_id)
        await self.repository.update(customer_id, {"is_active": is_active})
        return await self.get_customer(customer_id)

    async def get_supplier_ids(self, customer_id: uuid.UUID) -> list[uuid.UUID]:
        await self.get_customer(customer_id)
        return await self.supplier_map_repository.get_supplier_ids(customer_id)

    async def set_suppliers(
        self, customer_id: uuid.UUID, supplier_ids: list[uuid.UUID], mapped_by: uuid.UUID
    ) -> None:
        await self.get_customer(customer_id)

        unique_ids = list(dict.fromkeys(supplier_ids))
        existing_ids = await self.supplier_repository.get_existing_ids(unique_ids)
        unknown_ids = set(unique_ids) - existing_ids
        if unknown_ids:
            raise BadRequestException(f"Unknown supplier id(s): {', '.join(str(i) for i in unknown_ids)}")

        await self.supplier_map_repository.replace(customer_id, unique_ids, mapped_by=mapped_by)
