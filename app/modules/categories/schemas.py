import uuid

from pydantic import BaseModel, Field


class ChildCategoryItem(BaseModel):
    id: uuid.UUID
    name: str


class ParentCategoryNode(BaseModel):
    id: uuid.UUID
    name: str
    children: list[ChildCategoryItem]


class ParentCategoryListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    icon_url: str | None
    is_active: bool


class ParentCategoryDetail(BaseModel):
    id: uuid.UUID
    name: str
    icon_url: str | None
    is_active: bool


class ParentCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    icon_url: str | None = None


class ParentCategoryUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    icon_url: str | None = None


class ChildCategoryListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    icon_url: str | None
    parent_category_id: uuid.UUID
    parent_category_name: str
    is_active: bool


class ChildCategoryDetail(BaseModel):
    id: uuid.UUID
    name: str
    icon_url: str | None
    parent_category_id: uuid.UUID
    is_active: bool


class ChildCategoryCreateRequest(BaseModel):
    parent_category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=250)
    icon_url: str | None = None


class ChildCategoryUpdateRequest(BaseModel):
    parent_category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=250)
    icon_url: str | None = None


class StatusUpdateRequest(BaseModel):
    is_active: bool


class ParentCategoryCustomerItem(BaseModel):
    """category_code is derived (upper-cased name), not a stored column —
    the client app's AR hotspot types (wall/floor/window/...) are matched
    against it case-insensitively. See CategoryRepository.get_parent_by_name."""

    id: uuid.UUID
    name: str
    category_code: str
    icon_url: str | None


class ChildCategoryCustomerItem(BaseModel):
    """unique_code is derived (lower-cased, underscored name), not a stored
    column — the client app switches compositing behavior (e.g. repeat
    count) on specific slugs like "wallpaper"/"wall_art". Only matches for
    child categories whose name happens to equal one of those slugs; no
    such mapping is stored or guaranteed today."""

    id: uuid.UUID
    name: str
    unique_code: str
    icon_url: str | None
    parent_category_id: uuid.UUID
