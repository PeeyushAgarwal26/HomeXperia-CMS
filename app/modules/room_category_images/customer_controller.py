import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer_optional
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.customers.models import Customer
from app.modules.room_category_images.schemas import LegacyHotspotItem
from app.modules.room_category_images.service import RoomCategoryImageService

# Prefix is "/room", not "/customer/room" — matches the real, unmodified
# homexperia-client-frontend's roomHotspotService.js exactly
# (axiosInstance.get("/room/image-hotspots", ...)), which this is a drop-in
# backend for, not a fresh design.
router = APIRouter(prefix="/room", tags=["Customer Room Hotspots"])
controller = BaseController()


@router.get("/image-hotspots", response_model=APIResponse[list[LegacyHotspotItem]])
async def list_image_hotspots(
    room_category_image_id: Annotated[uuid.UUID, Query()],
    # Optional, not required: the Shopify-embed room-configurator screen has
    # no logged-in customer at all and must still be able to look up
    # hotspots (same x-visualizer-key-or-Bearer-token pattern the /visualizer
    # routes already use). The service below never reads `customer` — this
    # is purely an auth gate, so relaxing it here is safe.
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await RoomCategoryImageService(session).list_hotspots_for_customer(room_category_image_id)
    return controller.success(data=data)
