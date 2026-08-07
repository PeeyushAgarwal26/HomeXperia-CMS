# Every module's models.py must be imported here so Base.metadata is fully
# populated before `alembic revision --autogenerate` runs.
import app.modules.geo.models  # noqa: F401
import app.modules.module_catalog.models  # noqa: F401
import app.modules.admin_users.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.activity_logs.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
import app.modules.suppliers.models  # noqa: F401
import app.modules.supplier_auth.models  # noqa: F401
import app.modules.customer_auth.models  # noqa: F401
import app.modules.customers.models  # noqa: F401
import app.modules.logs.models  # noqa: F401
import app.modules.filters.models  # noqa: F401
import app.modules.products.models  # noqa: F401
import app.modules.product_uploads.models  # noqa: F401
import app.modules.room_categories.models  # noqa: F401
import app.modules.room_category_images.models  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.visualizer.models  # noqa: F401
import app.modules.orders.models  # noqa: F401
import app.modules.qr_generator.models  # noqa: F401
import app.modules.ai_credits.models  # noqa: F401
