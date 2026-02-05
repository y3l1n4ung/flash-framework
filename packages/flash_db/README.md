# Flash DB

Flash DB is a lightweight, asynchronous ORM (Object-Relational Mapper) for Python, built on top of the powerful SQLAlchemy Core and designed to feel familiar for developers coming from Django. It provides a simple, yet powerful, API for interacting with your database in modern asynchronous Python applications.

## Features

- **Asynchronous from the ground up:** Built for `asyncio`.
- **Django-like API:** `Model.objects` manager, lazy `QuerySet`s, and familiar method names.
- **SQLAlchemy's power:** Leverage the full power of SQLAlchemy's expression language when needed.
- **Type-safe:** Fully type-annotated for a better development experience with tools like MyPy.
- **Simple setup:** Easy to integrate with FastAPI and other async frameworks.

## Installation

```bash
pip install flash_db
```

## Quickstart

### 1. Initialize the Database

First, initialize the database connection. For a FastAPI application, you should use the `lifespan` context manager.

```python
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

```python
# models.py
from sqlalchemy.orm import Mapped, mapped_column
from flash_db import Model, TimestampMixin

class User(Model, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
```

### 3. Create Records

Use the `objects.create()` method on the model manager.

```python
# usage.py
from flash_db import get_db
from .models import User

async def create_user():
    async for db in get_db():
        user = await User.objects.create(db, name="John Doe", email="john.doe@example.com")
        print(f"Created user: {user.name}")
```

### 4. Query Data

Use the `objects` manager to query the database.

**Get all records:**

```python
async def list_users():
    async for db in get_db():
        users = await User.objects.all().fetch(db)
        for user in users:
            print(user.name)
```

**Filter records:**

```python
async def find_user():
    async for db in get_db():
        user = await User.objects.filter(User.email == "john.doe@example.com").first(db)
        if user:
            print(f"Found user: {user.name}")
```

**Get a single record:**

```python
async def get_user():
    async for db in get_db():
        try:
            user = await User.objects.get(db, User.name == "John Doe")
            print(f"Got user: {user.name}")
        except ValueError:
            print("User not found or multiple users found.")

```

### 5. Update Records

Update records using the `update` method.

```python
async def update_user_email():
    async for db in get_db():
        await User.objects.filter(User.name == "John Doe").update(db, email="new.email@example.com")
```

### 6. Delete Records

Delete records using the `delete` method.

```python
async def delete_user():
    async for db in get_db():
        await User.objects.filter(User.name == "John Doe").delete(db)
```

## Async and Session Management

Flash DB is fully asynchronous, and it requires you to manage the database session explicitly. The `get_db` function provides an async generator that yields an `AsyncSession` object. You should use this session for all your database operations.

This explicit approach ensures that the session is correctly handled and closed, which is crucial in an async environment.

## TODO: Next Steps for `flash_db`

To evolve `flash_db` and align it more closely with the comprehensive capabilities found in Django's ORM, the following tasks are planned:

1.  **Implement Transaction Management:** Introduce a robust mechanism (e.g., a decorator or context manager) to facilitate database transactions, allowing multiple operations to be grouped into a single atomic unit. This will ensure data integrity across complex operations.

    ```python
    # Conceptual example of desired implementation
    @transaction
    async def create_user_and_profile(db: AsyncSession):
        user = await User.objects.create(db, name="Jane Doe", email="jane.doe@example.com")
        await Profile.objects.create(db, user=user, bio="A bio.")
    ```

2.  **Add `get_or_create()` Method:** Develop a `get_or_create()` method for the `ModelManager` to simplify fetching an object if it exists, or creating it if it doesn't.

    ```python
    # Conceptual example
    user, created = await User.objects.get_or_create(db, email="jane.doe@example.com", defaults={"name": "Jane Doe"})
    ```

3.  **Add `update_or_create()` Method:** Implement an `update_or_create()` method to either update an existing object or create a new one based on given criteria, similar to Django's ORM.

4.  **Enhance `QuerySet` with More Methods:** Expand the `QuerySet` API to include additional Django-like functionalities:
    *   `exclude()`: To filter out records that match specific conditions.
    *   `distinct()`: To retrieve unique rows from the query results.
    *   **Aggregation Functions:** Integrate common aggregation functions (e.g., `Count`, `Sum`, `Avg`) to enable more complex data analysis directly through the `QuerySet`.

5.  **Explore Simplified Session Management:** Investigate ways to potentially abstract away explicit session passing in common scenarios (e.g., via a dependency injection decorator), aiming to reduce boilerplate while maintaining the asynchronous nature and control over database sessions.
