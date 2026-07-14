from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import get_current_user
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.geo.repository import StateRepository
from app.modules.geo.schemas import StateItem

router = APIRouter(prefix="/geo", tags=["Geo"])
controller = BaseController()


@router.get("/states", response_model=APIResponse[list[StateItem]])
async def list_states(
    _: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    states = await StateRepository(session).list_all()
    data = [StateItem(code=s.code, name=s.name) for s in states]
    return controller.success(data=data)
