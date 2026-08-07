from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.customers.models import Customer
from app.modules.qr_generator.schemas import CatalogueLookupResponse
from app.modules.qr_generator.service import QrGeneratorService

router = APIRouter(prefix="/customer", tags=["Customer QR Catalogue"])
controller = BaseController()


@router.get("/qr-catalogue-lookup", response_model=APIResponse[CatalogueLookupResponse])
async def qr_catalogue_lookup(
    filter_value: Annotated[str, Query()],
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await QrGeneratorService(session).get_catalogue_lookup(customer.id, filter_value)
    return controller.success(data=data)
