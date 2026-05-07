#!/usr/bin/env python3
"""Create the single admin user. Run once after first migration.

Usage:
    python scripts/create_admin.py admin@example.com secretpassword
"""

import asyncio
import sys

from fastapi_users.password import PasswordHelper

from app.auth.users import get_user_db
from app.db import _session_factory


async def create_admin(email: str, password: str) -> None:
    helper = PasswordHelper()
    hashed = helper.hash(password)

    async with _session_factory() as session:
        gen = get_user_db(session)
        user_db = await gen.__anext__()

        existing = await user_db.get_by_email(email)
        if existing is not None:
            print(f"User {email} already exists.")
            return

        await user_db.create(
            {
                "email": email,
                "hashed_password": hashed,
                "is_active": True,
                "is_superuser": True,
                "is_verified": True,
            }
        )
        print(f"Admin user {email} created.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_admin.py <email> <password>")
        sys.exit(1)
    asyncio.run(create_admin(sys.argv[1], sys.argv[2]))
