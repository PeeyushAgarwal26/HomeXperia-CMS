import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class QrCodeGenerateRequest(BaseModel):
    customer_code: str = Field(min_length=1, max_length=100)
    # One or more catalogue/pattern names, all encoded into the SAME QR (see
    # service.py's _build_verify_url for the current joining/limitation caveat).
    filter_values: list[str] = Field(default_factory=list)
    # A URL already uploaded via the existing files/upload endpoint (root-relative
    # or absolute) — composited into the center of the QR as a branding logo.
    # Purely cosmetic: confirmed (via a live audit of the real customer-facing
    # frontend's scan-handling code) that brand_logo plays no part in what a scan
    # actually does — only customer_code and filter_value are read off the URL.
    brand_logo_url: str | None = None


# ---- saved QR codes (admin explicitly keeps one after generating it) ----


class SavedQrCodeDetail(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_code: str
    filter_values: list[str]
    brand_logo_url: str | None
    image_url: str
    created_at: datetime


# ---- catalogue mapping (replaces the old customerCatalog.js static file) ----


class RoomImagePickerItem(BaseModel):
    id: uuid.UUID
    image_url: str
    room_category_id: uuid.UUID
    room_category_name: str


class HotspotPickerItem(BaseModel):
    id: uuid.UUID
    label: str
    type: str
    sub_type: str | None
    x: float
    y: float
    mask_image_url: str


class HotspotProductAssignment(BaseModel):
    """One hotspot + the ONE product that applies to it — a room image's
    floor/wall/curtain/curtain hotspots each need their own product, so a
    catalogue entry carries a list of these rather than a single shared
    product_id.

    hotspot_id targets a REAL, shared room hotspot (floor, wall — never
    needs a curtain). A curtain-panel hotspot generated for THIS mapping is
    never written into the shared room_category_image_hotspots table (see
    QrCatalogueEntryHotspot's docstring — curtains belong to the mapping,
    not the room's master photo) — its geometry travels inline instead via
    label/type/x/y/mask_image_url. Exactly one of hotspot_id or the inline
    fields must be set."""

    hotspot_id: uuid.UUID | None = None
    product_id: uuid.UUID
    label: str | None = None
    type: str | None = None
    x: float | None = None
    y: float | None = None
    mask_image_url: str | None = None

    @model_validator(mode="after")
    def _check_target(self) -> "HotspotProductAssignment":
        has_inline = None not in (self.label, self.type, self.x, self.y, self.mask_image_url)
        if self.hotspot_id is None and not has_inline:
            raise ValueError("Either hotspot_id or (label, type, x, y, mask_image_url) must be provided.")
        return self


class CatalogueEntryCreateRequest(BaseModel):
    customer_id: uuid.UUID
    filter_value: str = Field(min_length=1, max_length=250)
    catalog_name: str = Field(min_length=1, max_length=250)
    room_category_image_id: uuid.UUID
    hotspot_products: list[HotspotProductAssignment] = Field(min_length=1)
    # A curtain generated while building this mapping — persisted here,
    # NEVER onto the shared room_category_image row (see
    # QrCatalogueEntry.override_image_url's docstring). None means this
    # mapping's hotspots needed no curtain; the room's own photo is used.
    override_image_url: str | None = None


class CatalogueEntryUpdateRequest(BaseModel):
    catalog_name: str = Field(min_length=1, max_length=250)
    room_category_image_id: uuid.UUID
    hotspot_products: list[HotspotProductAssignment] = Field(min_length=1)
    override_image_url: str | None = None


class HotspotProductDetail(BaseModel):
    # Stable key for this row: the real room hotspot's id when hotspot_id is
    # set, otherwise this junction row's own id (an inline curtain panel has
    # no real shared hotspot to key off).
    id: uuid.UUID
    hotspot_id: uuid.UUID | None
    product_id: uuid.UUID
    product_name: str
    product_image_url: str | None
    product_width: float | None
    label: str
    type: str
    x: float
    y: float
    mask_image_url: str


class CatalogueEntryDetail(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_code: str
    filter_value: str
    catalog_name: str
    room_category_image_id: uuid.UUID
    room_image_url: str
    hotspot_products: list[HotspotProductDetail]


class PreviewHotspotAssignment(BaseModel):
    """Same as HotspotProductAssignment, but a preview can also target a
    curtain-panel hotspot that preview_curtain just detected and hasn't
    been committed to the DB yet (see RoomCategoryImageService.
    preview_curtain/commit_curtain) — no hotspot_id exists for that yet, so
    its geometry travels inline instead. Exactly one of hotspot_id or
    (x, y, type) must be set."""

    hotspot_id: uuid.UUID | None = None
    product_id: uuid.UUID
    x: float | None = None
    y: float | None = None
    type: str | None = None

    @model_validator(mode="after")
    def _check_target(self) -> "PreviewHotspotAssignment":
        has_inline = self.x is not None and self.y is not None and self.type is not None
        if self.hotspot_id is None and not has_inline:
            raise ValueError("Either hotspot_id or (x, y, type) must be provided.")
        return self


class CataloguePreviewRequest(BaseModel):
    room_category_image_id: uuid.UUID
    hotspot_products: list[PreviewHotspotAssignment] = Field(min_length=1)
    # Lets a Preview composite against a curtain generated moments ago but
    # not yet committed to the room image (see RoomCategoryImageService.
    # preview_curtain/commit_curtain) — falls back to the persisted
    # room_category_image's own image_url when omitted.
    base_image_url: str | None = None


class CataloguePreviewResponse(BaseModel):
    final_image_url: str


# ---- customer-facing lookup (what the client frontend calls instead of
# importing customerCatalog.js) ----


class CatalogueLookupResponse(BaseModel):
    catalog_name: str
    room_category_image_id: uuid.UUID
    room_image_url: str
    hotspot_products: list[HotspotProductDetail]
    # The real Filters system's "Catalogue Name" Filter.id (see
    # QrGeneratorService._ensure_filter_value_linked) — the client applies
    # this filter_value as a real, pre-checked Filters-panel selection, which
    # requires a real filter_id, not a fabricated one.
    catalogue_filter_id: uuid.UUID | None
