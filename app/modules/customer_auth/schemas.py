import uuid

from pydantic import BaseModel

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


class CustomerLoginResponse(TokenPair):
    customer: CustomerProfile
    # Every supplier this customer is mapped to that has a logo set — lets
    # the client-facing app show branding for all of them, not just one.
    supplier_logos: list[str] = []


class CustomerRefreshRequest(BaseModel):
    refresh_token: str


class CustomerLogoutRequest(BaseModel):
    refresh_token: str
