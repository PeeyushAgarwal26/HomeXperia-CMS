from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import get_current_user
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MeResponse,
    MyProfileResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenPair,
    UpdateMyProfileRequest,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
controller = BaseController()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/login", response_model=APIResponse[LoginResponse])
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await AuthService(session).login(
        body.username, body.password, _client_ip(request), _user_agent(request)
    )
    return controller.success(data=result, message="Login successful.")


@router.post("/forgot-password", response_model=APIResponse[None])
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AuthService(session).forgot_password(body.username, _client_ip(request))
    return controller.success(message="If that account exists, a reset link has been sent.")


@router.post("/reset-password", response_model=APIResponse[None])
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AuthService(session).reset_password(body.token, body.new_password)
    return controller.success(message="Password reset successfully.")


@router.post("/refresh", response_model=APIResponse[TokenPair])
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    result = await AuthService(session).refresh(
        body.refresh_token, _client_ip(request), _user_agent(request)
    )
    return controller.success(data=result)


@router.post("/logout", response_model=APIResponse[None])
async def logout(
    body: LogoutRequest,
    admin_user: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AuthService(session).logout(admin_user.id, body.refresh_token)
    return controller.success(message="Logged out.")


@router.post("/change-password", response_model=APIResponse[None])
async def change_password(
    body: ChangePasswordRequest,
    admin_user: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AuthService(session).change_password(admin_user, body.current_password, body.new_password)
    return controller.success(message="Password changed successfully.")


@router.get("/me", response_model=APIResponse[MeResponse])
async def me(
    admin_user: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    permitted_module_keys = await AuthService(session).get_permitted_module_keys(admin_user)
    return controller.success(
        data=MeResponse(
            id=admin_user.id,
            name=admin_user.name,
            username=admin_user.username,
            email=admin_user.email,
            is_super_admin=admin_user.is_super_admin,
            permitted_module_keys=permitted_module_keys,
        )
    )


@router.get("/profile", response_model=APIResponse[MyProfileResponse])
async def get_my_profile(
    admin_user: AdminUser = Depends(get_current_user),
) -> APIResponse:
    return controller.success(data=MyProfileResponse.model_validate(admin_user, from_attributes=True))


@router.put("/profile", response_model=APIResponse[MyProfileResponse])
async def update_my_profile(
    body: UpdateMyProfileRequest,
    admin_user: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    updated = await AuthService(session).update_my_profile(admin_user, body)
    return controller.success(
        data=MyProfileResponse.model_validate(updated, from_attributes=True),
        message="Profile updated successfully.",
    )
