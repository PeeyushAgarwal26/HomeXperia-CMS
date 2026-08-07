import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.customers.models import Customer
from app.modules.orders.models import Cart, CartItem, Order, OrderItem
from app.modules.products.models import Product


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_open_cart(self, customer_id: uuid.UUID) -> Cart | None:
        stmt = select(Cart).where(Cart.customer_id == customer_id, Cart.status == "open")
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_open_cart(self, customer_id: uuid.UUID) -> Cart:
        cart = Cart(customer_id=customer_id, status="open")
        self.session.add(cart)
        await self.session.flush()
        return cart

    async def get_items_with_products(self, cart_id: uuid.UUID) -> list[tuple[CartItem, Product]]:
        stmt = (
            select(CartItem, Product)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.cart_id == cart_id)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    async def get_item(self, cart_id: uuid.UUID, product_id: uuid.UUID) -> CartItem | None:
        stmt = select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_item(self, cart_id: uuid.UUID, product_id: uuid.UUID, quantity: int, uom: str) -> None:
        existing = await self.get_item(cart_id, product_id)
        if existing is not None:
            existing.quantity = quantity
            existing.uom = uom
        else:
            self.session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity, uom=uom))
        await self.session.flush()

    async def delete_item(self, cart_id: uuid.UUID, product_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
        )

    async def clear_items(self, cart_id: uuid.UUID) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Order, session)

    async def next_invoice_number(self) -> str:
        seq_value = await self.session.scalar(select(func.nextval("order_invoice_seq")))
        return f"INV-{datetime.now(timezone.utc):%Y%m}-{seq_value:05d}"

    async def create_items(self, items: list[dict]) -> None:
        self.session.add_all([OrderItem(**item) for item in items])
        await self.session.flush()

    async def get_items(self, order_id: uuid.UUID) -> list[OrderItem]:
        stmt = select(OrderItem).where(OrderItem.order_id == order_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_detail(self, order_id: uuid.UUID) -> tuple[Order, Customer] | None:
        stmt = select(Order, Customer).join(Customer, Customer.id == Order.customer_id).where(Order.id == order_id)
        row = (await self.session.execute(stmt)).first()
        return (row[0], row[1]) if row else None

    def _admin_query(
        self,
        search: str | None,
        from_date: date | None,
        to_date: date | None,
        customer_id: uuid.UUID | None,
    ):
        stmt = select(Order, Customer).join(Customer, Customer.id == Order.customer_id)
        if search:
            stmt = stmt.where(
                or_(
                    Order.client_name.ilike(f"%{search}%"),
                    Order.invoice_number.ilike(f"%{search}%"),
                    Customer.name.ilike(f"%{search}%"),
                    Customer.customer_code.ilike(f"%{search}%"),
                )
            )
        if customer_id:
            stmt = stmt.where(Order.customer_id == customer_id)
        if from_date:
            stmt = stmt.where(Order.created_at >= from_date)
        if to_date:
            stmt = stmt.where(Order.created_at < to_date + timedelta(days=1))
        return stmt

    async def list_admin(
        self,
        offset: int,
        limit: int | None,
        search: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[tuple[Order, Customer]], int]:
        stmt = self._admin_query(search, from_date, to_date, None)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = stmt.order_by(Order.created_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows], total

    async def list_for_export(self, search: str | None) -> list[tuple[Order, Customer]]:
        stmt = self._admin_query(search, None, None, None).order_by(Order.created_at.desc())
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def list_for_customer(
        self, customer_id: uuid.UUID, offset: int, limit: int | None
    ) -> tuple[list[tuple[Order, int]], int]:
        item_count = select(func.count(OrderItem.id)).where(OrderItem.order_id == Order.id).correlate(Order).scalar_subquery()
        stmt = select(Order, item_count).where(Order.customer_id == customer_id)
        total = await self.session.scalar(
            select(func.count()).select_from(select(Order.id).where(Order.customer_id == customer_id).subquery())
        ) or 0
        stmt = stmt.order_by(Order.created_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows], total
