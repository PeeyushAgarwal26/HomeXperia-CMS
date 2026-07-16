import uuid

from pydantic import BaseModel, Field


class FilterListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    is_active: bool


class FilterDetail(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool


class FilterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)


class FilterUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)


class FilterValueListItem(BaseModel):
    id: uuid.UUID
    sno: int
    value: str
    filter_id: uuid.UUID
    filter_name: str
    child_category_id: uuid.UUID
    child_category_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    is_active: bool


class FilterValueDetail(BaseModel):
    id: uuid.UUID
    value: str
    filter_id: uuid.UUID
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    is_active: bool


class FilterValueCreateRequest(BaseModel):
    filter_id: uuid.UUID
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    value: str = Field(min_length=1, max_length=250)


class FilterValueUpdateRequest(BaseModel):
    filter_id: uuid.UUID
    child_category_id: uuid.UUID
    supplier_id: uuid.UUID
    value: str = Field(min_length=1, max_length=250)


class StatusUpdateRequest(BaseModel):
    is_active: bool
