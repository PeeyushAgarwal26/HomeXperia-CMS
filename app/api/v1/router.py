from fastapi import APIRouter

from app.modules.auth.controller import router as auth_router
from app.modules.supplier_auth.controller import router as supplier_auth_router
from app.modules.customer_auth.controller import router as customer_auth_router
from app.modules.customer_auth.qr_login_controller import router as customer_qr_login_router
from app.modules.admin_users.controller import router as admin_users_router
from app.modules.module_catalog.controller import router as module_catalog_router
from app.modules.geo.controller import router as geo_router
from app.modules.files.controller import router as files_router
from app.modules.categories.controller import router as categories_router
from app.modules.categories.customer_controller import router as customer_categories_router
from app.modules.customers.controller import router as customers_router
from app.modules.customers.supplier_controller import router as supplier_customers_router
from app.modules.customers.theme_controller import router as theme_configuration_router
from app.modules.suppliers.controller import router as suppliers_router
from app.modules.logs.controller import router as logs_router
from app.modules.filters.controller import router as filters_router
from app.modules.filters.supplier_controller import router as supplier_filter_values_router
from app.modules.products.controller import router as products_router
from app.modules.products.customer_controller import router as customer_products_router
from app.modules.products.supplier_controller import router as supplier_products_router
from app.modules.product_uploads.controller import router as product_uploads_router
from app.modules.product_uploads.supplier_controller import router as supplier_product_uploads_router
from app.modules.room_categories.controller import router as room_categories_router
from app.modules.room_categories.customer_controller import router as customer_room_categories_router
from app.modules.room_category_images.controller import router as room_category_images_router
from app.modules.notifications.controller import router as notifications_router
from app.modules.visualizer.controller import router as visualizer_router
from app.modules.visualizer.admin_controller import router as visualizer_admin_router
from app.modules.orders.controller import router as orders_router
from app.modules.orders.customer_controller import cart_router, order_router as customer_order_router
from app.modules.qr_generator.controller import router as qr_generator_router
from app.modules.qr_generator.customer_controller import router as qr_generator_customer_router
from app.modules.room_category_images.customer_controller import router as room_category_images_customer_router
from app.modules.ai_credits.controller import router as ai_credits_router
from app.modules.ai_credits.supplier_controller import router as supplier_ai_credits_router

# Each module's controller.py defines its own `router = APIRouter(prefix=..., tags=[...])`.
# Register it here as the module is built.

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(supplier_auth_router)
api_v1_router.include_router(customer_auth_router)
api_v1_router.include_router(customer_qr_login_router)
api_v1_router.include_router(admin_users_router)
api_v1_router.include_router(module_catalog_router)
api_v1_router.include_router(geo_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(customer_categories_router)
api_v1_router.include_router(customers_router)
api_v1_router.include_router(supplier_customers_router)
api_v1_router.include_router(theme_configuration_router)
api_v1_router.include_router(suppliers_router)
api_v1_router.include_router(logs_router)
api_v1_router.include_router(filters_router)
api_v1_router.include_router(supplier_filter_values_router)
api_v1_router.include_router(products_router)
api_v1_router.include_router(customer_products_router)
api_v1_router.include_router(supplier_products_router)
api_v1_router.include_router(product_uploads_router)
api_v1_router.include_router(supplier_product_uploads_router)
api_v1_router.include_router(room_categories_router)
api_v1_router.include_router(customer_room_categories_router)
api_v1_router.include_router(room_category_images_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(visualizer_router)
api_v1_router.include_router(visualizer_admin_router)
api_v1_router.include_router(orders_router)
api_v1_router.include_router(cart_router)
api_v1_router.include_router(customer_order_router)
api_v1_router.include_router(qr_generator_router)
api_v1_router.include_router(qr_generator_customer_router)
api_v1_router.include_router(room_category_images_customer_router)
api_v1_router.include_router(ai_credits_router)
api_v1_router.include_router(supplier_ai_credits_router)
