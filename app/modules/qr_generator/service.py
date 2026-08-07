"""Generates a QR code encoding the real customer-facing storefront's
/verify?customer-code=...&filter-value=... URL — confirmed (via a live audit
of homexperia-client-frontend's VerifyToken.jsx) to be the exact URL shape
and hyphenated query param names that page actually reads on scan. The
python-qrcode + Pillow logo-overlay approach mirrors
homexperia-client-backend/generate_qrcode.py's settings (version 1, "H"
error correction, box_size 10, border 4) — that script was a dead,
hand-edited-per-run stub with no logo support and no parameters at all;
this is the same QR recipe made into a real, parameterized admin feature.

Synchronous by design (qrcode/Pillow/httpx.Client are all sync here), run
via anyio.to_thread from the async service method below — same convention
as the visualizer's PDF/report generation."""

from __future__ import annotations

import io
import uuid
from urllib.parse import quote, urlencode

import httpx
import qrcode
from anyio import to_thread
from PIL import Image
from qrcode.constants import ERROR_CORRECT_H
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.common.storage import get_storage, resolve_uploaded_file_path
from app.core.config import settings
from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.filters.repository import FilterRepository, FilterValueRepository
from app.modules.products.models import Product
from app.modules.products.repository import ProductFilterValueRepository, ProductRepository
from app.modules.qr_generator.repository import QrCatalogueEntryRepository, SavedQrCodeRepository
from app.modules.qr_generator.schemas import (
    CatalogueEntryCreateRequest,
    CatalogueEntryDetail,
    CatalogueEntryUpdateRequest,
    CatalogueLookupResponse,
    CataloguePreviewRequest,
    CataloguePreviewResponse,
    HotspotProductAssignment,
    HotspotProductDetail,
    QrCodeGenerateRequest,
    RoomImagePickerItem,
    SavedQrCodeDetail,
)
from app.modules.room_category_images.repository import (
    RoomCategoryImageHotspotRepository,
    RoomCategoryImageRepository,
)
from app.modules.visualizer.schemas import HotspotLayer, HotspotProduct, ProcessRoomRequest
from app.modules.visualizer.service import VisualizerService

_DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0"}
_DOWNLOAD_TIMEOUT = 15.0
# Fraction of the QR's own width the logo is resized to. "H" error correction
# tolerates ~30% of the code being obscured; staying well under that (with a
# white backing plate for contrast) keeps it reliably scannable.
_LOGO_SIZE_RATIO = 0.22


def _download_logo(url: str) -> Image.Image | None:
    try:
        if url.startswith(("http://", "https://")):
            with httpx.Client() as client:
                resp = client.get(url, headers=_DOWNLOAD_HEADERS, timeout=_DOWNLOAD_TIMEOUT)
            if resp.status_code != 200:
                return None
            return Image.open(io.BytesIO(resp.content)).convert("RGBA")
        local_path = resolve_uploaded_file_path(url)
        if local_path is None or not local_path.exists():
            return None
        return Image.open(local_path).convert("RGBA")
    except Exception:
        return None


def _build_verify_url(customer_code: str, filter_values: list[str]) -> str:
    params = {"customer-code": customer_code}
    if filter_values:
        # Comma-joined into the SAME single "filter-value" param the real
        # scan-handling page reads. NOTE: that page (as it exists today)
        # only ever matches one exact value against one catalog entry — a
        # joined multi-value string won't match anything there yet. This
        # keeps everything in one QR as asked; making a scan actually act on
        # more than one value requires a follow-up change on the
        # customer-frontend side (not done here).
        params["filter-value"] = ",".join(filter_values)
    # urlencode would escape the hyphen-containing keys fine, but the real
    # frontend route only ever sees these two exact keys — spelled out here
    # (rather than relying on dict ordering) so that stays obvious.
    query = urlencode(params, quote_via=quote)
    return f"{settings.customer_frontend_url.rstrip('/')}/verify?{query}"


