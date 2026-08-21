import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, model_validator


class AdminUserProfile(BaseModel):
    id: uuid.UUID
    name: str
    username: str
    email: str | None
    is_super_admin: bool
    profile_image_url: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str


class LoginResponse(TokenPair):
    admin_user: AdminUserProfile


class ForgotPasswordRequest(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class MeResponse(BaseModel):
    id: uuid.UUID
    name: str
    username: str
    email: str | None
    profile_image_url: str | None = None
    is_super_admin: bool
    permitted_module_keys: list[str]


class MyProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    date_of_birth: date | None
    email: str | None
    address: str | None
    phone_number: str
    pin_code: str
    state_code: str
    city: str
    profile_image_url: str | None
    username: str
    is_super_admin: bool


# Deliberately excludes username/password (see /auth/change-password) and
# is_active (a user can't deactivate themselves) — this is self-service
# profile editing, not the admin-only "manage this sub-admin" form.
class UpdateMyProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    date_of_birth: date | None = None
    email: EmailStr | None = None
    address: str | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    pin_code: str = Field(min_length=4, max_length=10)
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    profile_image_url: str | None = None
