from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer_optional
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.customers.models import Customer
from app.modules.room_categories.schemas import RoomCategoryCustomerItem
from app.modules.room_categories.service import RoomCategoryService

router = APIRouter(prefix="/customer/room-categories", tags=["Customer Room Categories"])
controller = BaseController()


@router.get("", response_model=APIResponse[list[RoomCategoryCustomerItem]])
async def list_room_categories_for_customer(
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await RoomCategoryService(session).list_active_for_customer()
    return controller.success(data=data)
