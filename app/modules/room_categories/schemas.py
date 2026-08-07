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


class RoomCategoryCustomerImage(BaseModel):
    room_category_image_id: uuid.UUID
    image_url: str


class RoomCategoryCustomerItem(BaseModel):
    """Field names (room_category_id/icon/room_category_images/...) match
    what the client app's RoomUpload/VirtualRoom pages already consume,
    not this module's own admin-facing naming (id/icon_url) — this is a
    separate customer-facing shape, not a re-export of RoomCategoryDetail.

    Note: room_category_images here carries only {id, image_url} — the
    per-image shoppable-hotspot metadata (bounding boxes, masks) the demo
    room flow ultimately needs isn't modeled anywhere yet (see
    room_category_images/models.py's own docstring); clicking into one of
    these demo images today will show no interactive hotspots until that
    content-modeling gap is addressed separately."""

    room_category_id: uuid.UUID
    name: str
    icon: str | None
    room_category_images: list[RoomCategoryCustomerImage]
