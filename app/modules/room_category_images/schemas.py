import uuid

from pydantic import BaseModel, Field


class RoomCategoryImageListItem(BaseModel):
    id: uuid.UUID
    sno: int
    order_no: int
    image_url: str
    is_uploaded_to_cdn: bool
    suppliers: list[str]


class RoomCategoryImageDetail(BaseModel):
    id: uuid.UUID
    room_category_id: uuid.UUID
    order_no: int
    image_url: str
    is_uploaded_to_cdn: bool


class RoomCategoryImageCreateRequest(BaseModel):
    order_no: int = Field(ge=0)
    image_url: str = Field(min_length=1)


class RoomCategoryImageUpdateRequest(BaseModel):
    order_no: int = Field(ge=0)
    image_url: str = Field(min_length=1)


class MapSuppliersRequest(BaseModel):
    supplier_ids: list[uuid.UUID]


class MapSuppliersResponse(BaseModel):
    supplier_ids: list[uuid.UUID]
