import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class CustomerListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    profile_image_url: str | None
    logo_url: str | None
    customer_code: str
    email: str | None
    phone_number: str
    gst_number: str | None
    city: str | None
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
    logo_url: str | None
    device_limit: int
    customer_code: str
    is_active: bool
    linked_supplier_id: uuid.UUID | None


class LinkedAccountCreatedResponse(BaseModel):
    linked_id: uuid.UUID
    login_identifier: str


class CustomerCreateResponse(CustomerDetail):
    # Set only when also_create_supplier was checked — surfaces that linked
    # account's login identifier too, since it isn't shown anywhere else.
    linked_supplier: LinkedAccountCreatedResponse | None = None


class CustomerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    date_of_start: date | None = None
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    profile_image_url: str | None = None
    logo_url: str | None = None
    device_limit: int = Field(ge=1, le=100)
    customer_code: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    confirm_password: str
    # Auto-provisions a linked Supplier identity (own username, same password
    # as this account) so this customer can also log into the Supplier Portal
    # — see CustomerService.promote_to_supplier. supplier_username is
    # required only when this is set.
    also_create_supplier: bool = False
    supplier_username: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def passwords_match(self) -> "CustomerCreateRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self

    @model_validator(mode="after")
    def supplier_username_required_if_promoting(self) -> "CustomerCreateRequest":
        if self.also_create_supplier and not self.supplier_username:
            raise ValueError("A username is required to also create a supplier account.")
        return self


class PromoteToSupplierRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    # Only used if this customer doesn't already have state_code/city set —
    # Supplier requires both, Customer allows either to be null.
    state_code: str | None = Field(default=None, min_length=1, max_length=10)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "PromoteToSupplierRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class CustomerUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    date_of_start: date | None = None
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    profile_image_url: str | None = None
    logo_url: str | None = None
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


class SupplierCustomerListItem(BaseModel):
    id: uuid.UUID
    sno: int
    name: str
    customer_code: str
    city: str | None


# primary_color/secondary_color are placeholder fields — the real field set
# for a customer's theme is still pending discussion with the client. Null
# means no theme configured yet.
class CustomerThemeDetail(BaseModel):
    customer_id: uuid.UUID
    primary_color: str | None
    secondary_color: str | None


class UpdateCustomerThemeRequest(BaseModel):
    primary_color: str | None = Field(default=None, max_length=20)
    secondary_color: str | None = Field(default=None, max_length=20)


# This customer's OWN theme (Customer.primary_color/secondary_color) — set
# directly by admin/sub-admin, with no supplier involved. Distinct from
# CustomerThemeDetail above, which is one specific supplier's branding for
# this customer.
class CustomerDirectThemeDetail(BaseModel):
    customer_id: uuid.UUID
    primary_color: str | None
    secondary_color: str | None


class UpdateCustomerDirectThemeRequest(BaseModel):
    primary_color: str | None = Field(default=None, max_length=20)
    secondary_color: str | None = Field(default=None, max_length=20)


# Admin-facing view: one row per supplier this customer is mapped to, showing
# whichever theme that specific supplier has configured for them (if any).
class CustomerSupplierThemeItem(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    primary_color: str | None
    secondary_color: str | None


class UpdateCustomerSupplierThemeRequest(BaseModel):
    primary_color: str | None = Field(default=None, max_length=20)
    secondary_color: str | None = Field(default=None, max_length=20)
