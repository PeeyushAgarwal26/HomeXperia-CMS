import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import PaginationParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.qr_generator.schemas import (
    CatalogueEntryCreateRequest,
    CatalogueEntryDetail,
    CatalogueEntryUpdateRequest,
    CataloguePreviewRequest,
    CataloguePreviewResponse,
    QrCodeGenerateRequest,
    RoomImagePickerItem,
    SavedQrCodeDetail,
)
from app.modules.qr_generator.service import QrGeneratorService

router = APIRouter(prefix="/qr-generator", tags=["QR Code Generator"])
controller = BaseController()

_require_qr_generator_access = require_module_permission("qr_generator")
_require_saved_qr_list_access = require_module_permission("qr_generator.saved_list")


@router.post("/generate")
async def generate_qr_code(
    body: QrCodeGenerateRequest,
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    png_bytes = await QrGeneratorService(session).generate(body)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="qr-{body.customer_code}.png"'},
    )


@router.post("/saved", response_model=APIResponse[SavedQrCodeDetail], status_code=201)
async def save_qr_code(
    body: QrCodeGenerateRequest,
    current_admin: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).save_qr_code(body, created_by=current_admin.id)
    return controller.success(data=data, message="QR code saved.")


@router.get("/saved", response_model=APIResponse[list[SavedQrCodeDetail]])
async def list_saved_qr_codes(
    pagination: Annotated[PaginationParams, Depends()],
    search: Annotated[str | None, Query()] = None,
    _: AdminUser = Depends(_require_saved_qr_list_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data, total = await QrGeneratorService(session).list_saved_qr_codes(pagination, search)
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/room-images", response_model=APIResponse[list[RoomImagePickerItem]])
async def list_room_images(
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).list_room_images()
    return controller.success(data=data)


@router.get("/filter-values", response_model=APIResponse[list[str]])
async def list_filter_values_for_customer(
    customer_id: Annotated[uuid.UUID, Query()],
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).list_filter_values_for_customer(customer_id)
    return controller.success(data=data)


@router.get("/catalogue-entries", response_model=APIResponse[list[CatalogueEntryDetail]])
async def list_catalogue_entries(
    customer_id: Annotated[uuid.UUID, Query()],
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).list_catalogue_entries(customer_id)
    return controller.success(data=data)


@router.post("/catalogue-entries", response_model=APIResponse[CatalogueEntryDetail], status_code=201)
async def create_catalogue_entry(
    body: CatalogueEntryCreateRequest,
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).create_catalogue_entry(body)
    return controller.success(data=data, message="Catalogue mapping saved.")


@router.put("/catalogue-entries/{entry_id}", response_model=APIResponse[CatalogueEntryDetail])
async def update_catalogue_entry(
    entry_id: uuid.UUID,
    body: CatalogueEntryUpdateRequest,
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).update_catalogue_entry(entry_id, body)
    return controller.success(data=data, message="Catalogue mapping updated.")


@router.delete("/catalogue-entries/{entry_id}", response_model=APIResponse[None])
async def delete_catalogue_entry(
    entry_id: uuid.UUID,
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await QrGeneratorService(session).delete_catalogue_entry(entry_id)
    return controller.success(message="Catalogue mapping deleted.")


@router.post("/preview", response_model=APIResponse[CataloguePreviewResponse])
async def preview_catalogue_composite(
    body: CataloguePreviewRequest,
    _: AdminUser = Depends(_require_qr_generator_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).preview_composite(body)
    return controller.success(data=data)
