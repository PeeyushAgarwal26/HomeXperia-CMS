import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.session import AsyncSessionFactory
from app.modules.ai_credits.service import AiCreditService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_monthly_rollover_job() -> None:
    """The actual job body — a fresh session per run, same lifecycle as a
    request. Idempotent by construction (see AiCreditService.
    run_monthly_rollover / the ledger's UniqueConstraint), so it's always
    safe to fire this more than once for the same month, whether from this
    scheduler, a manual admin "run now", or a catch-up after downtime."""
    async with AsyncSessionFactory() as session:
        try:
            result = await AiCreditService(session).run_monthly_rollover()
            await session.commit()
            logger.info(
                "ai_credits monthly rollover: processed %s accounts for period %s",
                result.processed_accounts,
                result.period_start,
            )
        except Exception:
            await session.rollback()
            logger.exception("ai_credits monthly rollover job failed")


def start_ai_credit_scheduler() -> AsyncIOScheduler:
    """Runs on the 1st of every month. Also fires once at startup (via
    run_monthly_rollover's own catch-up loop inside AiCreditService, which
    walks forward from each supplier's last-closed month) so a missed run
    — server restart, deploy window spanning midnight on the 1st — self
    heals on the next boot rather than silently skipping a month."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        run_monthly_rollover_job,
        trigger=CronTrigger(day=1, hour=0, minute=5),
        id="ai_credits_monthly_rollover",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("ai_credits monthly rollover scheduler started")
    return _scheduler


def stop_ai_credit_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
