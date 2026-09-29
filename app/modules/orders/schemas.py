import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---- cart (customer-facing) ----


class CartItemCreateRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    uom: str = Field(min_length=1, max_length=50)


class CartCreateRequest(BaseModel):
    """One shot: creates a new named cart and its items together — matches
    the real client-frontend's "Lock Cart" step, which only ever has a
    client-side (sessionStorage) working cart to hand over at this point,
    never an existing server-side cart id.

    total_amount is accepted on the wire but never read — same as
    OrderCreateRequest, it's recomputed server-side from live product
    rates in get_cart_detail rather than ever being trusted from the
    client (Pydantic silently drops it since it isn't declared here).
    Each item on the wire also carries a full product snapshot
    (catalog_name, rate, brand_name, ...) that isn't declared on
    CartItemCreateRequest for the same reason — create_cart only ever
    reads product_id/quantity/uom off it and looks the rest up itself."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=250)
    whatsapp_no: str = Field(min_length=1, max_length=20)
    items: list[CartItemCreateRequest] = Field(min_length=1, alias="cart_items")


class CartItemUpsertRequest(BaseModel):
    cart_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    uom: str = Field(min_length=1, max_length=50)


class CartItemRemoveRequest(BaseModel):
    cart_id: uuid.UUID
    product_id: uuid.UUID


class CartItemDetail(BaseModel):
    product_id: uuid.UUID
    catalog_name: str | None
    design_no: str | None
    image_url: str | None
    uom: str
    rate: float
    quantity: int
    amount: float


class CartDetail(BaseModel):
    id: uuid.UUID
    name: str
    whatsapp_no: str
    items: list[CartItemDetail]
    total_amount: float


class CartSummary(BaseModel):
    """Lighter-weight than CartDetail (no per-item product lookups) — for
    the "Locked" tab's list of a customer's carts."""

    id: uuid.UUID
    name: str
    whatsapp_no: str
    item_count: int
    total_amount: float
    created_at: datetime


# ---- order placement (customer-facing) ----


class OrderItemCreateRequest(BaseModel):
    """rate/amount aren't declared here even though the real frontend still
    sends them per item — they're computed server-side from the live
    Product.rate instead of ever being trusted from the client, and Pydantic
    silently drops undeclared fields by default."""

    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    uom: str = Field(min_length=1, max_length=50)


class OrderCreateRequest(BaseModel):
    """Matches the real client-frontend's /order/save-order payload
    verbatim via aliases — customer_email/customer_whatsapp_no in the wire
    format are the showroom OWNER's contact, not the logged-in account (that
    comes from the JWT). total_amount is accepted on the wire but never
    read — it's recomputed server-side from live product rates."""

    model_config = ConfigDict(populate_by_name=True)

    client_name: str = Field(min_length=1, max_length=250)
    client_email: str = Field(min_length=1, max_length=255)
    client_whatsapp_no: str = Field(min_length=1, max_length=20)
    owner_email: str = Field(min_length=1, max_length=255, alias="customer_email")
    owner_whatsapp_no: str = Field(min_length=1, max_length=20, alias="customer_whatsapp_no")
    items: list[OrderItemCreateRequest] = Field(min_length=1, alias="itemsList")


class OrderCreateResponse(BaseModel):
    order_id: uuid.UUID
    invoice_number: str


class MyOrderListItem(BaseModel):
    id: uuid.UUID
    invoice_number: str
    total_amount: float
    item_count: int
    created_at: datetime


# ---- admin ----


class OrderItemDetail(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    catalog_name: str | None
    design_no: str | None
    image_url: str | None
    supplier_name: str | None
    category_name: str | None
    width: float | None
    uom: str
    rate: float
    quantity: int
    amount: float


class OrderListItem(BaseModel):
    id: uuid.UUID
    sno: int
    invoice_number: str
    client_name: str
    customer_name: str
    customer_code: str
    total_amount: float
    created_at: datetime


class OrderDetail(BaseModel):
    id: uuid.UUID
    invoice_number: str
    client_name: str
    client_email: str
    client_whatsapp_no: str
    owner_email: str
    owner_whatsapp_no: str
    customer_name: str
    customer_code: str
    total_amount: float
    notes: str | None
    created_at: datetime
    items: list[OrderItemDetail]
