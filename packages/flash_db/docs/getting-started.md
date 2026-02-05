# Getting Started

This guide covers the basic setup for `flash_db` in a FastAPI application.

## Installation

Install the package from PyPI:

```bash
pip install flash_db
```

## Database Initialization

Use FastAPI's `lifespan` context manager to handle database startup and shutdown.

```python title="main.py"
from contextlib import asynccontextmanager
from fastapi import FastAPI
from flash_db import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database on startup
    init_db("sqlite+aiosqlite:///db.sqlite3")
    yield
    # Close the database on shutdown
    await close_db()

app = FastAPI(lifespan=lifespan)
```

## Database Session

Inject the database session into your FastAPI endpoints using `Depends(get_db)`.

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from flash_db import get_db

@app.get("/items/")
async def read_items(db: AsyncSession = Depends(get_db)):
    # The 'db' session is now available for database calls
    # e.g., items = await Item.objects.all().fetch(db)
    pass
```

The `get_db` dependency provides an `AsyncSession` that is automatically managed for each request.