def _generate_qr_png(customer_code: str, filter_values: list[str], logo_url: str | None) -> bytes:
    url = _build_verify_url(customer_code, filter_values)

    qr = qrcode.QRCode(version=1, error_correction=ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    logo = _download_logo(logo_url) if logo_url else None
    if logo is not None:
        qr_width, qr_height = image.size
        logo_size = int(qr_width * _LOGO_SIZE_RATIO)
        logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)

        plate_size = (logo.size[0] + 16, logo.size[1] + 16)
        plate = Image.new("RGBA", plate_size, (255, 255, 255, 255))
        plate.paste(logo, ((plate_size[0] - logo.size[0]) // 2, (plate_size[1] - logo.size[1]) // 2), logo)

        position = ((qr_width - plate_size[0]) // 2, (qr_height - plate_size[1]) // 2)
        image.paste(plate, position, plate)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class QrGeneratorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.customer_repo = CustomerRepository(session)
        self.entry_repo = QrCatalogueEntryRepository(session)
        self.room_image_repo = RoomCategoryImageRepository(session)
        self.product_repo = ProductRepository(session)
        self.saved_qr_repo = SavedQrCodeRepository(session)

    async def generate(self, data: QrCodeGenerateRequest) -> bytes:
        customer = await self.customer_repo.get_by_customer_code(data.customer_code)
        if customer is None:
            raise NotFoundException("Customer")
        return await to_thread.run_sync(_generate_qr_png, data.customer_code, data.filter_values, data.brand_logo_url)

    # ---- saved QR codes (admin explicitly keeps one after generating it) ----

    async def _to_saved_qr_detail(self, saved) -> SavedQrCodeDetail:
        customer = await self.customer_repo.get_by_id(saved.customer_id)
        return SavedQrCodeDetail(
            id=saved.id,
            customer_id=saved.customer_id,
            customer_name=customer.name if customer else "",
            customer_code=customer.customer_code if customer else "",
            filter_values=saved.filter_values.split(",") if saved.filter_values else [],
            brand_logo_url=saved.brand_logo_url,
            image_url=saved.image_url,
            created_at=saved.created_at,
        )

    async def save_qr_code(self, data: QrCodeGenerateRequest, created_by: uuid.UUID) -> SavedQrCodeDetail:
        customer = await self.customer_repo.get_by_customer_code(data.customer_code)
        if customer is None:
            raise NotFoundException("Customer")
        png_bytes = await to_thread.run_sync(
            _generate_qr_png, data.customer_code, data.filter_values, data.brand_logo_url
        )
        image_url = await get_storage().save_bytes(f"{uuid.uuid4()}.png", png_bytes, "qr-codes")
        saved = await self.saved_qr_repo.create(
            {
                "customer_id": customer.id,
                "filter_values": ",".join(data.filter_values) if data.filter_values else None,
                "brand_logo_url": data.brand_logo_url,
                "image_url": image_url,
                "created_by": created_by,
            }
        )
        return await self._to_saved_qr_detail(saved)

    async def list_saved_qr_codes(
        self, pagination: PaginationParams, search: str | None = None
    ) -> tuple[list[SavedQrCodeDetail], int]:
        items, total = await self.saved_qr_repo.list_with_search(
            search, offset=pagination.offset, limit=pagination.limit
        )
        return [await self._to_saved_qr_detail(item) for item in items], total

    # ---- catalogue mapping (admin) ----

    async def list_room_images(self) -> list[RoomImagePickerItem]:
        rows = await self.entry_repo.list_room_images()
        return [
            RoomImagePickerItem(
                id=image.id,
                image_url=image.image_url,
                room_category_id=image.room_category_id,
                room_category_name=category_name,
            )
            for image, category_name in rows
        ]

    async def _to_hotspot_product_details(self, entry_id) -> list[HotspotProductDetail]:
        rows = await self.entry_repo.get_hotspot_products(entry_id)
        hotspot_repo = RoomCategoryImageHotspotRepository(self.session)
        details = []
        for row in rows:
            product = await self.product_repo.get_by_id(row.product_id)
            if row.hotspot_id is not None:
                # A real, shared room hotspot (floor, wall — never needs a
                # curtain of its own).
                hotspot = await hotspot_repo.get_by_id(row.hotspot_id)
                key_id = hotspot.id if hotspot else row.id
                label = hotspot.label if hotspot else ""
                hotspot_type = hotspot.type if hotspot else ""
                x = hotspot.x if hotspot else 0.0
                y = hotspot.y if hotspot else 0.0
                mask_image_url = hotspot.mask_image_url if hotspot else ""
            else:
                # A curtain panel scoped to THIS mapping only — its geometry
                # lives inline on the junction row, never on a shared hotspot.
                key_id = row.id
                label = row.inline_label or ""
                hotspot_type = row.inline_type or ""
                x = row.inline_x or 0.0
                y = row.inline_y or 0.0
                mask_image_url = row.inline_mask_image_url or ""
            details.append(
                HotspotProductDetail(
                    id=key_id,
                    hotspot_id=row.hotspot_id,
                    product_id=row.product_id,
                    product_name=product.catalog_name if product else "",
                    product_image_url=product.image_url if product else None,
                    product_width=float(product.width) if product and product.width is not None else None,
                    label=label,
                    type=hotspot_type,
                    x=x,
                    y=y,
                    mask_image_url=mask_image_url,
                )
            )
        return details

    async def _to_entry_detail(self, entry) -> CatalogueEntryDetail:
        customer = await self.customer_repo.get_by_id(entry.customer_id)
        room_image = await self.room_image_repo.get_by_id(entry.room_category_image_id)
        return CatalogueEntryDetail(
            id=entry.id,
            customer_id=entry.customer_id,
            customer_name=customer.name if customer else "",
            customer_code=customer.customer_code if customer else "",
            filter_value=entry.filter_value,
            catalog_name=entry.catalog_name,
            room_category_image_id=entry.room_category_image_id,
            room_image_url=entry.override_image_url or (room_image.image_url if room_image else ""),
            hotspot_products=await self._to_hotspot_product_details(entry.id),
        )

    async def list_catalogue_entries(self, customer_id) -> list[CatalogueEntryDetail]:
        entries = await self.entry_repo.list_by_customer(customer_id)
        return [await self._to_entry_detail(entry) for entry in entries]

    async def list_filter_values_for_customer(self, customer_id) -> list[str]:
        """Every existing "Catalogue Name" FilterValue already registered
        under this customer's mapped suppliers — surfaced so the admin's
        Filter Value(s) picker can offer values that predate any QR mapping,
        not just ones a QR catalogue entry has already been saved for.
        Customers relate to FilterValue only indirectly, through suppliers."""
        catalogue_filter = await FilterRepository(self.session).get_by_name_ci("Catalogue Name")
        if catalogue_filter is None:
            return []
        supplier_ids = await CustomerSupplierRepository(self.session).get_supplier_ids(customer_id)
        return await FilterValueRepository(self.session).list_values_for_suppliers(catalogue_filter.id, supplier_ids)

    async def _load_hotspot_products(
        self, assignments: list[HotspotProductAssignment]
    ) -> list[tuple[dict, Product]]:
        """Validates every assignment's product exists, returns (row dict,
        Product) pairs in the same order — the row dict is ready for
        QrCatalogueEntryRepository.set_hotspot_products as-is; the Product
        is kept alongside so the caller can link its filter value without
        an extra fetch. A real hotspot_id passes through unchanged; inline
        curtain-panel geometry maps onto the junction's own inline_* columns
        (never onto the shared room_category_image_hotspots table — see
        QrCatalogueEntryHotspot's docstring)."""
        loaded = []
        for assignment in assignments:
            product = await self.product_repo.get_by_id(assignment.product_id)
            if product is None:
                raise NotFoundException("Product")
            if assignment.hotspot_id is not None:
                row = {"hotspot_id": assignment.hotspot_id, "product_id": product.id}
            else:
                row = {
                    "hotspot_id": None,
                    "product_id": product.id,
                    "inline_label": assignment.label,
                    "inline_type": assignment.type,
                    "inline_x": assignment.x,
                    "inline_y": assignment.y,
                    "inline_mask_image_url": assignment.mask_image_url,
                }
            loaded.append((row, product))
        return loaded

    async def create_catalogue_entry(self, data: CatalogueEntryCreateRequest) -> CatalogueEntryDetail:
        if await self.customer_repo.get_by_id(data.customer_id) is None:
            raise NotFoundException("Customer")
        if await self.room_image_repo.get_by_id(data.room_category_image_id) is None:
            raise NotFoundException("Room category image")
        loaded = await self._load_hotspot_products(data.hotspot_products)
        existing = await self.entry_repo.get_by_customer_and_filter_value(data.customer_id, data.filter_value)
        if existing is not None:
            raise BadRequestException("A catalogue mapping for this customer and filter value already exists.")

        entry = await self.entry_repo.create(
            {
                "customer_id": data.customer_id,
                "filter_value": data.filter_value,
                "catalog_name": data.catalog_name,
                "room_category_image_id": data.room_category_image_id,
                "override_image_url": data.override_image_url,
            }
        )
        await self.entry_repo.set_hotspot_products(entry.id, [row for row, _product in loaded])
        for _row, product in loaded:
            await self._ensure_filter_value_linked(product, data.filter_value)
        return await self._to_entry_detail(entry)

    async def update_catalogue_entry(self, entry_id, data: CatalogueEntryUpdateRequest) -> CatalogueEntryDetail:
        entry = await self.entry_repo.get_by_id(entry_id)
        if entry is None:
            raise NotFoundException("Catalogue mapping")
        if await self.room_image_repo.get_by_id(data.room_category_image_id) is None:
            raise NotFoundException("Room category image")
        loaded = await self._load_hotspot_products(data.hotspot_products)

        updated = await self.entry_repo.update(
            entry_id,
            {
                "catalog_name": data.catalog_name,
                "room_category_image_id": data.room_category_image_id,
                "override_image_url": data.override_image_url,
            },
        )
        await self.entry_repo.set_hotspot_products(entry_id, [row for row, _product in loaded])
        for _row, product in loaded:
            await self._ensure_filter_value_linked(product, entry.filter_value)
        return await self._to_entry_detail(updated)

    async def _ensure_filter_value_linked(self, product: Product, filter_value_text: str) -> None:
        """Keeps the QR catalogue's free-text filter value in sync with the
        real Filters system: the customer-facing Filters panel (and any
        non-QR browsing) can only show/select a "CATALOGUE NAME" value that
        already exists as a real FilterValue row linked to a product — a
        brand-new QR filter value wouldn't otherwise appear there at all."""
        filter_repo = FilterRepository(self.session)
        filter_value_repo = FilterValueRepository(self.session)
        product_filter_value_repo = ProductFilterValueRepository(self.session)

        catalogue_filter = await filter_repo.get_by_name_ci("Catalogue Name")
        if catalogue_filter is None:
            catalogue_filter = await filter_repo.create({"name": "Catalogue Name", "is_active": True})

        filter_value = await filter_value_repo.get_by_value_ci(
            catalogue_filter.id, product.child_category_id, product.supplier_id, filter_value_text
        )
        if filter_value is None:
            filter_value = await filter_value_repo.create(
                {
                    "filter_id": catalogue_filter.id,
                    "child_category_id": product.child_category_id,
                    "supplier_id": product.supplier_id,
                    "value": filter_value_text.strip().upper(),
                    "is_active": True,
                }
            )

        existing_ids = await product_filter_value_repo.get_filter_value_ids(product.id)
        if filter_value.id not in existing_ids:
            await product_filter_value_repo.replace(product.id, [*existing_ids, filter_value.id])

    async def delete_catalogue_entry(self, entry_id) -> None:
        entry = await self.entry_repo.get_by_id(entry_id)
        if entry is None:
            raise NotFoundException("Catalogue mapping")
        await self.entry_repo.hard_delete(entry_id)

    # ---- catalogue lookup (customer-facing — replaces customerCatalog.js) ----

    async def get_catalogue_lookup(self, customer_id, filter_value: str) -> CatalogueLookupResponse:
        entry = await self.entry_repo.get_by_customer_and_filter_value(customer_id, filter_value)
        if entry is None:
            raise NotFoundException("Catalogue mapping")
        room_image = await self.room_image_repo.get_by_id(entry.room_category_image_id)
        catalogue_filter = await FilterRepository(self.session).get_by_name_ci("Catalogue Name")
        return CatalogueLookupResponse(
            catalog_name=entry.catalog_name,
            room_category_image_id=entry.room_category_image_id,
            room_image_url=entry.override_image_url or (room_image.image_url if room_image else ""),
            hotspot_products=await self._to_hotspot_product_details(entry.id),
            catalogue_filter_id=catalogue_filter.id if catalogue_filter else None,
        )

    # ---- live preview (reuses the exact visualizer compositing pipeline) ----

    async def preview_composite(self, data: CataloguePreviewRequest) -> CataloguePreviewResponse:
        room_image = await self.room_image_repo.get_by_id(data.room_category_image_id)
        if room_image is None:
            raise NotFoundException("Room category image")
        hotspot_repo = RoomCategoryImageHotspotRepository(self.session)
        layers = []
        for index, assignment in enumerate(data.hotspot_products):
            product = await self.product_repo.get_by_id(assignment.product_id)
            if product is None:
                raise NotFoundException("Product")
            if assignment.hotspot_id is not None:
                hotspot = await hotspot_repo.get_by_id(assignment.hotspot_id)
                if hotspot is None or hotspot.room_category_image_id != room_image.id:
                    raise NotFoundException("Hotspot")
                layer_id, category, x, y = str(hotspot.id), hotspot.type, hotspot.x, hotspot.y
            else:
                # A curtain-panel hotspot preview_curtain just detected but
                # hasn't been committed to the DB yet — its geometry travels
                # inline on the request instead of a hotspot_id (see
                # PreviewHotspotAssignment). Pydantic's validator already
                # guarantees x/y/type are set whenever hotspot_id isn't.
                layer_id, category, x, y = f"pending-{index}", assignment.type, assignment.x, assignment.y
            layers.append(
                HotspotLayer(
                    hotspotId=layer_id,
                    category=category,
                    coords={"x": x, "y": y},
                    product=HotspotProduct(
                        productImageUrl=product.image_url,
                        productId=str(product.id),
                        width=str(product.width) if product.width is not None else None,
                    ),
                )
            )

        request = ProcessRoomRequest(
            roomId=str(room_image.id),
            baseImageUrl=data.base_image_url or room_image.image_url,
            applyHotspot=layers,
        )
        result = await VisualizerService(self.session).process_room(None, request)
        if not result.success or not result.finalImageUrl:
            raise BadRequestException(result.error or "Could not generate a preview for this combination.")
        return CataloguePreviewResponse(final_image_url=result.finalImageUrl)
