from fastapi import APIRouter, Depends, UploadFile

from app.common.base_controller import BaseController
from app.common.deps import get_current_user
from app.common.response import APIResponse
from app.common.storage import StorageInterface, get_storage
from app.common.supplier_deps import get_current_supplier
from app.exceptions.http_exceptions import BadRequestException
from app.modules.admin_users.models import AdminUser
from app.modules.files.schemas import UploadResponse
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/files", tags=["Files"])
controller = BaseController()

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


async def _validated_bytes(file: UploadFile) -> None:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise BadRequestException("Only .jpg, .jpeg, .png, and .webp images are allowed.")

    contents = await file.read()
    if len(contents) > _MAX_FILE_SIZE_BYTES:
        raise BadRequestException("File too large — max 5 MB.")
    await file.seek(0)


@router.post("/upload", response_model=APIResponse[UploadResponse], status_code=201)
async def upload_file(
    file: UploadFile,
    _: AdminUser = Depends(get_current_user),
    storage: StorageInterface = Depends(get_storage),
) -> APIResponse:
    await _validated_bytes(file)
    url = await storage.save(file, subfolder="admin-users")
    return controller.success(data=UploadResponse(url=url), message="File uploaded.")


@router.post("/supplier-upload", response_model=APIResponse[UploadResponse], status_code=201)
async def supplier_upload_file(
    file: UploadFile,
    _: Supplier = Depends(get_current_supplier),
    storage: StorageInterface = Depends(get_storage),
) -> APIResponse:
    await _validated_bytes(file)
    url = await storage.save(file, subfolder="products")
    return controller.success(data=UploadResponse(url=url), message="File uploaded.")
