# Defining Models

Define database schemas by creating Python classes that inherit from `flash_db.Model`.

## Basic Usage

Models map directly to database tables. Use standard SQLAlchemy `Mapped` types for field definitions.

```python title="models.py"
from sqlalchemy.orm import Mapped, mapped_column
from flash_db import Model

class User(Model):
    __tablename__ = "users"

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
```

## Mixins

Mixins provide reusable field sets for common patterns.

### Timestamps

The `TimestampMixin` automatically manages `created_at` and `updated_at` fields.

```python title="models.py"
from flash_db import Model, TimestampMixin

class Post(Model, TimestampMixin):
    __tablename__ = "posts"
    
    title: Mapped[str]
    # created_at and updated_at are added automatically
```

### Soft Deletion

The `SoftDeleteMixin` adds a `deleted_at` field to support non-destructive deletion workflows.

```python title="models.py"
from flash_db import Model, SoftDeleteMixin

class Comment(Model, SoftDeleteMixin):
    __tablename__ = "comments"
    
    text: Mapped[str]
    # deleted_at is added automatically
```