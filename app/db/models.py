# Every module's models.py must be imported here so Base.metadata is fully
# populated before `alembic revision --autogenerate` runs.
import app.modules.geo.models  # noqa: F401
import app.modules.module_catalog.models  # noqa: F401
import app.modules.admin_users.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.activity_logs.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
import app.modules.suppliers.models  # noqa: F401
import app.modules.customers.models  # noqa: F401
import app.modules.logs.models  # noqa: F401
