import uuid
from datetime import date

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.customers.models import Customer
from app.modules.orders.models import Order
from app.modules.orders.pdf import generate_invoice_pdf
from app.modules.orders.repository import CartRepository, OrderRepository
from app.modules.orders.schemas import (
    CartDetail,
    CartItemDeleteRequest,
    CartItemDetail,
    CartItemUpsertRequest,
    MyOrderListItem,
    OrderCreateRequest,
    OrderCreateResponse,
    OrderDetail,
    OrderItemDetail,
    OrderListItem,
)
from app.modules.products.repository import ProductRepository


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cart_repo = CartRepository(session)
        self.order_repo = OrderRepository(session)
        self.product_repo = ProductRepository(session)

    # ---- cart ----

    async def get_or_create_cart(self, customer_id: uuid.UUID):
        cart = await self.cart_repo.get_open_cart(customer_id)
        if cart is None:
            cart = await self.cart_repo.create_open_cart(customer_id)
        return cart

    async def get_cart_detail(self, customer_id: uuid.UUID) -> CartDetail:
        cart = await self.get_or_create_cart(customer_id)
        rows = await self.cart_repo.get_items_with_products(cart.id)
        items: list[CartItemDetail] = []
        total = 0.0
        for cart_item, product in rows:
            rate = float(product.rate or 0)
            amount = rate * cart_item.quantity
            total += amount
            items.append(
                CartItemDetail(
                    product_id=product.id,
                    catalog_name=product.catalog_name,
                    design_no=product.design_no,
                    image_url=product.image_url,
                    uom=cart_item.uom,
                    rate=rate,
                    quantity=cart_item.quantity,
                    amount=amount,
                )
            )
        return CartDetail(id=cart.id, status=cart.status, items=items, total_amount=total)

    async def upsert_cart_item(self, customer_id: uuid.UUID, data: CartItemUpsertRequest) -> CartDetail:
        product = await self.product_repo.get_by_id(data.product_id)
        if product is None or not product.is_active:
            raise BadRequestException("Product not found or unavailable.")
        cart = await self.get_or_create_cart(customer_id)
        await self.cart_repo.upsert_item(cart.id, data.product_id, data.quantity, data.uom.upper())
        return await self.get_cart_detail(customer_id)

    async def delete_cart_item(self, customer_id: uuid.UUID, data: CartItemDeleteRequest) -> CartDetail:
        cart = await self.get_or_create_cart(customer_id)
        if data.product_id is not None:
            await self.cart_repo.delete_item(cart.id, data.product_id)
        else:
            await self.cart_repo.clear_items(cart.id)
        return await self.get_cart_detail(customer_id)

    # ---- order placement ----

    async def save_order(self, customer_id: uuid.UUID, data: OrderCreateRequest) -> OrderCreateResponse:
        item_rows = []
        total = 0.0
        for line in data.items:
            product = await self.product_repo.get_by_id(line.product_id)
            if product is None or not product.is_active:
                raise BadRequestException(f"Product {line.product_id} not found or unavailable.")
            rate = float(product.rate or 0)
            amount = rate * line.quantity
            total += amount
            item_rows.append(
                {
                    "product_id": product.id,
                    "catalog_name": product.catalog_name,
                    "design_no": product.design_no,
                    "image_url": product.image_url,
                    "supplier_name": product.supplier.name,
                    "category_name": product.child_category.name,
                    "width": float(product.width) if product.width is not None else None,
                    "uom": line.uom.upper(),
                    "rate": rate,
                    "quantity": line.quantity,
                    "amount": amount,
                }
            )

        invoice_number = await self.order_repo.next_invoice_number()
        order = await self.order_repo.create(
            {
                "customer_id": customer_id,
                "invoice_number": invoice_number,
                "client_name": data.client_name,
                "client_email": data.client_email,
                "client_whatsapp_no": data.client_whatsapp_no,
                "owner_email": data.owner_email,
                "owner_whatsapp_no": data.owner_whatsapp_no,
                "total_amount": total,
            }
        )
        for row in item_rows:
            row["order_id"] = order.id
        await self.order_repo.create_items(item_rows)
        return OrderCreateResponse(order_id=order.id, invoice_number=invoice_number)

    async def list_my_orders(
        self, customer_id: uuid.UUID, offset: int, limit: int | None
    ) -> tuple[list[MyOrderListItem], int]:
        rows, total = await self.order_repo.list_for_customer(customer_id, offset, limit)
        items = [
            MyOrderListItem(
                id=order.id,
                invoice_number=order.invoice_number,
                total_amount=float(order.total_amount),
                item_count=item_count,
                created_at=order.created_at,
            )
            for order, item_count in rows
        ]
        return items, total

    # ---- invoice ----

    async def generate_invoice(self, order_id: uuid.UUID, *, customer_id: uuid.UUID | None = None) -> bytes:
        detail = await self.order_repo.get_detail(order_id)
        if detail is None or (customer_id is not None and detail[0].customer_id != customer_id):
            raise NotFoundException("Order")
        order, customer = detail
        items = await self.order_repo.get_items(order_id)
        return await to_thread.run_sync(generate_invoice_pdf, order, customer, items)

    # ---- admin ----

    async def list_orders(
        self,
        offset: int,
        limit: int | None,
        search: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[OrderListItem], int]:
        rows, total = await self.order_repo.list_admin(offset, limit, search, from_date, to_date)
        start = offset + 1
        items = [
            OrderListItem(
                id=order.id,
                sno=start + i,
                invoice_number=order.invoice_number,
                client_name=order.client_name,
                customer_name=customer.name,
                customer_code=customer.customer_code,
                total_amount=float(order.total_amount),
                created_at=order.created_at,
            )
            for i, (order, customer) in enumerate(rows)
        ]
        return items, total

    async def get_order_detail(self, order_id: uuid.UUID) -> OrderDetail:
        detail = await self.order_repo.get_detail(order_id)
        if detail is None:
            raise NotFoundException("Order")
        order, customer = detail
        items = await self.order_repo.get_items(order_id)
        return OrderDetail(
            id=order.id,
            invoice_number=order.invoice_number,
            client_name=order.client_name,
            client_email=order.client_email,
            client_whatsapp_no=order.client_whatsapp_no,
            owner_email=order.owner_email,
            owner_whatsapp_no=order.owner_whatsapp_no,
            customer_name=customer.name,
            customer_code=customer.customer_code,
            total_amount=float(order.total_amount),
            notes=order.notes,
            created_at=order.created_at,
            items=[
                OrderItemDetail(
                    id=item.id,
                    product_id=item.product_id,
                    catalog_name=item.catalog_name,
                    design_no=item.design_no,
                    image_url=item.image_url,
                    supplier_name=item.supplier_name,
                    category_name=item.category_name,
                    width=float(item.width) if item.width is not None else None,
                    uom=item.uom,
                    rate=float(item.rate),
                    quantity=item.quantity,
                    amount=float(item.amount),
                )
                for item in items
            ],
        )

    async def list_for_export(self, search: str | None) -> list[tuple[Order, Customer]]:
        return await self.order_repo.list_for_export(search)
