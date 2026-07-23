import uuid

from sqlalchemy import ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class State(Base):
    """Read-only reference data backing the State dropdown. Seeded once."""

    __tablename__ = "states"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class City(Base):
    """Read-only suggestion data for the City field, filtered by State — not a
    foreign key constraint on any entity's own `city` column. Those columns stay
    free text; a value that isn't in this list is still perfectly valid (e.g. a
    real supplier town like Bhadohi that a curated list can't fully cover)."""

    __tablename__ = "cities"
    __table_args__ = (Index("ix_cities_state_code", "state_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state_code: Mapped[str] = mapped_column(String(10), ForeignKey("states.code"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
