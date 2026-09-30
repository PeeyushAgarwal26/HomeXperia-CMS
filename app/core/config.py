from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_env: str = "development"
    app_name: str = "homexperia-admin-api"
    app_version: str = "0.1.0"
    # Defaults to False (not True) on purpose: FastAPI's debug=True makes
    # Starlette's outermost ServerErrorMiddleware return the raw traceback
    # (full local filesystem paths included) straight in the HTTP response
    # body for ANY unhandled exception, bypassing the app's own registered
    # exception handlers entirely - a deployment that forgets to set
    # APP_DEBUG explicitly should fail safe, not leak internals. Local dev's
    # own .env already sets APP_DEBUG=true explicitly for real tracebacks.
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/homexperia_db"

    secret_key: str = "insecure-default-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Customer-facing client-frontend only (admin/supplier access tokens keep
    # using access_token_expire_minutes) — longer-lived since a shopper
    # session on the visualizer tends to run longer than a 30-minute admin
    # editing session before the refresh flow would otherwise kick in.
    customer_access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    # Hard ceiling on a session's total age, independent of activity — without
    # this, a rotating refresh token (see auth/service.py) renews forever as
    # long as the user keeps browsing, so a session could otherwise never end.
    absolute_session_expire_days: int = 7
    password_reset_token_expire_minutes: int = 30

    # Comma-separated, not list[str] — pydantic-settings would try to JSON-parse
    # a list-typed env var, and a bare "*" isn't valid JSON.
    cors_origins_raw: str = "http://localhost:5173"

    # Base URL of the React admin app — used to build the password-reset email link.
    frontend_url: str = "http://localhost:5173"
    # Base URL of the *customer-facing* storefront (a different app/domain from
    # frontend_url above) — used to build the /verify?customer-code=...&filter-value=...
    # URL encoded into generated QR codes. That /verify route + its query param
    # names (hyphenated, not underscored) already exist and are load-bearing in
    # homexperia-client-frontend's VerifyToken.jsx; this must match exactly.
    customer_frontend_url: str = "https://homexperia.com"
    # Shared secret the client-frontend's QR/deep-link auto-login flow sends
    # as the literal header "x_key" (underscore, not the usual hyphen) —
    # matches VITE_X_KEY, already baked into that app's .env. Not meant to be
    # secure against a determined attacker (same tier as visualizer_service_key
    # below); it's the real, existing contract, not something invented here.
    customer_code_login_key: str = "9f8c1c6a-1a5c-4f8d-b7a0-6c2e4c5f9b12"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "HomeXperia Admin"

    # Where uploaded files actually live on disk — dev default is a relative
    # path (resolved from wherever the process starts), but in production this
    # should be set to an absolute path outside the deployment directory
    # (e.g. a mounted volume) so files survive a redeploy. Deliberately
    # decoupled from uploads_url_prefix below: the URL clients see must stay
    # "/uploads/..." regardless of where the directory physically is,
    # otherwise an absolute UPLOADS_DIR would leak into the URL itself.
    uploads_dir: str = "uploads"
    # The URL path segment files are served under — always "uploads", never
    # derived from uploads_dir. See LocalDiskStorage and app.main's static mount.
    uploads_url_prefix: str = "uploads"
    log_dir: str = "logs"

    # Room visualizer (ported from the client's Flask backend) — external service
    # credentials, none of which existed in this codebase before that port.
    sam_api_url: str = ""
    sam_api_key: str = ""
    openai_api_key: str = ""
    # Local checkpoint for scene_segmentation.py's occluder-refinement model
    # (SAM-HQ ViT-B) — not bundled with the segment-anything-hq package, must
    # be downloaded once (see imaging/scene_segmentation.py's module docstring
    # for the source URL) since it's too large to commit.
    sam_hq_checkpoint_path: str = "data/models/sam_hq_vit_b.pth"
    # Flask hardcoded this True unconditionally, writing to a Debugs/ folder that
    # isn't guaranteed to exist. Default off here — an explicit, safer default.
    visualizer_debug_images: bool = False
    # Shared secret for callers with no Homexperia login at all (Shopify-embed
    # pages) — replaces Flask's hardcoded "this_is_api_key" literal with a real
    # configurable value. See get_current_customer_optional.
    visualizer_service_key: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
