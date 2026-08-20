import uuid

from pydantic import BaseModel, EmailStr, Field

from app.modules.auth.schemas import TokenPair


class CustomerLoginRequest(BaseModel):
    customer_code: str
    password: str


class CustomerProfile(BaseModel):
    id: uuid.UUID
    name: str
    customer_code: str
    email: str | None
    phone_number: str
    profile_image_url: str | None
    # This customer's own business logo — see Customer.logo_url. Directly
    # settable via /customer-auth/me/profile, unlike the old approach this
    # replaced (deriving it from a linked Supplier identity, if any).
    logo_url: str | None


class CustomerLoginResponse(TokenPair):
    customer: CustomerProfile
    # Every supplier this customer is mapped to (buys from) that has a logo
    # set — lets the client-facing app show branding for all of them, not
    # just one. customer.logo_url (above) is this customer's OWN logo.
    supplier_logos: list[str] = []


class CustomerRefreshRequest(BaseModel):
    refresh_token: str


class CustomerLogoutRequest(BaseModel):
    refresh_token: str


class CustomerMyProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone_number: str
    gst_number: str | None
    address: str | None
    pin_code: str | None
    state_code: str | None
    city: str | None
    profile_image_url: str | None
    logo_url: str | None
    customer_code: str


# Deliberately excludes customer_code/password (no self-service password
# change exists for customers today — only login), is_active (a customer
# can't deactivate themselves), and date_of_start/device_limit (admin-managed
# business terms, not the customer's own contact info) — same self-service-
# vs-admin-managed split as UpdateSupplierMyProfileRequest.
class UpdateCustomerMyProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    email: EmailStr | None = None
    phone_number: str = Field(min_length=10, max_length=20)
    gst_number: str | None = None
    address: str | None = None
    pin_code: str | None = None
    state_code: str | None = Field(default=None, min_length=1, max_length=10)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    profile_image_url: str | None = None
    logo_url: str | None = None
