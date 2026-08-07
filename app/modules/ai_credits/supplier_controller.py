from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.pagination import PaginationParams
from app.common.response import APIResponse
from app.common.supplier_deps import get_current_supplier
from app.db.session import get_db_session
from app.modules.ai_credits.repository import AccountKey
from app.modules.ai_credits.schemas import AuditLogItem, BalanceSheetResponse
from app.modules.ai_credits.service import AiCreditService
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/supplier/ai-credits", tags=["Supplier AI Credits"])
controller = BaseController()


@router.get("/balance-sheet", response_model=APIResponse[BalanceSheetResponse])
async def get_my_balance_sheet(
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await AiCreditService(session).compute_balance_sheet(AccountKey.for_supplier(supplier.id))
    return controller.success(data=data)


@router.get("/audit-log", response_model=APIResponse[list[AuditLogItem]])
async def get_my_audit_log(
    pagination: Annotated[PaginationParams, Depends()],
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data, total = await AiCreditService(session).get_audit_log(
        AccountKey.for_supplier(supplier.id), pagination.offset, pagination.limit
    )
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)
