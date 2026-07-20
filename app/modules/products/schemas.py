import uuid

from pydantic import BaseModel, Field


class ProductListItem(BaseModel):
    id: uuid.UUID
    sno: int
    order_no: int
    child_category_id: uuid.UUID
    child_category_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    catalog_name: str
    design_no: str | None
    bar_code: str
    image_url: str | None
    available_quantity: int | None
    rate: float | None
    length: float
    width: float
    is_active: bool


class ProductDetail(BaseModel):
    id: uuid.UUID
    order_no: int
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    catalog_name: str
    design_no: str | None
    bar_code: str
    image_url: str | None
    available_quantity: int | None
    rate: float | None
    length: float
    width: float
    is_active: bool
    filter_value_ids: list[uuid.UUID]


class ProductCreateRequest(BaseModel):
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    order_no: int = Field(ge=0)
    catalog_name: str = Field(min_length=1, max_length=250)
    design_no: str | None = None
    bar_code: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    length: float
    width: float
    filter_value_ids: list[uuid.UUID] = Field(default_factory=list)


class ProductUpdateRequest(BaseModel):
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    order_no: int = Field(ge=0)
    catalog_name: str = Field(min_length=1, max_length=250)
    design_no: str | None = None
    bar_code: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    length: float
    width: float
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
