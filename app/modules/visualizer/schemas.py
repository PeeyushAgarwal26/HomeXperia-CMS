from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# These mirror Flask's loosely-typed dict.get() request/response shapes as
# closely as Pydantic allows. Several fields stay Any/extra="allow" on
# purpose — the original has no schema either, and different `category`
# values legitimately carry different `settings` keys (curtain vs floor vs
# wall vs rug). Tightening this further is a real future improvement, not
# something to invent silently during a behavior-preserving port.


class HotspotSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    repeat: int | None = None
    shading: float | None = None
    rotation: float | None = None
    groutWidth: float | None = None
    groutColor: str | None = None
    curtainWidthCm: float | None = None


class HotspotProduct(BaseModel):
    model_config = ConfigDict(extra="allow")

    productImageUrl: str | None = None
    width: str | None = None
    productId: str | None = None


class HotspotLayer(BaseModel):
    model_config = ConfigDict(extra="allow")

    hotspotId: str | None = None
    category: str | None = None
    category_type: str | None = None
    coords: Any = None
    product: HotspotProduct | None = None
    settings: HotspotSettings | None = None
    mask_image: str | None = None


class ProcessRoomRequest(BaseModel):
    roomId: str
    baseImageUrl: str
    customer_code: str | None = None
    applyHotspot: list[HotspotLayer] | HotspotLayer | None = None
    product: HotspotProduct | None = None
    appliedHotspots: list[HotspotLayer] = Field(default_factory=list)
    remainingHotspots: list[Any] = Field(default_factory=list)


class ProcessRoomResponse(BaseModel):
    success: bool
    finalImageUrl: str | None = None
    appliedHotspots: list[HotspotLayer] = Field(default_factory=list)
    remainingHotspots: list[Any] = Field(default_factory=list)
    error: str | None = None


class CurtainGenerationRequest(BaseModel):
    image_url: str
    mask_urls: list[str] = Field(min_length=1)
    curtain_style: str = "pinch pleat"


class ResetRoomRequest(BaseModel):
    roomId: str


class ResetRoomResponse(BaseModel):
    success: bool


class MaskGenerationRequest(BaseModel):
    roomId: str
    baseImageUrl: str
    coords: Any


class MaskGenerationResponse(BaseModel):
    success: bool
    roomId: str
    maskImageUrl: str | None = None
    error: str | None = None


class RugVisualizerSceneRequest(BaseModel):
    room_url: str | None = None
    room_b64: str | None = None
    floor_mask_urls: list[str] = Field(default_factory=list)


class RugVisualizerSceneResponse(BaseModel):
    room_width: int
    room_height: int
    room_width_ft: float
    room_length_ft: float
    floor_top_norm: float
    floor_quad_norm: list[list[float]]
    floor_mask_b64: str
    shadow_map_b64: str


class WallArtVisualizerSceneRequest(BaseModel):
    room_url: str | None = None
    wall_mask_url: str | None = None
    product_url: str | None = None
    product_dimensions: dict[str, Any] | None = None


class WallArtVisualizerSceneResponse(BaseModel):
    """No real wall-art detection algorithm exists yet anywhere (not in the
    Flask backend this module ported from, not specified since) — the
    frontend's own code already treats this as a dev/dummy response. This is
    a structurally-valid placeholder, not a ported feature; replace once
    there's a real spec."""

    wall_quad_norm: list[list[float]]
    room_width: int
    room_height: int
    wall_mask_b64: str
    shadow_map_b64: str
    placement_quad_norm: list[list[float]]
    placement_center_norm: list[float]


class RoomListItem(BaseModel):
    roomId: str
    imageUrl: str


class RoomListResponse(BaseModel):
    rooms: list[RoomListItem]


class RoomDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    imageUrl: str


class CleanupResponse(BaseModel):
    success: bool
    folder: str
    deleted_files: int
    errors: list[str] | None = None


class CacheFileEntry(BaseModel):
    name: str
    size_mb: float


class CacheStatsResponse(BaseModel):
    cache_dir: str
    total_files: int
    total_size_mb: float
    total_size_gb: float
    files: list[CacheFileEntry]


class CacheClearResponse(BaseModel):
    success: bool
    message: str
