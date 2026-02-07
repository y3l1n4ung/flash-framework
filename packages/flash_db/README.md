# Flash DB

Flash DB is a lightweight async Django ORM alternative built on top of SQLAlchemy. While it is part of the **Flash Web Framework**, it can be used **standalone** with frameworks like **FastAPI**.

## Features

- **Asynchronous from the ground up:** Built for `asyncio`.
- **Django-like API:** `Model.objects` manager, lazy `QuerySet`s, and familiar method names.
- **SQLAlchemy's power:** Leverage the full power of SQLAlchemy's expression language when needed.
- **Transaction Management:** Manages database transactions as a context manager or decorator, with nested savepoint support.
- **Type-safe:** Fully type-annotated for a better development experience with tools like MyPy.
- **Simple setup:** Easy to integrate with FastAPI and other async frameworks.

## Installation

```bash
pip install flash_db
```

## Quickstart

### 1. Initialize the Database

First, initialize the database connection. For a FastAPI application, you should use the `lifespan` context manager.

```python title="main.py"
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from flash_db import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database
    init_db("sqlite+aiosqlite:///db.sqlite3")
    yield
    # Close the database
    await close_db()

app = FastAPI(lifespan=lifespan)
```

### 2. Define Your Models

Create your models by inheriting from `flash_db.Model`.

```python title="models.py"
# models.py
from sqlalchemy.orm import Mapped, mapped_column
from flash_db import Model, TimestampMixin

class User(Model, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
```

### 3. Create Records

Use the `objects.create()` method on the model manager. Operations require an explicit commit.

```python title="usage.py"
# usage.py
from flash_db import get_db, atomic
from .models import User

async def create_user():
    async for db in get_db():
        # Option 1: Explicit commit
        user = await User.objects.create(db, name="John Doe", email="john.doe@example.com")
        await db.commit()
        print(f"Created user: {user.name}")

        # Option 2: Atomic block (commits automatically on exit)
        async with atomic(db):
            await User.objects.create(db, name="Jane Doe", email="jane@example.com")
```

### 4. Query Data

Use the `objects` manager to query the database.

**Get all records:**

```python title="query.py"
async def list_users():
    async for db in get_db():
        users = await User.objects.all().fetch(db)
        for user in users:
            print(user.name)
```

**Filter records:**

```python title="filter.py"
async def find_user():
    async for db in get_db():
        user = await User.objects.filter(User.email == "john.doe@example.com").first(db)
        if user:
            print(f"Found user: {user.name}")
```

**Get a single record:**

```python title="get.py"
async def get_user():
    async for db in get_db():
        try:
            user = await User.objects.get(db, User.name == "John Doe")
            print(f"Got user: {user.name}")
        except User.DoesNotExist:
            print("User not found.")
        except User.MultipleObjectsReturned:
            print("Multiple users found.")

```

### 5. Update Records

Update records using the `update` method.

```python title="update.py"
async def update_user_email():
    async for db in get_db():
        await User.objects.filter(User.name == "John Doe").update(db, email="new.email@example.com")
        await db.commit()
```

### 6. Delete Records

Delete records using the `delete` method.

```python title="delete.py"
async def delete_user():
    async for db in get_db():
        await User.objects.filter(User.name == "John Doe").delete(db)
        await db.commit()
```

## Async and Session Management

Flash DB is fully asynchronous, and it requires you to manage the database session explicitly. The `get_db` function provides an async generator that yields an `AsyncSession` object. You should use this session for all your database operations.

This explicit approach ensures that the session is correctly handled and closed, which is crucial in an async environment.

## Roadmap

Our goal for `flash_db` is to build a lightweight, yet powerful, async ORM that feels intuitive to Django developers.

- [x] **Transaction Management:** Atomic transactions via decorator or context manager.
- [x] **`get_or_create()` / `update_or_create()`:** Streamline create/update patterns.
- [ ] **Model Validation Hooks:** `clean()` methods for data validation.
- [x] **Advanced Querying:** `exclude()`, `distinct()`, `only()`, `defer()`, and more.
- [x] **Complex Lookups:** `Q` Objects and `F` Expressions (Beta), Prefetching.
- [x] **Performance:** `bulk_create`, `bulk_update` (Beta).
- [ ] **Signals:** `pre_save`, `post_save`, `pre_delete`, `post_delete`.
