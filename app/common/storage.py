import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


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

        return f"/{settings.uploads_dir}/{subfolder}/{stored_name}"

    async def delete(self, url: str) -> None:
        relative_path = url.lstrip("/")
        target_path = Path(relative_path)
        if target_path.exists():
            target_path.unlink()


def get_storage() -> StorageInterface:
    return LocalDiskStorage()
