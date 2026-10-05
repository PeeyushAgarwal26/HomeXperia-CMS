from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer_optional
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.categories.schemas import ChildCategoryCustomerItem, ParentCategoryCustomerItem
from app.modules.categories.service import CategoryService
from app.modules.customers.models import Customer

router = APIRouter(prefix="/customer/categories", tags=["Customer Categories"])
controller = BaseController()

# get_current_customer_optional, same as the visualizer routes — the
# Shopify-embed pages need this data with no Homexperia login too.


@router.get("/parents", response_model=APIResponse[list[ParentCategoryCustomerItem]])
async def list_parents_for_customer(
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    parents = await CategoryService(session).get_customer_parents()
    data = [
        ParentCategoryCustomerItem(
            id=p.id, name=p.name, category_code=p.name.strip().upper(), icon_url=p.icon_url
        )
        for p in parents
    ]
    return controller.success(data=data)


@router.get("/children", response_model=APIResponse[list[ChildCategoryCustomerItem]])
async def list_children_for_customer(
    category_code: Annotated[str, Query()],
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    children = await CategoryService(session).get_customer_children(category_code)
    data = [
        ChildCategoryCustomerItem(
            id=c.id,
            name=c.name,
            unique_code=c.name.strip().lower().replace(" ", "_"),
            visualizer_type=c.visualizer_type,
            icon_url=c.icon_url,
            parent_category_id=c.parent_category_id,
        )
        for c in children
    ]
    return controller.success(data=data)
