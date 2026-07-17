import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadLogRow(BaseModel):
    row_no: int
    catalog_name: str | None
    is_success: bool
    action: str | None  # "created" | "updated" when is_success, else None
    message: str | None


class UploadLogListItem(BaseModel):
    id: uuid.UUID
    sno: int
    file_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    uploaded_at: datetime
    total_rows: int
    success_count: int
    error_count: int
    status: str  # "success" | "partial" | "failed"


class UploadLogDetail(BaseModel):
    id: uuid.UUID
    file_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    uploaded_at: datetime
    total_rows: int
    success_count: int
    error_count: int
    status: str  # "success" | "partial" | "failed"
    error_message: str | None
    rows: list[UploadLogRow]


class UploadPreviewResult(BaseModel):
    """A dry run — nothing is written to the database. Lets the admin see exactly what would
    happen (created / updated / failed, and why) before committing to it."""

    total_rows: int
    created_count: int
    updated_count: int
    error_count: int
    rows: list[UploadLogRow]
