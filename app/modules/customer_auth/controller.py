from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.auth.schemas import TokenPair
from app.modules.customer_auth.schemas import (
    CustomerLoginRequest,
    CustomerLoginResponse,
    CustomerLogoutRequest,
    CustomerMyProfileResponse,
    CustomerRefreshRequest,
    UpdateCustomerMyProfileRequest,
)
from app.modules.customer_auth.service import CustomerAuthService
from app.modules.customers.models import Customer

router = APIRouter(prefix="/customer-auth", tags=["Customer Auth"])
controller = BaseController()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/login", response_model=APIResponse[CustomerLoginResponse])
async def customer_login(
    body: CustomerLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await CustomerAuthService(session).login(
        body.customer_code, body.password, _client_ip(request), _user_agent(request)
    )
    return controller.success(data=result, message="Login successful.")


@router.post("/refresh", response_model=APIResponse[TokenPair])
async def customer_refresh(
    body: CustomerRefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await CustomerAuthService(session).refresh(
        body.refresh_token, _client_ip(request), _user_agent(request)
    )
    return controller.success(data=result)


@router.post("/logout", response_model=APIResponse[None])
async def customer_logout(
    body: CustomerLogoutRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await CustomerAuthService(session).logout(customer.id, body.refresh_token)
    return controller.success(message="Logged out.")


@router.get("/me/profile", response_model=APIResponse[CustomerMyProfileResponse])
async def get_my_profile(customer: Customer = Depends(get_current_customer)) -> APIResponse:
    return controller.success(data=CustomerMyProfileResponse.model_validate(customer, from_attributes=True))


@router.put("/me/profile", response_model=APIResponse[CustomerMyProfileResponse])
async def update_my_profile(
    body: UpdateCustomerMyProfileRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    updated = await CustomerAuthService(session).update_my_profile(customer, body)
    return controller.success(
        data=CustomerMyProfileResponse.model_validate(updated, from_attributes=True),
        message="Profile updated successfully.",
    )
