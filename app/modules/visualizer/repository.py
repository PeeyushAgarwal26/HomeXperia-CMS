import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.visualizer.models import TooltipUsage, UsageLog

logger = logging.getLogger(__name__)


class UsageLogRepository:
    """Ported from utils/usage_tracking.py. Flask's write helpers swallow and
    log DB errors rather than raising, so a usage-tracking failure never
    aborts the render/generation the customer actually asked for — same
    contract here, via a session rollback + log rather than a bare except,
    so a failed insert doesn't poison the rest of the request's session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_generation_attempt(
        self,
        customer_id: uuid.UUID,
        curtain_style: str | None = None,
        openai_status: str = "failed",
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        error: str | None = None,
    ) -> uuid.UUID | None:
        generation_units = 1 if openai_status == "success" else 0
        try:
            log = UsageLog(
                customer_id=customer_id,
                source="curtain_generation",
                curtain_style=curtain_style,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                openai_status=openai_status,
                generation_units=generation_units,
                error=error,
            )
            self.session.add(log)
            await self.session.flush()
            return log.id
        except Exception:
            logger.exception("log_generation_attempt failed")
            await self.session.rollback()
            return None

    async def set_segmentation_result(
        self,
        log_id: uuid.UUID | None,
        segmentation_status: str,
        room_id: str | None = None,
        error: str | None = None,
    ) -> None:
        if log_id is None:
            return
        try:
            log = await self.session.get(UsageLog, log_id)
            if log is None:
                return
            log.segmentation_status = segmentation_status
            if room_id is not None:
                log.room_id = room_id
            if error is not None:
                log.error = error
            await self.session.flush()
        except Exception:
            logger.exception("set_segmentation_result failed")
            await self.session.rollback()

    async def record_tooltip_usage(
        self, customer_id: uuid.UUID, room_id: str, hotspots: list[tuple[str, str | None]]
    ) -> set[str]:
        """hotspots: [(hotspot_id, category), ...] for every layer with a truthy
        hotspot_id. A given (room, hotspot, customer) triple only ever
        increments tooltip_units once, no matter how many times the same
        hotspot gets re-applied by the same customer. Returns the hotspot_ids
        that were genuinely first-time (used by AiCreditService to decide
        which renders are credit-charging vs free re-renders)."""
        hotspots = [(hid, category) for hid, category in hotspots if hid]
        if not room_id or not hotspots:
            return set()
        newly_counted_ids: set[str] = set()
        try:
            upsert_stmt = (
                pg_insert(UsageLog)
                .values(room_id=room_id, customer_id=customer_id, source="process_room")
                .on_conflict_do_nothing(index_elements=["room_id", "customer_id"])
            )
            await self.session.execute(upsert_stmt)

            for hotspot_id, category in hotspots:
                insert_stmt = (
                    pg_insert(TooltipUsage)
                    .values(
                        room_id=room_id,
                        hotspot_id=hotspot_id,
                        customer_id=customer_id,
                        category=category,
                    )
                    .on_conflict_do_nothing(index_elements=["room_id", "hotspot_id", "customer_id"])
                    .returning(TooltipUsage.id)
                )
                result = await self.session.execute(insert_stmt)
                if result.first() is not None:
                    newly_counted_ids.add(hotspot_id)

            if newly_counted_ids:
                stmt = select(UsageLog).where(
                    UsageLog.room_id == room_id, UsageLog.customer_id == customer_id
                )
                log = (await self.session.execute(stmt)).scalar_one_or_none()
                if log is not None:
                    log.tooltip_units += len(newly_counted_ids)
                    log.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return newly_counted_ids
        except Exception:
            logger.exception("record_tooltip_usage failed")
            await self.session.rollback()
            return set()

    async def get_usage_totals(self, customer_id: uuid.UUID) -> dict:
        stmt = select(
            func.coalesce(func.sum(UsageLog.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(UsageLog.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_gen_tokens"),
            func.count(UsageLog.id).filter(UsageLog.openai_status == "success").label("generations_success"),
            func.count(UsageLog.id).filter(UsageLog.openai_status == "failed").label("generations_failed"),
            func.coalesce(func.sum(UsageLog.generation_units), 0).label("generation_units"),
            func.coalesce(func.sum(UsageLog.tooltip_units), 0).label("tooltip_units"),
            func.min(UsageLog.created_at).label("first_activity_at"),
            func.max(UsageLog.updated_at).label("last_activity_at"),
        ).where(UsageLog.customer_id == customer_id)
        row = (await self.session.execute(stmt)).one()
        return dict(row._mapping)
