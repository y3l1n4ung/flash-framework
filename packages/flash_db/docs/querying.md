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

