import uuid
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import PRODUCT_UPLOAD_FIXED_COLUMNS as FIXED_COLUMNS
from app.common.logging import get_logger
from app.common.pagination import PaginationParams
from app.common.storage import StorageInterface
from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.categories.repository import ChildCategoryRepository
from app.modules.filters.repository import FilterValueRepository
from app.modules.product_uploads.models import ProductUploadLog, ProductUploadLogItem
from app.modules.product_uploads.repository import ProductUploadLogItemRepository, ProductUploadLogRepository
from app.modules.products.repository import ProductFilterValueRepository, ProductRepository
from app.modules.suppliers.categories_repository import SupplierCategoryRepository
from app.modules.suppliers.repository import SupplierRepository

_FIXED_COLUMN_KEYS = {c.lower() for c in FIXED_COLUMNS}
logger = get_logger(__name__)


class ProductUploadService:
    def __init__(self, session: AsyncSession, storage: StorageInterface) -> None:
        self.session = session
        self.storage = storage
        self.log_repository = ProductUploadLogRepository(session)
        self.log_item_repository = ProductUploadLogItemRepository(session)
        self.supplier_repository = SupplierRepository(session)
        self.supplier_category_repository = SupplierCategoryRepository(session)
        self.child_category_repository = ChildCategoryRepository(session)
        self.filter_value_repository = FilterValueRepository(session)
        self.product_repository = ProductRepository(session)
        self.product_filter_value_repository = ProductFilterValueRepository(session)

    async def _get_supplier_or_404(self, supplier_id: uuid.UUID):
        supplier = await self.supplier_repository.get_by_id(supplier_id)
        if supplier is None:
            raise NotFoundException("Supplier")
        return supplier

    async def _get_suppliers_categories(self, supplier_id: uuid.UUID) -> list:
        category_ids = await self.supplier_category_repository.get_child_category_ids(supplier_id)
        if not category_ids:
            return []
        categories, _ = await self.child_category_repository.get_all(
            filters={"id": category_ids}, limit=len(category_ids)
        )
        return categories

    # ---------------------------------------------------------------- template

    async def build_template(self, supplier_id: uuid.UUID) -> bytes:
        """Generated fresh from the current Filter/FilterValue set every time — a Filter
        added via the Filter module's own Add form shows up as a new column on the very
        next download, with no template file to maintain and no code change needed."""
        await self._get_supplier_or_404(supplier_id)

        categories = await self._get_suppliers_categories(supplier_id)
        category_names = [c.name for c in categories]

        filters = await self.filter_value_repository.list_distinct_filters_for_supplier(supplier_id)
        headers = [*FIXED_COLUMNS, *(f.name for f in filters)]

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Products"
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column_cells in sheet.columns:
            sheet.column_dimensions[column_cells[0].column_letter].width = 22

        if category_names:
            # Excel's inline list validation is capped at 255 chars combined — fine for a
            # supplier's realistic category count; a very large one would need a named-range
            # validation instead.
            validation = DataValidation(type="list", formula1='"{}"'.format(",".join(category_names)))
            sheet.add_data_validation(validation)
            validation.add("A2:A1000")

        ref_sheet = workbook.create_sheet("Reference - Valid Filter Values")
        ref_sheet.append(["Child Category", "Filter", "Valid Values"])
        for cell in ref_sheet[1]:
            cell.font = Font(bold=True)
        for category in categories:
            values = await self.filter_value_repository.list_applicable(category.id, supplier_id)
            grouped: dict[str, list[str]] = {}
            for value in values:
                grouped.setdefault(value.filter.name, []).append(value.value)
            for filter_name, options in sorted(grouped.items()):
                ref_sheet.append([category.name, filter_name, ", ".join(options)])
        for column_cells in ref_sheet.columns:
            max_length = max(len(str(c.value)) if c.value is not None else 0 for c in column_cells)
            ref_sheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 60)

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    # ---------------------------------------------------------------- upload

    async def _run_rows(
        self,
        supplier_id: uuid.UUID,
        excel_bytes: bytes,
        images_zip_bytes: bytes | None,
        *,
        commit: bool,
    ) -> tuple[list[dict], int, int, int, int]:
        """Validates every row and, only when commit=True, writes the resulting Products.
        A row whose (supplier, Bar Code) already matches an existing product updates it in
        place instead of creating a duplicate — this is what makes re-submitting the same
        sheet (e.g. after fixing 2 failed rows) safe to do without duplicating the rest.

        Returns (row_results, total, created_count, updated_count, error_count).
        """
        await self._get_supplier_or_404(supplier_id)

        categories = await self._get_suppliers_categories(supplier_id)
        category_by_name = {c.name.strip().lower(): c for c in categories}

        active_filters = await self.filter_value_repository.list_distinct_filters_for_supplier(supplier_id)
        filter_by_name = {f.name.strip().lower(): f for f in active_filters}
        filter_name_by_id = {f.id: f.name for f in active_filters}

        images: dict[str, bytes] = {}
        if images_zip_bytes:
            with zipfile.ZipFile(BytesIO(images_zip_bytes)) as zip_file:
                for info in zip_file.infolist():
                    if info.is_dir():
                        continue
                    images[Path(info.filename).name] = zip_file.read(info.filename)

        try:
            workbook = load_workbook(BytesIO(excel_bytes), data_only=True)
        except Exception as exc:
            raise BadRequestException("Could not read the uploaded file — is it a valid .xlsx?") from exc

        sheet = workbook["Products"] if "Products" in workbook.sheetnames else workbook.worksheets[0]
        header_row = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
        if not any(header_row):
            raise BadRequestException("Uploaded file has no header row.")

        column_kind: list[tuple[str, object]] = []
        for header in header_row:
            key = header.lower()
            if key in _FIXED_COLUMN_KEYS:
                column_kind.append(("fixed", header))
            elif key in filter_by_name:
                column_kind.append(("filter", filter_by_name[key].id))
            else:
                # Unrecognized column — e.g. a Filter that's since been deactivated/renamed
                # since this copy of the template was downloaded. Ignored, not an error.
                column_kind.append(("unknown", header))

        applicable_cache: dict[uuid.UUID, dict[tuple[uuid.UUID, str], uuid.UUID]] = {}

        async def lookup_for_category(child_category_id: uuid.UUID) -> dict[tuple[uuid.UUID, str], uuid.UUID]:
            if child_category_id not in applicable_cache:
                values = await self.filter_value_repository.list_applicable(child_category_id, supplier_id)
                applicable_cache[child_category_id] = {
                    (value.filter_id, value.value.strip().lower()): value.id for value in values
                }
            return applicable_cache[child_category_id]

        total = created_count = updated_count = error_count = 0
        row_results: list[dict] = []

        for row_cells in sheet.iter_rows(min_row=2):
            raw_values = [cell.value for cell in row_cells]
            if all(v is None or str(v).strip() == "" for v in raw_values):
                continue
            total += 1
            row_no = row_cells[0].row

            record: dict[str, str] = {}
            filter_cells: dict[uuid.UUID, str] = {}
            for (kind, ref), value in zip(column_kind, raw_values):
                text = str(value).strip() if value is not None else ""
                if kind == "fixed":
                    record[ref] = text
                elif kind == "filter" and text:
                    filter_cells[ref] = text

            catalog_name = record.get("Catalog Name") or None
            error_message: str | None = None

            category = category_by_name.get((record.get("Category") or "").strip().lower())
            if category is None:
                error_message = f'"{record.get("Category") or ""}" is not a category this supplier sells in.'
            elif not record.get("Catalog Name"):
                error_message = "Catalog Name is required."
            elif not record.get("Bar Code"):
                error_message = "Bar Code is required."
            elif not record.get("Length"):
                error_message = "Length is required."
            elif not record.get("Width"):
                error_message = "Width is required."

            filter_value_ids: list[uuid.UUID] = []
            if error_message is None and filter_cells:
                lookup = await lookup_for_category(category.id)
                for filter_id, text in filter_cells.items():
                    matched_id = lookup.get((filter_id, text.strip().lower()))
                    if matched_id is None:
                        filter_name = filter_name_by_id.get(filter_id, "Filter")
                        error_message = (
                            f'"{text}" is not a valid {filter_name} value for '
                            f"{category.name} / this supplier."
                        )
                        break
                    filter_value_ids.append(matched_id)

            image_ref = (record.get("Image") or "").strip()
            image_content: bytes | None = None
            if error_message is None and image_ref:
                image_content = images.get(image_ref)
                if image_content is None:
                    error_message = f'Image "{image_ref}" was not found in the uploaded zip.'

            order_no = available_quantity = rate = None
            length = width = None
            if error_message is None:
                try:
                    order_no = int(float(record.get("Order No") or 0))
                    available_quantity = record.get("Available Quantity") or None
                    available_quantity = int(float(available_quantity)) if available_quantity else None
                    rate = record.get("Rate per Piece") or None
                    rate = float(rate) if rate else None
                    length = float(record["Length"])
                    width = float(record["Width"])
                except (TypeError, ValueError):
                    error_message = "One or more numeric fields (Order No, Length, Width, etc.) are invalid."

            action: str | None = None
            if error_message is None:
                existing = await self.product_repository.get_by_supplier_and_bar_code(
                    supplier_id, record["Bar Code"]
                )
                action = "updated" if existing else "created"

                if commit:
                    image_url = existing.image_url if existing and not image_ref else None
                    if image_content is not None:
                        image_url = await self.storage.save_bytes(image_ref, image_content, "products")

                    payload = {
                        "child_category_id": category.id,
                        "supplier_id": supplier_id,
                        "order_no": order_no,
                        "catalog_name": record["Catalog Name"],
                        "design_no": record.get("Design No") or None,
                        "bar_code": record["Bar Code"],
                        "image_url": image_url,
                        "available_quantity": available_quantity,
                        "rate": rate,
                        "length": length,
                        "width": width,
                    }
                    if existing:
                        await self.product_repository.update(existing.id, payload)
                        product_id = existing.id
                    else:
                        product = await self.product_repository.create(payload)
                        product_id = product.id
                    await self.product_filter_value_repository.replace(product_id, filter_value_ids)

                if action == "created":
                    created_count += 1
                else:
                    updated_count += 1
            else:
                error_count += 1

            row_results.append(
                {
                    "row_no": row_no,
                    "catalog_name": catalog_name,
                    "is_success": error_message is None,
                    "action": action,
                    "message": error_message,
                }
            )

        return row_results, total, created_count, updated_count, error_count

    async def preview_upload(
        self,
        supplier_id: uuid.UUID,
        excel_bytes: bytes,
        images_zip_bytes: bytes | None,
    ) -> tuple[list[dict], int, int, int, int]:
        return await self._run_rows(supplier_id, excel_bytes, images_zip_bytes, commit=False)

    async def process_upload(
        self,
        supplier_id: uuid.UUID,
        excel_bytes: bytes,
        excel_filename: str,
        images_zip_bytes: bytes | None,
        uploaded_by: uuid.UUID | None,
    ) -> ProductUploadLog:
        # A hard failure here (corrupt file, a disk/DB error mid-write, anything unexpected)
        # still gets a Log entry — the point of this module is a complete run history, not
        # just successful ones. NotFoundException (bad supplier_id) is the one exception that
        # re-raises as-is: there is no valid supplier to attach a log row to.
        try:
            row_results, total, created_count, updated_count, error_count = await self._run_rows(
                supplier_id, excel_bytes, images_zip_bytes, commit=True
            )
        except NotFoundException:
            raise
        except BadRequestException as exc:
            return await self.log_repository.create(
                {
                    "supplier_id": supplier_id,
                    "uploaded_by": uploaded_by,
                    "file_name": excel_filename,
                    "total_rows": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "status": "failed",
                    "error_message": exc.detail,
                }
            )
        except Exception:
            # The admin only ever sees the generic message below — the real exception (with
            # traceback) still needs to reach the server logs, or this failure mode is
            # undiagnosable. Caught here specifically so it never reaches the global handler
            # (which would 500 the request instead of returning a normal, logged Failed run).
            logger.exception(
                "product_upload_failed", supplier_id=str(supplier_id), file_name=excel_filename
            )
            return await self.log_repository.create(
                {
                    "supplier_id": supplier_id,
                    "uploaded_by": uploaded_by,
                    "file_name": excel_filename,
                    "total_rows": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "status": "failed",
                    "error_message": "Unexpected server error while processing this file. Please try again.",
                }
            )

        if total == 0:
            status, error_message = "failed", "The sheet has no product rows to import."
        elif error_count == 0:
            status, error_message = "success", None
        elif created_count + updated_count > 0:
            status, error_message = "partial", None
        else:
            status, error_message = "failed", None

        log = await self.log_repository.create(
            {
                "supplier_id": supplier_id,
                "uploaded_by": uploaded_by,
                "file_name": excel_filename,
                "total_rows": total,
                "success_count": created_count + updated_count,
                "error_count": error_count,
                "status": status,
                "error_message": error_message,
            }
        )
        await self.log_item_repository.bulk_create(log.id, row_results)
        return log

    # ---------------------------------------------------------------- logs

    async def list_logs(
        self,
        pagination: PaginationParams,
        search: str | None,
        supplier_id: uuid.UUID | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[ProductUploadLog], int]:
        rows, total = await self.log_repository.list_logs(
            supplier_id=supplier_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
            offset=pagination.offset,
            limit=pagination.limit,
        )
        return list(rows), total

    async def get_log_detail(self, log_id: uuid.UUID) -> tuple[ProductUploadLog, list[ProductUploadLogItem]]:
        log = await self.log_repository.get_by_id(log_id)
        if log is None:
            raise NotFoundException("Upload log")
        rows = await self.log_item_repository.list_for_log(log_id)
        return log, rows

    async def get_own_log_detail(
        self, log_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> tuple[ProductUploadLog, list[ProductUploadLogItem]]:
        """Same 404 either way (missing vs. belongs to another supplier) — mirrors
        get_own_product/get_own_value; see products/service.py."""
        log, rows = await self.get_log_detail(log_id)
        if log.supplier_id != supplier_id:
            raise NotFoundException("Upload log")
        return log, rows
