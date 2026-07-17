from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import get_current_user
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.categories.schemas import ParentCategoryNode
from app.modules.categories.service import CategoryService

router = APIRouter(prefix="/categories", tags=["Categories"])
controller = BaseController()


@router.get("", response_model=APIResponse[list[ParentCategoryNode]])
async def get_categories(
    _: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    tree = await CategoryService(session).get_tree()
    return controller.success(data=tree)
