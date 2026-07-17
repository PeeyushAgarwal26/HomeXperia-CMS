import uuid

from pydantic import BaseModel, Field, model_validator


class AdminUserProfile(BaseModel):
    id: uuid.UUID
    name: str
    username: str
    email: str
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
    email: str
    is_super_admin: bool
    permitted_module_keys: list[str]
