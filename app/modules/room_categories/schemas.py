import uuid

from pydantic import BaseModel, Field


class RoomCategoryListItem(BaseModel):
    id: uuid.UUID
    sno: int
    order_no: int
    name: str
    icon_url: str | None
    is_active: bool


class RoomCategoryDetail(BaseModel):
    id: uuid.UUID
    name: str
    order_no: int
    icon_url: str | None
    is_active: bool


class RoomCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    order_no: int = Field(ge=0)
    icon_url: str | None = None


class RoomCategoryUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    order_no: int = Field(ge=0)
    icon_url: str | None = None


class StatusUpdateRequest(BaseModel):
    is_active: bool
