import uuid

from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Module(BaseModel):
    """The complete sidebar/permission catalog. Self-referencing tree via parent_id."""

    __tablename__ = "modules"
    __table_args__ = (Index("ix_modules_parent_id", "parent_id"),)

    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_buildable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
