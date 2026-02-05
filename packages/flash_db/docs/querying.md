# Querying with FastAPI

This guide shows how to perform CRUD (Create, Read, Update, Delete) operations with `flash_db` in a FastAPI application.

!!! tip
    All examples assume you have a `User` model and corresponding Pydantic schemas defined.

## Schemas for Validation

It's good practice to use Pydantic schemas for request and response validation.

```python title="schemas.py"
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    name: str
    email: EmailStr

class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr

    class Config:
        orm_mode = True
```

## CRUD Operations

Here are examples of how to implement CRUD endpoints in your FastAPI application.

### Create

Use `objects.create()` to add a new record.

```python title="main.py"
@app.post("/users/", response_model=UserRead, status_code=201)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await User.objects.create(db, **user.dict())
    return db_user
```

### Read

Fetch multiple records with `all()` and `filter()`. Fetch a single record with `get()`.

```python title="main.py"
@app.get("/users/", response_model=list[UserRead])
async def read_users(db: AsyncSession = Depends(get_db)):
    return await User.objects.all().fetch(db)

@app.get("/users/{user_id}", response_model=UserRead)
async def read_user(user_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await User.objects.get(db, User.id == user_id)
    except ValueError:
        raise HTTPException(404, "User not found")
```

### Update

Use `update()` to modify a record by its primary key.

```python title="main.py"
@app.put("/users/{user_id}", response_model=UserRead)
async def update_user(user_id: int, user: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await User.objects.update(db, pk=user_id, **user.dict())
    except ValueError:
        raise HTTPException(404, "User not found")
```

### Delete

Use `delete_by_pk()` to remove a record by its primary key.

```python title="main.py"
@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    deleted_count = await User.objects.delete_by_pk(db, pk=user_id)
    if not deleted_count:
        raise HTTPException(404, "User not found")
```

## Advanced Querying

### Filter and Exclude

- `filter(*conditions)`: Records matching conditions.
- `exclude(*conditions)`: Records *not* matching conditions.

```python
# All users except those named "John"
users = await User.objects.exclude(User.name == "John").fetch(db)
```

### Ordering and Limits

- `order_by(*criterion)`: Order results.
- `limit(count)`: Limit number of results.
- `offset(count)`: Skip a number of results.
- `latest(field)`: Get the most recent record.
- `earliest(field)`: Get the earliest record.

```python
# Get the most recently created user
latest_user = await User.objects.latest(db)
```

### Selective Column Loading

- `only(*fields)`: Load only specified columns.
- `defer(*fields)`: Exclude specified columns from initial load.

```python
# Load only name and email to save memory
users = await User.objects.only("name", "email").fetch(db)
```

### Retrieving Dictionaries or Tuples

- `values(*fields)`: Return a list of dictionaries.
- `values_list(*fields, flat=False)`: Return a list of tuples (or flat list if `flat=True`).

```python
# Get a list of user names
names = await User.objects.values_list(db, "name", flat=True)

# Get dictionaries with specific fields
users_data = await User.objects.values(db, "id", "name")
```

### Creation Shortcuts

- `get_or_create(defaults, **kwargs)`: Fetch an object or create it if it doesn't exist.
- `update_or_create(defaults, **kwargs)`: Update an object or create it if it doesn't exist.

```python
user, created = await User.objects.get_or_create(
    db,
    email="john@example.com",
    defaults={"name": "John Doe"}
)
```

### Existence and Counting

- `exists(*conditions)`: Check if any records match.
- `count(*conditions)`: Count matching records.

```python
# Check if a user with this email exists
if await User.objects.exists(db, User.email == "john@example.com"):
    print("User exists!")

# Count active users
active_count = await User.objects.count(db, User.is_active == True)
```

### Latest and Earliest

- `latest(field)`: Get the most recent record.
- `earliest(field)`: Get the earliest record.

```python
# Get the most recently joined user
latest_user = await User.objects.latest(db, field="created_at")
```

## Chaining Queries

QuerySet methods can be chained together. The query is only executed when you call an "execution method" like `fetch()`, `first()`, `latest()`, etc.

```python
# Get up to 10 active users, ordered by join date, only loading names
users = await (
    User.objects.filter(User.is_active == True)
    .exclude(User.is_staff == True)
    .order_by(User.created_at.desc())
    .only("name")
    .limit(10)
    .fetch(db)
)
```

