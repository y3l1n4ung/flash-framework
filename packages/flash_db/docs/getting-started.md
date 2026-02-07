# Getting Started

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

## Session Management

Inject the database session into route handlers using the `get_db` dependency.

```python
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