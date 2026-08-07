import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


def resolve_uploaded_file_path(url: str) -> Path | None:
    """Maps a URL previously returned by LocalDiskStorage.save()/save_bytes()
    back to its actual location on disk. Root-relative URLs are resolved via
    settings.uploads_dir — deliberately NOT via `Path(url.lstrip("/"))`,
    which only happens to work when uploads_dir is the literal relative
    string "uploads" and the process cwd is the repo root. In production,
    uploads_dir is an absolute path outside the app directory (see
    app/core/config.py), decoupled from the URL's fixed "/uploads/..."
    prefix, so every caller that reads an already-uploaded file back off
    disk must go through this instead of re-deriving the path itself.
    Returns None for anything that isn't one of our own upload URLs
    (a different prefix, an absolute http(s) URL, etc).
    """
    prefix = f"/{settings.uploads_url_prefix}/"
    if not url.startswith(prefix):
        return None
    return Path(settings.uploads_dir) / url[len(prefix) :]


class StorageInterface(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subfolder: str) -> str:
        """Persist the file and return a URL/path clients can use to fetch it."""

    @abstractmethod
    async def save_bytes(self, filename: str, content: bytes, subfolder: str) -> str:
        """Same as save(), for content already read into memory (e.g. a zip entry)."""

    @abstractmethod
    async def delete(self, url: str) -> None:
        """Remove a previously saved file. No-op if it doesn't exist."""


class LocalDiskStorage(StorageInterface):
    async def save(self, file: UploadFile, subfolder: str) -> str:
        contents = await file.read()
        return await self.save_bytes(file.filename or "", contents, subfolder)

    async def save_bytes(self, filename: str, content: bytes, subfolder: str) -> str:
        extension = Path(filename).suffix
        target_dir = Path(settings.uploads_dir) / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        stored_name = f"{uuid.uuid4()}{extension}"
        target_path = target_dir / stored_name
        target_path.write_bytes(content)

        return f"/{settings.uploads_url_prefix}/{subfolder}/{stored_name}"

    async def delete(self, url: str) -> None:
        target_path = resolve_uploaded_file_path(url)
        if target_path is not None and target_path.exists():
            target_path.unlink()


def get_storage() -> StorageInterface:
    return LocalDiskStorage()
