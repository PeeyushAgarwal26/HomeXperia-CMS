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


class GenerateHotspotMaskRequest(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class GenerateHotspotMaskResponse(BaseModel):
    mask_image_url: str


class HotspotDetail(BaseModel):
    id: uuid.UUID
    room_category_image_id: uuid.UUID
    label: str
    type: str
    sub_type: str | None
    options: str | None
    confidence: float | None
    description: str | None
    mask_image_url: str
    is_uploaded_to_cdn: bool
    x: float
    y: float
    order_no: int


class HotspotCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=250)
    type: str = Field(min_length=1, max_length=50)
    sub_type: str | None = None
    mask_image_url: str = Field(min_length=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    order_no: int = Field(default=0, ge=0)
    options: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    description: str | None = None


class HotspotUpdateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=250)
    type: str = Field(min_length=1, max_length=50)
    sub_type: str | None = None
    mask_image_url: str = Field(min_length=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    order_no: int = Field(default=0, ge=0)
    options: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    description: str | None = None


class GenerateCurtainRequest(BaseModel):
    curtain_style: str = Field(min_length=1, max_length=100)
    # Lets a second curtain on the same photo build on top of a first,
    # still-uncommitted preview instead of the original bare-window pixels.
    base_image_url: str | None = None


class PreviewedCurtainHotspot(BaseModel):
    """A curtain-panel hotspot detected by re-segmenting the freshly
    generated curtain image (see RoomCategoryImageService.preview_curtain) —
    a bare window is usually one opening but a rendered curtain is 1-3
    separate fabric panels, each of which needs its own product later, same
    as the real client-facing "Add Curtain" flow re-detects. NEVER becomes a
    real room_category_image_hotspots row — the shared room photo/hotspots
    are never written to from this flow. Its image_url/geometry are instead
    persisted directly onto the QR catalogue mapping that used it
    (QrCatalogueEntry.override_image_url / QrCatalogueEntryHotspot's
    inline_* columns), scoping the curtain to that one mapping only."""

    label: str
    type: str
    x: float
    y: float
    mask_image_url: str


class GenerateCurtainPreviewResponse(BaseModel):
    image_url: str
    hotspots: list[PreviewedCurtainHotspot]


class LegacyHotspotItem(BaseModel):
    """GET /room/image-hotspots' response shape — deliberately NOT
    HotspotDetail's field names. Traced directly from the real, unmodified
    homexperia-client-frontend (RoomConfigurator.jsx reads
    hs.image_hotspots_id, hs.mask_image, hs.type, hs.label, hs.x, hs.y,
    hs.sub_category_id) — matching this exactly is the only way that
    already-live code works against this backend without being changed."""

    image_hotspots_id: uuid.UUID
    label: str
    type: str
    mask_image: str
    x: float
    y: float
    sub_category_id: uuid.UUID | None = None
