from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.visualizer.schemas import CacheClearResponse, CacheStatsResponse, CleanupResponse
from app.modules.visualizer.service import VisualizerService

# Historically "Visualizer Admin" — per-customer AI usage/token tracking has
# since moved to AI Credits' per-supplier Pipeline Usage panel (reads the
# same UsageLog/TooltipUsage tables). This module key and router now cover
# only image-cache management, which isn't a billing concern and has no
# home anywhere else.
router = APIRouter(prefix="/visualizer/admin", tags=["Visualizer Cache Management"])
controller = BaseController()

_require_visualizer_admin = require_module_permission("visualizer_admin")


@router.delete("/cleanup/{folder}", response_model=APIResponse[CleanupResponse])
async def cleanup_folder(
    folder: str,
    _: AdminUser = Depends(_require_visualizer_admin),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).cleanup_folder(folder)
    return controller.success(data=result)


@router.get("/cache/stats", response_model=APIResponse[CacheStatsResponse])
async def cache_stats(
    _: AdminUser = Depends(_require_visualizer_admin),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).cache_stats()
    return controller.success(data=result)


@router.post("/cache/clear", response_model=APIResponse[CacheClearResponse])
async def cache_clear(
    _: AdminUser = Depends(_require_visualizer_admin),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await VisualizerService(session).cache_clear()
    return controller.success(data=result)
