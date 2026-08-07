from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.common.logging import configure_logging
from app.core.config import settings
from app.db.session import engine
from app.exceptions.handlers import register_exception_handlers
from app.middleware.context import RequestContextMiddleware
from app.modules.ai_credits.cron import run_monthly_rollover_job, start_ai_credit_scheduler, stop_ai_credit_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    configure_logging()
    # Runs once immediately (self-heals any month missed while the app was
    # down — the job is idempotent), then the scheduler takes over for the
    # 1st-of-month trigger going forward.
    await run_monthly_rollover_job()
    start_ai_credit_scheduler()
    yield
    stop_ai_credit_scheduler()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Cross-origin JS can't read Content-Disposition unless it's explicitly
        # exposed — needed so the frontend can recover the server-generated
        # (timestamped) filename for file exports (see app/common/xlsx_export.py).
        expose_headers=["Content-Disposition"],
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router)
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    app.mount(f"/{settings.uploads_url_prefix}", StaticFiles(directory=settings.uploads_dir), name="uploads")

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
