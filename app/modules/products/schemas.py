import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProductListItem(BaseModel):
    id: uuid.UUID
    sno: int
    order_no: int
    child_category_id: uuid.UUID
    child_category_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    catalog_name: str | None
    catalogue_name: str | None
    design_no: str | None
    bar_code: str
    image_url: str | None
    available_quantity: int | None
    rate: float | None
    length: float | None
    width: float | None
    is_active: bool


class ProductFilterValueDetail(BaseModel):
    filter_id: uuid.UUID
    filter_name: str
    value_id: uuid.UUID
    value: str


class ProductDetail(BaseModel):
    id: uuid.UUID
    order_no: int
    child_category_id: uuid.UUID
    child_category_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    catalog_name: str | None
    catalogue_name: str | None
    design_no: str | None
    bar_code: str
    image_url: str | None
    available_quantity: int | None
    rate: float | None
    length: float | None
    width: float | None
    is_active: bool
    filter_value_ids: list[uuid.UUID]
    filter_values: list[ProductFilterValueDetail]
    created_at: datetime
    updated_at: datetime


class ProductCreateRequest(BaseModel):
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    order_no: int = Field(ge=0)
    design_no: str | None = None
    bar_code: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    length: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, ge=0)
    filter_value_ids: list[uuid.UUID] = Field(default_factory=list)


class ProductUpdateRequest(BaseModel):
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    order_no: int = Field(ge=0)
    design_no: str | None = None
    bar_code: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    length: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, ge=0)
    filter_value_ids: list[uuid.UUID] = Field(default_factory=list)


# Same shape as ProductCreateRequest/UpdateRequest minus supplier_id — a
# supplier can only ever create/edit their own products, so supplier_id is
# derived from the authenticated supplier server-side, never accepted from
# the client. See products/supplier_controller.py.
class SupplierProductCreateRequest(BaseModel):
    child_category_id: uuid.UUID
    order_no: int = Field(ge=0)
    design_no: str | None = None
    bar_code: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    length: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, ge=0)
    filter_value_ids: list[uuid.UUID] = Field(default_factory=list)


class SupplierProductUpdateRequest(BaseModel):
    child_category_id: uuid.UUID
    order_no: int = Field(ge=0)
    design_no: str | None = None
    bar_code: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    length: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, ge=0)
    filter_value_ids: list[uuid.UUID] = Field(default_factory=list)


class StatusUpdateRequest(BaseModel):
    is_active: bool


class ProductFilterOption(BaseModel):
    id: uuid.UUID
    value: str


class ApplicableFilterGroup(BaseModel):
    filter_id: uuid.UUID
    filter_name: str
    options: list[ProductFilterOption]


class ProductCustomerItem(BaseModel):
    """Only fields that actually exist on Product — brand/size/weight/
    composition/end_use/wash_care/serial_no/shade_no/price_unit/uom aren't
    modeled anywhere in this backend yet (not on Product, not in the
    bulk-upload template) and are deliberately omitted rather than sent as
    fabricated nulls. product_name mirrors catalog_name under the
    alternate key name some UI components read."""

    product_id: uuid.UUID
    product_name: str | None
    catalog_name: str | None
    design_no: str | None
    product_image: str | None
    thumbnail: str | None
    rate: float | None
    width: float | None
    length: float | None
    child_category_id: uuid.UUID
