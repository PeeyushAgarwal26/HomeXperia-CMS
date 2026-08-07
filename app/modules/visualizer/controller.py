from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer_optional
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.customers.models import Customer
from app.modules.visualizer.schemas import (
    CurtainGenerationRequest,
    MaskGenerationRequest,
    MaskGenerationResponse,
    ProcessRoomRequest,
    ProcessRoomResponse,
    ResetRoomRequest,
    ResetRoomResponse,
    RoomDetailResponse,
    RoomListResponse,
    RugVisualizerSceneRequest,
    RugVisualizerSceneResponse,
    WallArtVisualizerSceneRequest,
    WallArtVisualizerSceneResponse,
)
from app.modules.visualizer.service import VisualizerService

router = APIRouter(prefix="/visualizer", tags=["Visualizer"])
controller = BaseController()

# get_current_customer_optional (not the strict get_current_customer) on every
# route below — the Shopify-embed pages call these with no Homexperia login
# at all, authenticated only by the shared visualizer service key. See
# app/common/customer_deps.py.


@router.post("/upload", response_model=APIResponse[dict])
async def upload(
    body: dict[str, Any],
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).upload(body)
    return controller.success(data=result)


@router.post("/process-room", response_model=APIResponse[ProcessRoomResponse])
async def process_room(
    body: ProcessRoomRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    customer_id = customer.id if customer else None
    result = await VisualizerService(session).process_room(customer_id, body)
    return controller.success(data=result)


@router.post("/curtain-generation", response_model=APIResponse[dict])
async def curtain_generation(
    body: CurtainGenerationRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    customer_id = customer.id if customer else None
    result = await VisualizerService(session).curtain_generation(customer_id, body)
    return controller.success(data=result)


@router.post("/reset", response_model=APIResponse[ResetRoomResponse])
async def reset(
    body: ResetRoomRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).reset(body)
    return controller.success(data=result)


@router.post("/mask-generation", response_model=APIResponse[MaskGenerationResponse])
async def mask_generation(
    body: MaskGenerationRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).mask_generation(body)
    return controller.success(data=result)


@router.post("/generate-pdf")
async def generate_pdf(
    body: dict[str, Any],
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    pdf_bytes = await VisualizerService(session).generate_pdf(body)
    room_id = body.get("roomID", "Unknown")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="HomeXperia_Design_{room_id}.pdf"'},
    )


@router.post("/rug-visualizer-scene", response_model=APIResponse[RugVisualizerSceneResponse])
async def rug_visualizer_scene(
    body: RugVisualizerSceneRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).rug_visualizer_scene(body)
    return controller.success(data=result)


@router.post("/wallart-visualizer-scene", response_model=APIResponse[WallArtVisualizerSceneResponse])
async def wallart_visualizer_scene(
    body: WallArtVisualizerSceneRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).wallart_visualizer_scene(body)
    return controller.success(data=result)


@router.get("/rooms", response_model=APIResponse[RoomListResponse])
async def list_rooms(
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).list_rooms()
    return controller.success(data=result)


@router.get("/rooms/{room_id}", response_model=APIResponse[RoomDetailResponse])
async def get_room(
    room_id: str,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).get_room(room_id)
    return controller.success(data=result)
