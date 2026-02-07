# Getting Started

Flash DB is a lightweight async Django ORM alternative built on top of SQLAlchemy. While it is part of the **Flash Web Framework**, it can be used **standalone** with frameworks like **FastAPI**.

## Installation

Install `flash_db` using pip:

```bash
pip install flash_db
```

## Configuration

Initialize the database connection within your application's lifespan.

```python title="main.py"
from contextlib import asynccontextmanager
from fastapi import FastAPI
from flash_db import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database (e.g., using SQLite)
    init_db("sqlite+aiosqlite:///db.sqlite3")
    yield
    # Close connections on shutdown
    await close_db()

app = FastAPI(lifespan=lifespan)
```

## Transactions & Persistence

By default, **Flash DB does not auto-commit** changes. After calling methods like `create()`, `update()`, or `delete()`, you must explicitly commit your changes or use the `atomic` block.

```python title="transactions.py"
from flash_db import atomic

# Option 1: Explicit Commit
await User.objects.create(db, name="Manual")
await db.commit()

# Option 2: Atomic Block 
# Automatically commits on success, rolls back on error.
async with atomic(db):
    await User.objects.create(db, name="Auto")
    await User.objects.create(db, name="Magic")
```

## Session Management

Inject the database session into route handlers using the `get_db` dependency.

```python title="routes.py"
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from flash_db import get_db

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Example endpoint using the database session dependency.
    """
    # The 'db' session is an SQLAlchemy AsyncSession ready for use.
    return {"status": "ok"}
```