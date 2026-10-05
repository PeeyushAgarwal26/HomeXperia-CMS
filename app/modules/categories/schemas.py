import uuid
from typing import Literal

from pydantic import BaseModel, Field

# Closed, admin-set vocabulary for ChildCategory.visualizer_type — replaces
# deriving visualizer behavior from the category's display name (see
# ChildCategoryCustomerItem below for why). A fixed set on purpose: the
# whole point is that nothing here can be mistyped, so adding a new value
# is a deliberate code change, not something an admin can accidentally
# produce by renaming a category.
VisualizerType = Literal["rug", "wall_art", "wallpaper", "wall_paint"]


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
    visualizer_type: VisualizerType | None


class ChildCategoryDetail(BaseModel):
    id: uuid.UUID
    name: str
    icon_url: str | None
    parent_category_id: uuid.UUID
    is_active: bool
    visualizer_type: VisualizerType | None


class ChildCategoryCreateRequest(BaseModel):
    parent_category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=250)
    icon_url: str | None = None
    visualizer_type: VisualizerType | None = None


class ChildCategoryUpdateRequest(BaseModel):
    parent_category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=250)
    icon_url: str | None = None
    visualizer_type: VisualizerType | None = None


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
    """unique_code is derived (lower-cased, underscored name) and kept
    exactly as-is for backward compatibility — unchanged by the
    visualizer_type addition below, so nothing currently reading it
    (including whatever a caller does with the category_type value built
    from it) regresses.

    visualizer_type is the real, admin-set, closed-vocabulary replacement:
    a stored column (see ChildCategory.visualizer_type), not derived from
    `name` at all. The client should switch to reading this field instead
    of deriving/matching against `name`/`unique_code` for deciding which
    visualizer flow a category triggers — it can't be broken by a display-
    text rename or typo the way unique_code always could."""

    id: uuid.UUID
    name: str
    unique_code: str
    visualizer_type: VisualizerType | None
    icon_url: str | None
    parent_category_id: uuid.UUID
