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
    # Real product width comes in both shapes depending on how the supplier
    # entered it: a plain number (e.g. 10.0) or a compound descriptive
    # string (e.g. "5 X 7 FT") that curtain.parse_width_to_cm regex-parses
    # the first number out of. That function already coerces its input via
    # str(width_str) before matching, so accepting either shape here is
    # safe — this was previously str-only, which 422'd on a plain numeric
    # width even though nothing downstream actually required a string.
    width: str | float | int | None = None
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
    # True when a real metric depth map (imaging/depth.py) was fit to the
    # floor plane and (when a reference object was found) calibrated against
    # it, grounding room_width_ft/room_length_ft and floor_quad_norm's own
    # span in actual 3D geometry rather than a vision-LLM guess. False when
    # that failed for any reason and the classical 2D quad + GPT-vision size
    # estimate ran instead — the response is still complete either way.
    used_depth: bool = False


class WallArtVisualizerSceneRequest(BaseModel):
    room_url: str | None = None
    room_b64: str | None = None
    wall_mask_url: str | None = None
    product_url: str | None = None
    # {"width": <number>, "height": <number>}, unit ambiguous on the wire —
    # see _art_dimensions_ft in service.py for how this gets resolved.
    product_dimensions: dict[str, Any] | None = None


class WallArtVisualizerSceneResponse(BaseModel):
    """Real detection, mirroring rug_visualizer_scene's structure: wall.py's
    existing detect_wall_quad (already used by the wallpaper/paint apply
    path) for wall_quad_norm, wall_scene.estimate_wall_clear_region (new,
    same color-region-growing technique rug's estimate_floor_masks already
    uses) for clear_region_quad_norm, and the same OpenAI vision-estimate
    pattern rug uses for room ft-size, re-prompted for the wall specifically,
    for wall_width_ft/wall_height_ft."""

    wall_quad_norm: list[list[float]]
    # Obstacle-free sub-region within wall_quad_norm (avoids light switches,
    # outlets, mirrors, existing art) — distinct from the full detected wall.
    clear_region_quad_norm: list[list[float]]
    room_width: int
    room_height: int
    wall_width_ft: float
    wall_height_ft: float
    # None when the caller never sent product_dimensions — never fabricated.
    art_width_ft: float | None
    art_height_ft: float | None
    # True if the art's real-world size fit inside clear_region_quad_norm
    # without needing to be scaled down.
    fitted: bool
    # True when a real metric depth map (imaging/depth.py) was successfully
    # fit to the wall plane for this request, grounding wall_width_ft/
    # wall_height_ft and obstacle detection in actual 3D geometry rather than
    # a vision-LLM guess / LAB-color-uniformity heuristic. False when that
    # failed for any reason (no wall mask supplied, insufficient depth
    # signal, degenerate plane fit) and the classical fallback path ran
    # instead — the response is still complete and usable either way, this
    # just reflects which method produced it.
    used_depth: bool
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
