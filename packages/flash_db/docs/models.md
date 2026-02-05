# Defining Models

Define database models by inheriting from the `flash_db.Model` base class.

## Basic Model

Create a model by defining a class that inherits from `Model`.

```python title="models.py"
from sqlalchemy.orm import Mapped, mapped_column
from flash_db import Model

class User(Model):
    __tablename__ = "users"

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
```

## Common Field Mixins

Flash DB provides mixins for common fields like timestamps and soft deletes.

### `TimestampMixin`

This mixin adds `created_at` and `updated_at` fields to your model.

```python title="models.py"
from flash_db import Model, TimestampMixin

class Post(Model, TimestampMixin):
    __tablename__ = "posts"

    title: Mapped[str]
    content: Mapped[str]
```

### `SoftDeleteMixin`

This mixin adds a `deleted_at` field, useful for implementing soft deletes.

```python title="models.py"
from flash_db import Model, SoftDeleteMixin

class Comment(Model, SoftDeleteMixin):
    __tablename__ = "comments"

    text: Mapped[str]
```
