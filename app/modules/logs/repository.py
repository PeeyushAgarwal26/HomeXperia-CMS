import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import Row, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin_users.models import AdminUser
from app.modules.customers.models import Customer, CustomerSupplier
from app.modules.logs.models import AdminUserLoginEvent, CustomerLoginEvent, SupplierLoginEvent
from app.modules.suppliers.models import Supplier


class CustomerLoginEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_query(
        self,
        *,
        search: str | None,
        supplier_id: uuid.UUID | None,
        from_date: date | None,
        to_date: date | None,
    ) -> Any:
        login_day = func.date(CustomerLoginEvent.logged_in_at)
        stmt = (
            select(
                Customer.id.label("customer_id"),
                Customer.name,
                Customer.customer_code,
                Customer.device_limit,
                func.count(CustomerLoginEvent.id).label("login_count"),
                func.max(CustomerLoginEvent.logged_in_at).label("login_date"),
            )
            .join(Customer, Customer.id == CustomerLoginEvent.customer_id)
            .where(Customer.deleted_at.is_(None))
            .group_by(Customer.id, Customer.name, Customer.customer_code, Customer.device_limit, login_day)
        )
        if supplier_id is not None:
            stmt = stmt.where(
                Customer.id.in_(
                    select(CustomerSupplier.customer_id).where(CustomerSupplier.supplier_id == supplier_id)
                )
            )
        if search:
            stmt = stmt.where(
                or_(Customer.name.ilike(f"%{search}%"), Customer.customer_code.ilike(f"%{search}%"))
            )
        if from_date:
            stmt = stmt.where(CustomerLoginEvent.logged_in_at >= from_date)
        if to_date:
            stmt = stmt.where(CustomerLoginEvent.logged_in_at < to_date + timedelta(days=1))
        return stmt

    async def get_day_wise(
        self,
        *,
        search: str | None,
        supplier_id: uuid.UUID | None,
        from_date: date | None,
        to_date: date | None,
        offset: int,
        limit: int | None,
    ) -> tuple[Sequence[Row], int]:
        stmt = self._base_query(search=search, supplier_id=supplier_id, from_date=from_date, to_date=to_date)

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        stmt = stmt.order_by(func.max(CustomerLoginEvent.logged_in_at).desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.all(), total

    async def get_events_for_day(
        self, customer_id: uuid.UUID, day: date
    ) -> Sequence[CustomerLoginEvent]:
        """The raw events one day-wise Customer Login History row summarizes —
        powers the row's drill-down, not shown in the day-wise list itself."""
        stmt = (
            select(CustomerLoginEvent)
            .where(
                CustomerLoginEvent.customer_id == customer_id,
                CustomerLoginEvent.logged_in_at >= day,
                CustomerLoginEvent.logged_in_at < day + timedelta(days=1),
            )
            .order_by(CustomerLoginEvent.logged_in_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


    async def create(self, customer_id: uuid.UUID, ip_address: str | None) -> None:
        self.session.add(CustomerLoginEvent(customer_id=customer_id, ip_address=ip_address))
        await self.session.flush()


class AdminUserLoginEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, admin_user_id: uuid.UUID, ip_address: str | None, user_agent: str | None
    ) -> None:
        self.session.add(
            AdminUserLoginEvent(admin_user_id=admin_user_id, ip_address=ip_address, user_agent=user_agent)
        )
        await self.session.flush()


class SupplierLoginEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, supplier_id: uuid.UUID, ip_address: str | None, user_agent: str | None
    ) -> None:
        self.session.add(
            SupplierLoginEvent(supplier_id=supplier_id, ip_address=ip_address, user_agent=user_agent)
        )
        await self.session.flush()


class LoginHistoryRepository:
    """Unified read side for Sub Admin + Supplier login events — a single UNION ALL
    query with a "role" discriminator column, not two separate queries merged in
    Python, so pagination/sorting/filtering stay correct across both sources.
    Customer Login History is deliberately NOT part of this union — it's a
    day-wise aggregation with customer-specific columns (device limit, login
    count), a genuinely different report, and stays on its own page."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_query(
        self,
        *,
        search: str | None,
        role: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> Any:
        admin_stmt = (
            select(
                AdminUserLoginEvent.id.label("id"),
                AdminUser.id.label("account_id"),
                AdminUser.name.label("name"),
                AdminUser.username.label("username"),
                literal("sub_admin").label("role"),
                AdminUserLoginEvent.logged_in_at.label("logged_in_at"),
                AdminUserLoginEvent.ip_address.label("ip_address"),
            )
            .join(AdminUser, AdminUser.id == AdminUserLoginEvent.admin_user_id)
            .where(AdminUser.is_super_admin.is_(False))
        )
        supplier_stmt = select(
            SupplierLoginEvent.id.label("id"),
            Supplier.id.label("account_id"),
            Supplier.name.label("name"),
            Supplier.username.label("username"),
            literal("supplier").label("role"),
            SupplierLoginEvent.logged_in_at.label("logged_in_at"),
            SupplierLoginEvent.ip_address.label("ip_address"),
        ).join(Supplier, Supplier.id == SupplierLoginEvent.supplier_id)

        combined = union_all(admin_stmt, supplier_stmt).subquery()
        stmt = select(combined)

        if role:
            stmt = stmt.where(combined.c.role == role)
        if search:
            stmt = stmt.where(
                or_(combined.c.name.ilike(f"%{search}%"), combined.c.username.ilike(f"%{search}%"))
            )
        if from_date:
            stmt = stmt.where(combined.c.logged_in_at >= from_date)
        if to_date:
            stmt = stmt.where(
                combined.c.logged_in_at < datetime.combine(to_date, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
                + timedelta(days=1)
            )
        return stmt, combined

    async def list_login_history(
        self,
        *,
        search: str | None,
        role: str | None,
        from_date: date | None,
        to_date: date | None,
        offset: int,
        limit: int | None,
    ) -> tuple[Sequence[Row], int]:
        stmt, combined = self._base_query(search=search, role=role, from_date=from_date, to_date=to_date)

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        stmt = stmt.order_by(combined.c.logged_in_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.all(), total
