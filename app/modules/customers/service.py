import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.core.security import generate_temp_password, hash_password
from app.exceptions.http_exceptions import BadRequestException, ConflictException, NotFoundException
from app.modules.customers.models import Customer, SupplierCustomerTheme
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import (
    CustomerCreateRequest,
    CustomerUpdateRequest,
    LinkedAccountCreatedResponse,
)
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.customers.theme_repository import SupplierCustomerThemeRepository
from app.modules.suppliers.repository import SupplierRepository
from app.services.email import send_email

logger = logging.getLogger(__name__)


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CustomerRepository(session)
        self.supplier_map_repository = CustomerSupplierRepository(session)
        self.supplier_repository = SupplierRepository(session)
        self.theme_repository = SupplierCustomerThemeRepository(session)

    async def list_customers(
        self, pagination: PaginationParams, sort: SortParams, search: str | None, supplier_id: uuid.UUID | None
    ) -> tuple[list[Customer], int]:
        if supplier_id is not None:
            return await self._list_for_supplier(pagination, sort, search, supplier_id)
        return await self.repository.get_all(
            search=search,
            search_fields=["name", "email", "city", "phone_number"],
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
            search_fields=["name", "email", "city", "phone_number"],
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
                    search_fields=["name", "email", "city", "phone_number"],
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

    async def create(
        self, data: CustomerCreateRequest, created_by: uuid.UUID
    ) -> tuple[Customer, str, LinkedAccountCreatedResponse | None]:
        await self._check_uniqueness(data.customer_code, data.phone_number, data.email)
        if data.also_create_supplier and await self.supplier_repository.username_taken(data.supplier_username):
            raise ConflictException("This username is already in use.")

        temp_password = generate_temp_password()
        payload = data.model_dump(exclude={"also_create_supplier", "supplier_username"})
        payload["password_hash"] = hash_password(temp_password)
        payload["created_by"] = created_by

        customer = await self.repository.create(payload)

        if customer.email:
            try:
                await send_email(
                    to=customer.email,
                    subject="Your HomeXperia Client Portal account",
                    body_html=(
                        f"<p>A Client Portal account has been created for you.</p>"
                        f"<p>Customer Code: <strong>{customer.customer_code}</strong><br>"
                        f"Temporary Password: <strong>{temp_password}</strong></p>"
                        f"<p>Please log in and change your password.</p>"
                    ),
                )
            except Exception:
                logger.exception("customer_credentials_email_failed", extra={"customer_id": str(customer.id)})

        linked_supplier = (
            await self.promote_to_supplier(
                customer.id, data.supplier_username, state_code=None, city=None, created_by=created_by
            )
            if data.also_create_supplier
            else None
        )
        return await self.get_customer(customer.id), temp_password, linked_supplier

    async def promote_to_supplier(
        self,
        customer_id: uuid.UUID,
        username: str,
        state_code: str | None,
        city: str | None,
        created_by: uuid.UUID,
    ) -> LinkedAccountCreatedResponse:
        """Auto-provisions this customer's own Supplier identity — a fully
        independent account (own username, own random temp password)
        carrying over the customer's shared fields. state_code/city are only
        taken from the arguments when the customer record doesn't already
        have them set — Supplier requires both, Customer allows either to be
        null."""
        customer = await self.get_customer(customer_id)
        if customer.linked_supplier_id is not None:
            raise ConflictException("This customer already has a linked supplier account.")
        if await self.supplier_repository.username_taken(username):
            raise BadRequestException("This username is already in use.")

        resolved_state_code = customer.state_code or state_code
        resolved_city = customer.city or city
        if not resolved_state_code or not resolved_city:
            raise BadRequestException("State and city are required to create a supplier account.")

        temp_password = generate_temp_password()
        supplier = await self.supplier_repository.create(
            {
                "name": customer.name,
                "email": customer.email,
                "phone_number": customer.phone_number,
                "gst_number": customer.gst_number,
                "address": customer.address,
                "pin_code": customer.pin_code,
                "state_code": resolved_state_code,
                "city": resolved_city,
                "username": username,
                "password_hash": hash_password(temp_password),
                "created_by": created_by,
                "linked_customer_id": customer.id,
            }
        )
        await self.repository.update(customer_id, {"linked_supplier_id": supplier.id})
        existing_supplier_ids = await self.supplier_map_repository.get_supplier_ids(customer_id)
        await self.supplier_map_repository.replace(
            customer_id,
            list(dict.fromkeys([*existing_supplier_ids, supplier.id])),
            mapped_by=created_by,
        )

        if customer.email:
            try:
                await send_email(
                    to=customer.email,
                    subject="Your HomeXperia Supplier Portal account",
                    body_html=(
                        f"<p>A Supplier Portal account has been created for you.</p>"
                        f"<p>Username: <strong>{username}</strong><br>"
                        f"Temporary Password: <strong>{temp_password}</strong></p>"
                        f"<p>Please log in and change your password.</p>"
                    ),
                )
            except Exception:
                logger.exception("linked_supplier_credentials_email_failed", extra={"customer_id": str(customer_id)})

        return LinkedAccountCreatedResponse(
            linked_id=supplier.id,
            login_identifier=username,
            email_sent_to=customer.email,
            temporary_password=temp_password,
        )

    async def update(self, customer_id: uuid.UUID, data: CustomerUpdateRequest) -> Customer:
        await self.get_customer(customer_id)
        await self._check_uniqueness(data.customer_code, data.phone_number, data.email, exclude_id=customer_id)

        payload = data.model_dump(exclude={"password", "confirm_password"})
        if data.password:
            payload["password_hash"] = hash_password(data.password)

        await self.repository.update(customer_id, payload)
        return await self.get_customer(customer_id)

    async def delete(self, customer_id: uuid.UUID) -> None:
        customer = await self.get_customer(customer_id)
        if customer.linked_supplier_id is not None:
            await self.supplier_repository.soft_delete(customer.linked_supplier_id)
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

    async def _ensure_own_customer(self, supplier_id: uuid.UUID, customer_id: uuid.UUID) -> None:
        """Same 404 either way (missing vs. not mapped to this supplier) — mirrors
        get_own_product/get_own_value; see products/service.py."""
        if not await self.supplier_map_repository.is_mapped(supplier_id, customer_id):
            raise NotFoundException("Customer")

    async def get_own_customer_theme(
        self, supplier_id: uuid.UUID, customer_id: uuid.UUID
    ) -> SupplierCustomerTheme | None:
        await self._ensure_own_customer(supplier_id, customer_id)
        return await self.theme_repository.get(supplier_id, customer_id)

    async def update_own_customer_theme(
        self,
        supplier_id: uuid.UUID,
        customer_id: uuid.UUID,
        primary_color: str | None,
        secondary_color: str | None,
    ) -> SupplierCustomerTheme:
        await self._ensure_own_customer(supplier_id, customer_id)
        return await self.theme_repository.upsert(supplier_id, customer_id, primary_color, secondary_color)

    async def list_customer_supplier_themes(
        self, customer_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str, str | None, str | None]]:
        """Admin-facing view — every supplier this customer is mapped to, with
        whichever theme that supplier has configured for them (None if not set yet)."""
        await self.get_customer(customer_id)
        supplier_ids = await self.supplier_map_repository.get_supplier_ids(customer_id)
        if not supplier_ids:
            return []
        suppliers, _ = await self.supplier_repository.get_all(
            filters={"id": supplier_ids}, limit=len(supplier_ids)
        )
        theme_by_supplier = {
            t.supplier_id: t for t in await self.theme_repository.list_for_customer(customer_id)
        }
        return [
            (
                s.id,
                s.name,
                theme_by_supplier[s.id].primary_color if s.id in theme_by_supplier else None,
                theme_by_supplier[s.id].secondary_color if s.id in theme_by_supplier else None,
            )
            for s in suppliers
        ]

    async def set_customer_supplier_theme(
        self,
        customer_id: uuid.UUID,
        supplier_id: uuid.UUID,
        primary_color: str | None,
        secondary_color: str | None,
    ) -> str:
        """Admin override — unlike the supplier's own self-service endpoint, this
        skips the ownership check (admin can act on behalf of any supplier) but
        still confirms the two are actually mapped, since a theme for an unrelated
        supplier makes no sense. Returns the supplier's name for the response."""
        await self.get_customer(customer_id)
        if not await self.supplier_map_repository.is_mapped(supplier_id, customer_id):
            raise BadRequestException("This supplier is not mapped to this customer.")
        supplier = await self.supplier_repository.get_by_id(supplier_id)
        if supplier is None:
            raise NotFoundException("Supplier")
        await self.theme_repository.upsert(supplier_id, customer_id, primary_color, secondary_color)
        return supplier.name

    async def get_customer_direct_theme(self, customer_id: uuid.UUID) -> Customer:
        """This customer's OWN theme — plain columns on Customer, no supplier
        involved. Distinct from the per-(supplier, customer) rows above."""
        return await self.get_customer(customer_id)

    async def set_customer_direct_theme(
        self, customer_id: uuid.UUID, primary_color: str | None, secondary_color: str | None
    ) -> Customer:
        await self.get_customer(customer_id)
        await self.repository.update(
            customer_id, {"primary_color": primary_color, "secondary_color": secondary_color}
        )
        return await self.get_customer(customer_id)
