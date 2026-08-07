import asyncio
from collections import defaultdict

import numpy as np

# Ported from app.py's in-memory caches. Deliberately unbounded — cache-forever
# until explicitly cleared via /visualizer/admin/cache/clear, matching Flask
# exactly (no TTL exists in the source either). Per-process, not shared across
# workers, same as Flask's per-gunicorn-worker in-memory dicts.

_processed_base_cache: dict[str, tuple[str, np.ndarray]] = {}
_output_cache: dict[tuple[str, str, str], str] = {}

_room_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_output_locks: dict[tuple[str, str, str], asyncio.Lock] = defaultdict(asyncio.Lock)


def get_processed_base(room_id: str) -> tuple[str, np.ndarray] | None:
    return _processed_base_cache.get(room_id)


def set_processed_base(room_id: str, base_image_url: str, image: np.ndarray) -> None:
    _processed_base_cache[room_id] = (base_image_url, image)


def get_output(key: tuple[str, str, str]) -> str | None:
    return _output_cache.get(key)


def set_output(key: tuple[str, str, str], url: str) -> None:
    _output_cache[key] = url


def room_lock(room_id: str) -> asyncio.Lock:
    return _room_locks[room_id]


def output_lock(key: tuple[str, str, str]) -> asyncio.Lock:
    return _output_locks[key]


def clear_for_room(room_id: str) -> None:
    _processed_base_cache.pop(room_id, None)
    for key in [k for k in _output_cache if k[0] == room_id]:
        _output_cache.pop(key, None)


def clear_all() -> None:
    _processed_base_cache.clear()
    _output_cache.clear()
