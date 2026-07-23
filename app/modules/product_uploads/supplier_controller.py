import uuid
from datetime import date, datetime
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.common.base_controller import BaseController
from app.common.pagination import FilterParams, PaginationParams
from app.common.response import APIResponse
from app.common.storage import StorageInterface, get_storage
from app.common.supplier_deps import get_current_supplier
from app.db.session import get_db_session
from app.exceptions.http_exceptions import BadRequestException
from app.modules.product_uploads.schemas import (
    UploadLogDetail,
    UploadLogListItem,
    UploadLogRow,
    UploadPreviewResult,
)
from app.modules.product_uploads.service import ProductUploadService
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/supplier/product-uploads", tags=["Supplier Product Uploads"])
controller = BaseController()


def _to_list_item(log, sno: int) -> UploadLogListItem:
    return UploadLogListItem(
        id=log.id,
        sno=sno,
        file_name=log.file_name,
        supplier_id=log.supplier_id,
        supplier_name=log.supplier.name,
        uploaded_at=log.created_at,
        total_rows=log.total_rows,
        success_count=log.success_count,
        error_count=log.error_count,
        status=log.status,
    )


def _to_detail(log, rows) -> UploadLogDetail:
    return UploadLogDetail(
        id=log.id,
        file_name=log.file_name,
        supplier_id=log.supplier_id,
        supplier_name=log.supplier.name,
        uploaded_at=log.created_at,
        total_rows=log.total_rows,
        success_count=log.success_count,
        error_count=log.error_count,
        status=log.status,
        error_message=log.error_message,
        rows=[
            UploadLogRow(
                row_no=r.row_no,
                catalog_name=r.catalog_name,
                is_success=r.is_success,
                action=r.action,
                message=r.message,
            )
            for r in rows
        ],
    )


def _row_dicts_to_rows(row_results: list[dict]) -> list[UploadLogRow]:
    return [UploadLogRow(**row) for row in row_results]


async def _read_upload_files(excel_file: UploadFile, images_zip: UploadFile | None) -> tuple[bytes, bytes | None]:
    if not (excel_file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise BadRequestException("Only .xlsx or .xls files are accepted for the product sheet.")
    if images_zip is not None and not (images_zip.filename or "").lower().endswith(".zip"):
        raise BadRequestException("Images must be uploaded as a single .zip file.")

    excel_bytes = await excel_file.read()
    images_bytes = await images_zip.read() if images_zip is not None else None
    return excel_bytes, images_bytes


@router.get("/template")
async def download_my_template(
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
    storage: StorageInterface = Depends(get_storage),
):
    content = await ProductUploadService(session, storage).build_template(supplier.id)
    filename = f"ProductUploadFormat_{datetime.now().strftime('%d-%b-%Y_%H.%M')}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/preview", response_model=APIResponse[UploadPreviewResult])
async def preview_my_upload(
    excel_file: UploadFile,
    images_zip: UploadFile | None = None,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
    storage: StorageInterface = Depends(get_storage),
) -> APIResponse:
    """Dry run — validates every row and reports what would happen, but writes nothing.
    The supplier decides whether to commit by calling POST /supplier/product-uploads
    with the same files."""
    excel_bytes, images_bytes = await _read_upload_files(excel_file, images_zip)

    row_results, total, created_count, updated_count, error_count = await ProductUploadService(
        session, storage
    ).preview_upload(supplier.id, excel_bytes, images_bytes)

    return controller.success(
        data=UploadPreviewResult(
            total_rows=total,
            created_count=created_count,
            updated_count=updated_count,
            error_count=error_count,
            rows=_row_dicts_to_rows(row_results),
        )
    )


@router.post("", response_model=APIResponse[UploadLogDetail], status_code=201)
async def upload_my_products(
    excel_file: UploadFile,
    images_zip: UploadFile | None = None,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
    storage: StorageInterface = Depends(get_storage),
) -> APIResponse:
    excel_bytes, images_bytes = await _read_upload_files(excel_file, images_zip)

    service = ProductUploadService(session, storage)
    log = await service.process_upload(
        supplier.id,
        excel_bytes,
        excel_file.filename or "upload.xlsx",
        images_bytes,
        None,  # no admin in the loop — this supplier uploaded it themselves
    )
    _, rows = await service.get_log_detail(log.id)
    if log.status == "success":
        message = "All rows imported successfully."
    elif log.status == "partial":
        message = f"{log.success_count} of {log.total_rows} rows imported — {log.error_count} failed."
    else:
        message = log.error_message or "Import failed."
    return controller.success(data=_to_detail(log, rows), message=message)


@router.get("/logs", response_model=APIResponse[list[UploadLogListItem]])
async def list_my_logs(
    pagination: Annotated[PaginationParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
    storage: StorageInterface = Depends(get_storage),
) -> APIResponse:
    service = ProductUploadService(session, storage)
    items, total = await service.list_logs(pagination, filters.search, supplier.id, from_date, to_date)
    start = pagination.offset + 1
    data = [_to_list_item(item, start + i) for i, item in enumerate(items)]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/logs/{log_id}", response_model=APIResponse[UploadLogDetail])
async def get_my_log(
    log_id: uuid.UUID,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
    storage: StorageInterface = Depends(get_storage),
) -> APIResponse:
    log, rows = await ProductUploadService(session, storage).get_own_log_detail(log_id, supplier.id)
    return controller.success(data=_to_detail(log, rows))
