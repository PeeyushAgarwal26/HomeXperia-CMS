import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CustomerLoginHistoryItem(BaseModel):
    customer_id: uuid.UUID
    sno: int
    name: str
    customer_code: str
    device_limit: int
    login_count: int
    login_date: datetime


class CustomerLoginEventDetail(BaseModel):
    id: uuid.UUID
    logged_in_at: datetime
    ip_address: str | None


class LoginHistoryItem(BaseModel):
    id: uuid.UUID
    sno: int
    account_id: uuid.UUID
    name: str
    username: str
    role: Literal["sub_admin", "supplier"]
    logged_in_at: datetime
    ip_address: str | None
