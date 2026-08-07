import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.core.security import generate_temp_password, hash_password
from app.exceptions.http_exceptions import BadRequestException, ConflictException, NotFoundException
from app.modules.categories.repository import CategoryRepository
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.filters.repository import FilterValueRepository
from app.modules.module_catalog.repository import ModuleRepository
from app.modules.products.repository import ProductRepository
from app.modules.suppliers.categories_repository import SupplierCategoryRepository
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.permissions_repository import SupplierPermissionRepository
from app.modules.suppliers.repository import SupplierRepository
from app.modules.suppliers.schemas import (
    LinkedAccountCreatedResponse,
    SupplierCreateRequest,
    SupplierUpdateRequest,
)
from app.services.email import send_email

logger = logging.getLogger(__name__)


class SupplierService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SupplierRepository(session)
        self.category_map_repository = SupplierCategoryRepository(session)
        self.category_repository = CategoryRepository(session)
        self.permission_repository = SupplierPermissionRepository(session)
        self.module_repository = ModuleRepository(session)
        self.product_repository = ProductRepository(session)
        self.filter_value_repository = FilterValueRepository(session)
        self.customer_supplier_repository = CustomerSupplierRepository(session)
        self.customer_repository = CustomerRepository(session)

    async def list_suppliers(
        self, pagination: PaginationParams, sort: SortParams, search: str | None
    ) -> tuple[list[Supplier], int]:
        return await self.repository.get_all(
            search=search,
            search_fields=["name", "email", "city", "phone_number"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def list_for_export(self, search: str | None) -> list[Supplier]:
        return (
            await self.repository.get_all(
                search=search, search_fields=["name", "email", "gst_number", "phone_number"], limit=None
            )
        )[0]

    async def get_supplier(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.repository.get_by_id(supplier_id)
        if supplier is None:
            raise NotFoundException("Supplier")
        return supplier

    async def get_category_names_map(self, supplier_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        return await self.category_map_repository.get_category_names_map(supplier_ids)

    async def _check_uniqueness(
        self, username: str, phone_number: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        if await self.repository.username_taken(username, exclude_id):
            raise ConflictException("This username is already in use.")
        if await self.repository.phone_number_taken(phone_number, exclude_id):
            raise ConflictException("This phone number is already in use.")

    async def create(
        self, data: SupplierCreateRequest, created_by: uuid.UUID
    ) -> tuple[Supplier, str, LinkedAccountCreatedResponse | None]:
        await self._check_uniqueness(data.username, data.phone_number)

        temp_password = generate_temp_password()
        payload = data.model_dump(exclude={"also_create_customer"})
        payload["password_hash"] = hash_password(temp_password)
        payload["created_by"] = created_by

        supplier = await self.repository.create(payload)

        if supplier.email:
            try:
                await send_email(
                    to=supplier.email,
                    subject="Your HomeXperia Supplier Portal account",
                    body_html=(
                        f"<p>A Supplier Portal account has been created for you.</p>"
                        f"<p>Username: <strong>{supplier.username}</strong><br>"
                        f"Temporary Password: <strong>{temp_password}</strong></p>"
                        f"<p>Please log in and change your password.</p>"
                    ),
                )
            except Exception:
                logger.exception("supplier_credentials_email_failed", extra={"supplier_id": str(supplier.id)})

        linked_customer = (
            await self.create_linked_customer(supplier.id, created_by) if data.also_create_customer else None
        )
        return await self.get_supplier(supplier.id), temp_password, linked_customer

    async def _generate_unique_customer_code(self, seed: str) -> str:
        base = "".join(ch for ch in seed.lower() if ch.isalnum()) or "customer"
        candidate = base
        suffix = 0
        while await self.customer_repository.customer_code_taken(candidate):
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    async def create_linked_customer(
        self, supplier_id: uuid.UUID, created_by: uuid.UUID
    ) -> LinkedAccountCreatedResponse:
        """Auto-provisions this supplier's own Customer identity — a fully
        independent account (own customer_code, own random temp password)
        carrying over the supplier's shared fields. Linked only by FK; never
        shares a password with the Supplier row it came from."""
        supplier = await self.get_supplier(supplier_id)
        if supplier.linked_customer_id is not None:
            raise ConflictException("This supplier already has a linked customer account.")

        customer_code = await self._generate_unique_customer_code(supplier.username)
        temp_password = generate_temp_password()
        customer = await self.customer_repository.create(
            {
                "name": supplier.name,
                "email": supplier.email,
                "phone_number": supplier.phone_number,
                "gst_number": supplier.gst_number,
                "address": supplier.address,
                "pin_code": supplier.pin_code,
                "state_code": supplier.state_code,
                "city": supplier.city,
                "customer_code": customer_code,
                "password_hash": hash_password(temp_password),
                "created_by": created_by,
                "linked_supplier_id": supplier.id,
            }
        )
        await self.repository.update(supplier_id, {"linked_customer_id": customer.id})

        if supplier.email:
            try:
                await send_email(
                    to=supplier.email,
                    subject="Your HomeXperia Client Portal account",
                    body_html=(
                        f"<p>A Client Portal account has been created for you.</p>"
                        f"<p>Customer Code: <strong>{customer_code}</strong><br>"
                        f"Temporary Password: <strong>{temp_password}</strong></p>"
                        f"<p>Please log in and change your password.</p>"
                    ),
                )
            except Exception:
                logger.exception("linked_customer_credentials_email_failed", extra={"supplier_id": str(supplier_id)})

        return LinkedAccountCreatedResponse(
            linked_id=customer.id,
            login_identifier=customer_code,
            email_sent_to=supplier.email,
            temporary_password=temp_password,
        )

    async def update(self, supplier_id: uuid.UUID, data: SupplierUpdateRequest) -> Supplier:
        await self.get_supplier(supplier_id)
        await self._check_uniqueness(data.username, data.phone_number, exclude_id=supplier_id)

        payload = data.model_dump(exclude={"password", "confirm_password"})
        if data.password:
            payload["password_hash"] = hash_password(data.password)

        await self.repository.update(supplier_id, payload)
        return await self.get_supplier(supplier_id)

    async def delete(self, supplier_id: uuid.UUID) -> None:
        supplier = await self.get_supplier(supplier_id)
        _, product_count = await self.product_repository.get_all(
            filters={"supplier_id": supplier_id}, limit=1
        )
        if product_count > 0:
            noun = "product" if product_count == 1 else "products"
            raise ConflictException(
                f'"{supplier.name}" has {product_count} {noun} in its catalog. Move or delete those '
                "products before removing this supplier."
            )
        _, filter_value_count = await self.filter_value_repository.get_all(
            filters={"supplier_id": supplier_id}, limit=1
        )
        if filter_value_count > 0:
            noun = "filter value" if filter_value_count == 1 else "filter values"
            raise ConflictException(
                f'"{supplier.name}" has {filter_value_count} {noun} assigned to it. Remove or reassign '
                "those filter values before removing this supplier."
            )
        customer_count = len(await self.customer_supplier_repository.get_customer_ids(supplier_id))
        if customer_count > 0:
            noun = "customer" if customer_count == 1 else "customers"
            raise ConflictException(
                f'"{supplier.name}" is mapped to {customer_count} {noun}. Unmap it from those customers '
                "before removing this supplier."
            )
        if supplier.linked_customer_id is not None:
            await self.customer_repository.soft_delete(supplier.linked_customer_id)
        await self.repository.soft_delete(supplier_id)

    async def set_status(self, supplier_id: uuid.UUID, is_active: bool) -> Supplier:
        await self.get_supplier(supplier_id)
        await self.repository.update(supplier_id, {"is_active": is_active})
        return await self.get_supplier(supplier_id)

    async def get_child_category_ids(self, supplier_id: uuid.UUID) -> list[uuid.UUID]:
        await self.get_supplier(supplier_id)
        return await self.category_map_repository.get_child_category_ids(supplier_id)

    async def set_categories(
        self, supplier_id: uuid.UUID, child_category_ids: list[uuid.UUID], granted_by: uuid.UUID
    ) -> None:
        await self.get_supplier(supplier_id)

        unique_ids = list(dict.fromkeys(child_category_ids))
        existing_ids = await self.category_repository.get_ids_for_ids(unique_ids)
        unknown_ids = set(unique_ids) - existing_ids
        if unknown_ids:
            raise BadRequestException(f"Unknown category id(s): {', '.join(str(i) for i in unknown_ids)}")

        await self.category_map_repository.replace(supplier_id, unique_ids, granted_by=granted_by)

    async def get_permission_keys(self, supplier_id: uuid.UUID) -> list[str]:
        await self.get_supplier(supplier_id)
        return await self.permission_repository.get_module_keys(supplier_id)

    async def set_permissions(
        self, supplier_id: uuid.UUID, module_keys: list[str], granted_by: uuid.UUID
    ) -> None:
        await self.get_supplier(supplier_id)

        unique_keys = list(dict.fromkeys(module_keys))
        key_to_id = await self.module_repository.get_ids_for_keys(unique_keys)
        unknown_keys = set(unique_keys) - set(key_to_id.keys())
        if unknown_keys:
            raise BadRequestException(f"Unknown module key(s): {', '.join(sorted(unknown_keys))}")

        await self.permission_repository.replace(
            supplier_id, list(key_to_id.values()), granted_by=granted_by
        )
