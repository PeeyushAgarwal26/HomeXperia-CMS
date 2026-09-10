import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, model_validator


class SupplierListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    username: str
    logo_url: str | None
    profile_image_url: str | None
    email: str | None
    phone_number: str
    gst_number: str | None
    state: str
    city: str
    web_link: str | None
    categories: list[str]
    is_active: bool


class SupplierDetail(BaseModel):
    id: uuid.UUID
    name: str
    start_of_subscription: date | None
    email: str | None
    phone_number: str
    gst_number: str | None
    address: str | None
    pin_code: str | None
    state_code: str
    city: str
    web_link: str | None
    logo_url: str | None
    profile_image_url: str | None
    username: str
    is_active: bool
    linked_customer_id: uuid.UUID | None


class LinkedAccountCreatedResponse(BaseModel):
    """Returned by both the Supplier->Customer and Customer->Supplier linking
    endpoints — just enough for the admin UI to show what was created."""

    linked_id: uuid.UUID
    login_identifier: str  # customer_code or username, whichever was just created


class SupplierCreateResponse(SupplierDetail):
    # Set only when also_create_customer was checked — surfaces that linked
    # account's login identifier too, since it isn't shown anywhere else.
    linked_customer: LinkedAccountCreatedResponse | None = None


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    start_of_subscription: date | None = None
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    web_link: str | None = None
    logo_url: str | None = None
    profile_image_url: str | None = None
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    confirm_password: str
    # Auto-provisions a linked Customer identity (own customer_code, same
    # password as this account) so this supplier can also log into the
    # Client Portal — see SupplierService.create_linked_customer.
    also_create_customer: bool = False

    @model_validator(mode="after")
    def passwords_match(self) -> "SupplierCreateRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class CreateCustomerAccountRequest(BaseModel):
    password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "CreateCustomerAccountRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class SupplierUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    start_of_subscription: date | None = None
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    web_link: str | None = None
    logo_url: str | None = None
    profile_image_url: str | None = None
    username: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8)
    confirm_password: str | None = None

    @model_validator(mode="after")
    def passwords_match_if_present(self) -> "SupplierUpdateRequest":
        if (self.password is None) != (self.confirm_password is None):
            raise ValueError("Both password and confirm_password are required to change the password.")
        if self.password is not None and self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class StatusUpdateRequest(BaseModel):
    is_active: bool


class SupplierCategoriesRequest(BaseModel):
    child_category_ids: list[uuid.UUID]


class SupplierCategoriesResponse(BaseModel):
    child_category_ids: list[uuid.UUID]


class AssignAccessRequest(BaseModel):
    module_keys: list[str]


class AssignAccessResponse(BaseModel):
    module_keys: list[str]
