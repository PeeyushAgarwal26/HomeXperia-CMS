"""Creates the one super admin account. There's no create-account page in the
reference UI — this is the only way a super admin ever comes into existence.

Usage:
  python -m scripts.create_superadmin \\
      --username admin --password Admin@123 --name "Super Admin" \\
      --email admin@homexperia.com --phone-number 9999999999 \\
      --pin-code 302001 --state-code RJ --city Jaipur
"""

import argparse
import asyncio

from sqlalchemy import select

import app.db.models  # noqa: F401 — registers every table so cross-model FKs resolve
from app.core.security import hash_password
from app.db.session import AsyncSessionFactory
from app.modules.admin_users.models import AdminUser


async def create_superadmin(args: argparse.Namespace) -> None:
    async with AsyncSessionFactory() as session:
        existing = await session.scalar(select(AdminUser.id).where(AdminUser.is_super_admin.is_(True)))
        if existing:
            print("A super admin already exists — skipping.")
            return

        session.add(
            AdminUser(
                is_super_admin=True,
                name=args.name,
                email=args.email,
                phone_number=args.phone_number,
                pin_code=args.pin_code,
                state_code=args.state_code,
                city=args.city,
                username=args.username,
                password_hash=hash_password(args.password),
                is_active=True,
            )
        )
        await session.commit()
        print(f"Super admin '{args.username}' created.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the super admin account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--phone-number", required=True)
    parser.add_argument("--pin-code", required=True)
    parser.add_argument("--state-code", required=True)
    parser.add_argument("--city", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(create_superadmin(parse_args()))
