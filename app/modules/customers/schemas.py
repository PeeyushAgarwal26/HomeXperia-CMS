import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class CustomerListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    profile_image_url: str | None
    customer_code: str
    email: str | None
    phone_number: str
    gst_number: str | None
    device_limit: int
    active_device_count: int
    last_login_at: datetime | None
    suppliers: list[str]
    is_active: bool


class CustomerDetail(BaseModel):
    id: uuid.UUID
    name: str
    date_of_start: date | None
    email: str | None
    phone_number: str
    gst_number: str | None
    address: str | None
    pin_code: str | None
    state_code: str | None
    city: str | None
    profile_image_url: str | None
    device_limit: int
    customer_code: str
    is_active: bool


class CustomerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    date_of_start: date | None = None
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str | None = None
    city: str | None = None
    profile_image_url: str | None = None
    device_limit: int = Field(ge=1, le=100)
    customer_code: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "CustomerCreateRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class CustomerUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    date_of_start: date | None = None
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str | None = None
    city: str | None = None
    profile_image_url: str | None = None
    device_limit: int = Field(ge=1, le=100)
    customer_code: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8)
    confirm_password: str | None = None

    @model_validator(mode="after")
    def passwords_match_if_present(self) -> "CustomerUpdateRequest":
        if (self.password is None) != (self.confirm_password is None):
            raise ValueError("Both password and confirm_password are required to change the password.")
        if self.password is not None and self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class StatusUpdateRequest(BaseModel):
    is_active: bool


class MapSuppliersRequest(BaseModel):
    supplier_ids: list[uuid.UUID]


class MapSuppliersResponse(BaseModel):
    supplier_ids: list[uuid.UUID]
