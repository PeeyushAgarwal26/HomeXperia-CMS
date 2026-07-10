from fastapi import APIRouter

# Each module's controller.py defines its own `router = APIRouter(prefix=..., tags=[...])`.
# Register it here as the module is built, e.g.:
# from app.modules.auth.controller import router as auth_router
# api_v1_router.include_router(auth_router)

api_v1_router = APIRouter(prefix="/api/v1")
