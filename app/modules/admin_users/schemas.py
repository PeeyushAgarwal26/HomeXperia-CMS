import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, model_validator


class SubAdminListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    profile_image_url: str | None
    email: str
    state: str
    phone_number: str
    city: str
    is_active: bool


class SubAdminDetail(BaseModel):
    id: uuid.UUID
    name: str
    date_of_birth: date | None
    email: str
    address: str | None
    phone_number: str
    pin_code: str
    state_code: str
    city: str
    profile_image_url: str | None
    username: str
    is_active: bool


class SubAdminCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    date_of_birth: date | None = None
    email: EmailStr
    address: str | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    pin_code: str = Field(min_length=4, max_length=10)
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    profile_image_url: str | None = None
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "SubAdminCreateRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class SubAdminUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    date_of_birth: date | None = None
    email: EmailStr
    address: str | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    pin_code: str = Field(min_length=4, max_length=10)
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    profile_image_url: str | None = None
    username: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8)
    confirm_password: str | None = None

    @model_validator(mode="after")
    def passwords_match_if_present(self) -> "SubAdminUpdateRequest":
        if (self.password is None) != (self.confirm_password is None):
            raise ValueError("Both password and confirm_password are required to change the password.")
        if self.password is not None and self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class StatusUpdateRequest(BaseModel):
    is_active: bool


class AssignAccessRequest(BaseModel):
    module_keys: list[str]


class AssignAccessResponse(BaseModel):
    module_keys: list[str]
