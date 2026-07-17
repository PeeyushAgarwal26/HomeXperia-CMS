import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator

MIN_SCHEDULE_LEAD_MINUTES = 5


class NotificationTemplateListItem(BaseModel):
    id: uuid.UUID
    sno: int
    heading: str
    image_url: str | None
    message: str
    is_sent: bool
    scheduled_at: datetime
    suppliers_label: str
    is_active: bool


class NotificationTemplateDetail(BaseModel):
    id: uuid.UUID
    heading: str
    message: str
    image_url: str | None
    scheduled_at: datetime
    is_sent: bool
    is_active: bool
    supplier_ids: list[uuid.UUID]


class NotificationTemplateCreateRequest(BaseModel):
    heading: str = Field(min_length=1, max_length=250)
    message: str = Field(min_length=1, max_length=2000)
    image_url: str | None = None
    scheduled_at: datetime
    supplier_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_is_in_the_future(cls, value: datetime) -> datetime:
        deadline = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if deadline < datetime.now(timezone.utc) + timedelta(minutes=MIN_SCHEDULE_LEAD_MINUTES):
            raise ValueError(f"Scheduled time must be at least {MIN_SCHEDULE_LEAD_MINUTES} minutes from now.")
        return value


class NotificationTemplateUpdateRequest(BaseModel):
    heading: str = Field(min_length=1, max_length=250)
    message: str = Field(min_length=1, max_length=2000)
    image_url: str | None = None
    scheduled_at: datetime
    supplier_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_is_in_the_future(cls, value: datetime) -> datetime:
        deadline = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if deadline < datetime.now(timezone.utc) + timedelta(minutes=MIN_SCHEDULE_LEAD_MINUTES):
            raise ValueError(f"Scheduled time must be at least {MIN_SCHEDULE_LEAD_MINUTES} minutes from now.")
        return value


class StatusUpdateRequest(BaseModel):
    is_active: bool
