from fastapi import APIRouter

from app.modules.auth.controller import router as auth_router
from app.modules.admin_users.controller import router as admin_users_router
from app.modules.module_catalog.controller import router as module_catalog_router
from app.modules.geo.controller import router as geo_router
from app.modules.files.controller import router as files_router
from app.modules.categories.controller import router as categories_router
from app.modules.customers.controller import router as customers_router
from app.modules.suppliers.controller import router as suppliers_router
from app.modules.logs.controller import router as logs_router

# Each module's controller.py defines its own `router = APIRouter(prefix=..., tags=[...])`.
# Register it here as the module is built.

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_users_router)
api_v1_router.include_router(module_catalog_router)
api_v1_router.include_router(geo_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(customers_router)
api_v1_router.include_router(suppliers_router)
api_v1_router.include_router(logs_router)
