"""Seeds states + the module/permission catalog. Idempotent — safe to re-run.

Usage: python -m scripts.seed_reference_data
"""

import asyncio

from sqlalchemy import select

import app.db.models  # noqa: F401 — registers every table so cross-model FKs resolve
from app.db.session import AsyncSessionFactory
from app.modules.geo.models import State
from app.modules.module_catalog.models import Module

# code -> (name, sort_order). 28 states + 8 union territories of India.
STATES: list[tuple[str, str]] = [
    ("AP", "Andhra Pradesh"), ("AR", "Arunachal Pradesh"), ("AS", "Assam"),
    ("BR", "Bihar"), ("CG", "Chhattisgarh"), ("GA", "Goa"), ("GJ", "Gujarat"),
    ("HR", "Haryana"), ("HP", "Himachal Pradesh"), ("JH", "Jharkhand"),
    ("KA", "Karnataka"), ("KL", "Kerala"), ("MP", "Madhya Pradesh"),
    ("MH", "Maharashtra"), ("MN", "Manipur"), ("ML", "Meghalaya"),
    ("MZ", "Mizoram"), ("NL", "Nagaland"), ("OD", "Odisha"), ("PB", "Punjab"),
    ("RJ", "Rajasthan"), ("SK", "Sikkim"), ("TN", "Tamil Nadu"),
    ("TG", "Telangana"), ("TR", "Tripura"), ("UP", "Uttar Pradesh"),
    ("UK", "Uttarakhand"), ("WB", "West Bengal"),
    ("AN", "Andaman and Nicobar Islands"), ("CH", "Chandigarh"),
    ("DN", "Dadra and Nagar Haveli and Daman and Diu"), ("DL", "Delhi"),
    ("JK", "Jammu and Kashmir"), ("LA", "Ladakh"), ("LD", "Lakshadweep"),
    ("PY", "Puducherry"),
]

# (key, name, parent_key, is_buildable) — order matters, parents before children.
# Confirmed against the real live site's admin-menu HTML — see
# docs/06-legacy-site-audit.md §1. This corrected a wrong, screenshot-guessed
# tree that had Master missing 3 of its 6 children, Activity wrongly
# carrying Filter/Product as children, and Template nested under App
# Feedback instead of Notification (App Feedback is actually a plain leaf).
MODULE_TREE: list[tuple[str, str, str | None, bool]] = [
    ("dashboard", "Dashboard", None, True),
    ("master", "Master", None, False),
    ("master.parent_category", "Parent Category", "master", False),
    ("master.child_category", "Child Category", "master", False),
    ("master.filter", "Filter", "master", False),
    ("master.filter_value", "Filter Value", "master", False),
    ("master.product", "Product", "master", False),
    ("master.room_category", "Room Category", "master", False),
    ("activity", "Activity", None, False),
    ("activity.orders", "Orders", "activity", False),
    ("upload_product", "Upload Product", None, False),
    ("upload_product.upload_files", "Upload Files", "upload_product", False),
    ("upload_product.log", "Log", "upload_product", False),
    ("user_management", "User Management", None, True),
    ("user_management.customer", "Customer", "user_management", True),
    ("user_management.sub_admin", "Sub Admin", "user_management", True),
    ("user_management.suppliers", "Suppliers", "user_management", True),
    ("logs", "Logs", None, False),
    ("logs.customer_login_history", "Customer Login History", "logs", False),
    ("notification", "Notification", None, False),
    ("notification.template", "Template", "notification", False),
    ("app_feedback", "App Feedback", None, False),
    ("setting", "Setting", None, False),
    ("setting.change_password", "Change Password", "setting", True),
    ("setting.log_off", "Log Off", "setting", False),
]



async def seed_states(session) -> None:
    existing = await session.scalar(select(State.code).limit(1))
    if existing:
        print("States already seeded — skipping.")
        return
    for sort_order, (code, name) in enumerate(STATES):
        session.add(State(code=code, name=name, sort_order=sort_order))
    print(f"Seeded {len(STATES)} states.")


async def seed_module_catalog(session) -> None:
    existing = await session.scalar(select(Module.key).limit(1))
    if existing:
        print("Module catalog already seeded — skipping.")
        return

    key_to_id: dict[str, object] = {}
    for sort_order, (key, name, parent_key, is_buildable) in enumerate(MODULE_TREE):
        module = Module(
            key=key,
            name=name,
            parent_id=key_to_id.get(parent_key) if parent_key else None,
            sort_order=sort_order,
            is_buildable=is_buildable,
        )
        session.add(module)
        await session.flush()  # need module.id before it can be a parent
        key_to_id[key] = module.id
    print(f"Seeded {len(MODULE_TREE)} module catalog entries.")


async def main() -> None:
    async with AsyncSessionFactory() as session:
        await seed_states(session)
        await seed_module_catalog(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
