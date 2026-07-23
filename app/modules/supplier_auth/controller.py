from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.response import APIResponse
from app.common.supplier_deps import get_current_supplier
from app.db.session import get_db_session
from app.modules.auth.schemas import TokenPair
from app.modules.suppliers.models import Supplier
from app.modules.supplier_auth.schemas import (
    MyCategoryItem,
    SupplierChangePasswordRequest,
    SupplierLoginRequest,
    SupplierLoginResponse,
    SupplierLogoutRequest,
    SupplierMyProfileResponse,
    SupplierProfile,
    SupplierRefreshRequest,
    UpdateSupplierMyProfileRequest,
)
from app.modules.supplier_auth.service import SupplierAuthService

router = APIRouter(prefix="/supplier-auth", tags=["Supplier Auth"])
controller = BaseController()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/login", response_model=APIResponse[SupplierLoginResponse])
async def supplier_login(
    body: SupplierLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await SupplierAuthService(session).login(
        body.username, body.password, _client_ip(request), _user_agent(request)
    )
    return controller.success(data=result, message="Login successful.")


@router.post("/refresh", response_model=APIResponse[TokenPair])
async def supplier_refresh(
    body: SupplierRefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await SupplierAuthService(session).refresh(
        body.refresh_token, _client_ip(request), _user_agent(request)
    )
    return controller.success(data=result)


@router.post("/logout", response_model=APIResponse[None])
async def supplier_logout(
    body: SupplierLogoutRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await SupplierAuthService(session).logout(supplier.id, body.refresh_token)
    return controller.success(message="Logged out.")


@router.post("/change-password", response_model=APIResponse[None])
async def supplier_change_password(
    body: SupplierChangePasswordRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await SupplierAuthService(session).change_password(
        supplier, body.current_password, body.new_password
    )
    return controller.success(message="Password changed successfully.")


@router.get("/me", response_model=APIResponse[SupplierProfile])
async def supplier_me(supplier: Supplier = Depends(get_current_supplier)) -> APIResponse:
    return controller.success(data=SupplierProfile.model_validate(supplier, from_attributes=True))


@router.get("/me/categories", response_model=APIResponse[list[MyCategoryItem]])
async def supplier_my_categories(
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    categories = await SupplierAuthService(session).get_my_categories(supplier.id)
    data = [
        MyCategoryItem(child_category_id=c.id, parent_name=c.parent_category.name, child_name=c.name)
        for c in categories
    ]
    return controller.success(data=data)


@router.get("/me/permissions", response_model=APIResponse[list[str]])
async def supplier_my_permissions(
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    module_keys = await SupplierAuthService(session).get_my_module_keys(supplier.id)
    return controller.success(data=module_keys)


@router.get("/me/profile", response_model=APIResponse[SupplierMyProfileResponse])
async def get_my_profile(supplier: Supplier = Depends(get_current_supplier)) -> APIResponse:
    return controller.success(data=SupplierMyProfileResponse.model_validate(supplier, from_attributes=True))


@router.put("/me/profile", response_model=APIResponse[SupplierMyProfileResponse])
async def update_my_profile(
    body: UpdateSupplierMyProfileRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    updated = await SupplierAuthService(session).update_my_profile(supplier, body)
    return controller.success(
        data=SupplierMyProfileResponse.model_validate(updated, from_attributes=True),
        message="Profile updated successfully.",
    )
