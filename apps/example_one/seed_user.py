import asyncio
from pathlib import Path

from flash_authentication.models import User
from flash_db import db as db_module
from flash_db.models import Model
from sqlalchemy import select

DATABASE_URL = "sqlite+aiosqlite:///blog.db"
DEFAULT_USER = {
    "username": "admin",
    "email": "admin@example.com",
    "password": "password123",
    "is_active": True,
    "is_staff": True,
    "is_superuser": True,
}


async def seed_user() -> None:
    db_module.init_db(DATABASE_URL, echo=False)
    engine = db_module._engine
    if engine is None:
        msg = "Database engine not initialized."
        raise RuntimeError(msg)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    async for session in db_module.get_db():
        stmt = select(User).where(User.username == DEFAULT_USER["username"])
        existing = await session.scalar(stmt)
        if existing:
            print(
                f"User '{DEFAULT_USER['username']}' already exists (id={existing.id})."
            )
            return

        user = User(
            username=DEFAULT_USER["username"],
            email=DEFAULT_USER["email"],
            is_active=DEFAULT_USER["is_active"],
            is_staff=DEFAULT_USER["is_staff"],
            is_superuser=DEFAULT_USER["is_superuser"],
        )
        user.set_password(DEFAULT_USER["password"])  # ty:ignore[invalid-argument-type]
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(
            f"Created user '{user.username}' (id={user.id}) with email '{user.email}'."
        )

    await db_module.close_db()


if __name__ == "__main__":
    db_path = Path("blog.db").resolve()
    print(f"Seeding user into {db_path}")
    asyncio.run(seed_user())
