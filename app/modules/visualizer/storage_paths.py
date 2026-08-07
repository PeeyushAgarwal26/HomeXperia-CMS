from pathlib import Path

from app.core.config import settings

# All visualizer files live under the existing public uploads mount
# (app.main mounts /{settings.uploads_url_prefix} via StaticFiles, backed by
# the settings.uploads_dir directory on disk) so they stay fetchable with no
# new mount, matching Flask's intentionally-unauthenticated
# uploads/generated/masks serving.
VISUALIZER_ROOT = Path(settings.uploads_dir) / "visualizer"
UPLOADS_DIR = VISUALIZER_ROOT / "uploads"
GENERATED_DIR = VISUALIZER_ROOT / "generated"
MASKS_DIR = VISUALIZER_ROOT / "masks"
CACHE_DIR = VISUALIZER_ROOT / "cache"
DEBUG_DIR = (VISUALIZER_ROOT / "debugs") if settings.visualizer_debug_images else None

GENERATED_SUBFOLDER = "visualizer/generated"  # get_storage().save_bytes(..., subfolder=...)


def ensure_dirs() -> None:
    for directory in (UPLOADS_DIR, GENERATED_DIR, MASKS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if DEBUG_DIR is not None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def mask_path(room_id: str, hotspot_id: str) -> Path:
    return MASKS_DIR / f"mask_{room_id}_{hotspot_id}.png"


def mask_url(room_id: str, hotspot_id: str) -> str:
    return f"/{settings.uploads_url_prefix}/visualizer/masks/mask_{room_id}_{hotspot_id}.png"
