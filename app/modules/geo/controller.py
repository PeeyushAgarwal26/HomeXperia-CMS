from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import get_current_user
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.geo.repository import CityRepository, StateRepository
from app.modules.geo.schemas import CityItem, StateItem

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


@router.get("/cities", response_model=APIResponse[list[CityItem]])
async def list_cities(
    state_code: Annotated[str, Query()],
    _: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    """Suggestions only — the City field itself stays free text (see City model
    docstring), so this is never used to reject a value, only to help fill one in."""
    cities = await CityRepository(session).list_by_state(state_code)
    data = [CityItem(name=c.name) for c in cities]
    return controller.success(data=data)
