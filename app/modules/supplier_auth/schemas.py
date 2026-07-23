import uuid

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.auth.schemas import TokenPair


class SupplierLoginRequest(BaseModel):
    username: str
    password: str


class SupplierProfile(BaseModel):
    id: uuid.UUID
    name: str
    username: str
    email: str | None
    logo_url: str | None


class SupplierLoginResponse(TokenPair):
    supplier: SupplierProfile


class SupplierRefreshRequest(BaseModel):
    refresh_token: str


class SupplierLogoutRequest(BaseModel):
    refresh_token: str


class MyCategoryItem(BaseModel):
    child_category_id: uuid.UUID
    parent_name: str
    child_name: str


class SupplierChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "SupplierChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class SupplierMyProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone_number: str
    gst_number: str | None
    address: str | None
    pin_code: str | None
    state_code: str
    city: str
    web_link: str | None
    logo_url: str | None
    username: str


# Deliberately excludes username/password (see /supplier-auth/change-password),
# is_active (a supplier can't deactivate themselves), and start_of_subscription
# (an admin-managed business term, not the supplier's own contact info) — same
# self-service-vs-admin-managed split as UpdateMyProfileRequest for admins.
class UpdateSupplierMyProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    web_link: str | None = None
    logo_url: str | None = None
