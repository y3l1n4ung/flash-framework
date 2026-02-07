# Querying with Flash DB

This guide details how to perform database operations using the `flash_db` API.

## 1. Create

Use `objects.create()` to persist a new record.

```python
# Create and refresh a new model instance
user = await User.objects.create(db, name="John Doe", email="john@example.com")
```

## 2. Read

Retrieve records using `all()`, `filter()`, or `get()`.

```python
# Fetch all records
users = await User.objects.all().fetch(db)

# Filter by criteria
active_users = await User.objects.filter(User.is_active == True).fetch(db)

# Retrieve a single record (raises DoesNotExist or MultipleObjectsReturned)
user = await User.objects.get(db, User.email == "john@example.com")
```

## 3. Update

Modify a record by its primary key using `update()`.

```python
# Update by primary key
user = await User.objects.update(db, pk=1, name="John Updated")
```

## 4. Delete

Remove a record by its primary key using `delete_by_pk()`.

```python
# Delete by primary key
count = await User.objects.delete_by_pk(db, pk=1)
```

## 5. Query Construction

### Filter and Exclude

- `filter(*conditions)`: Include records matching the conditions.
- `exclude(*conditions)`: Include records *not* matching the conditions.

```python
# Select users NOT named "John"
users = await User.objects.exclude(User.name == "John").fetch(db)
```

### Ordering and Limits

- `order_by(*criterion)`: Sort results.
- `limit(count)`: Restrict the number of results.
- `offset(count)`: Skip the specified number of results.
- `latest(field)`: Retrieve the most recent record.
- `earliest(field)`: Retrieve the oldest record.

```python
# Retrieve the most recently created user
latest_user = await User.objects.latest(db)
```

### Column Selection

- `only(*fields)`: Load only specific columns.
- `defer(*fields)`: Defer loading of specific columns.

```python
# Load only name and email
users = await User.objects.only("name", "email").fetch(db)
```

### Raw Values

- `values(*fields)`: Return a list of dictionaries.
- `values_list(*fields, flat=False)`: Return a list of tuples (or a flat list if `flat=True`).

```python
# Retrieve a list of user names
names = await User.objects.values_list(db, "name", flat=True)

# Retrieve dictionaries with specific fields
users_data = await User.objects.values(db, "id", "name")
```

### Creation Shortcuts

- `get_or_create(defaults, **kwargs)`: Retrieve an object or create it if missing.
- `update_or_create(defaults, **kwargs)`: Update an object or create it if missing.

```python
user, created = await User.objects.get_or_create(
    db,
    email="john@example.com",
    defaults={"name": "John Doe"}
)
```

### Existence and Aggregation

- `exists(*conditions)`: Check for matching records.
- `count(*conditions)`: Count matching records.

```python
# Check existence
if await User.objects.exists(db, User.email == "john@example.com"):
    print("User exists!")

# Count active users
active_count = await User.objects.count(db, User.is_active == True)
```

## 6. Relationships

To prevent N+1 queries, use the following methods:

- `select_related(*fields)`: Uses SQL `JOIN`. Ideal for many-to-one or one-to-one relationships.
- `prefetch_related(*fields)`: Uses separate `SELECT IN` queries. Ideal for many-to-many or reverse foreign keys (one-to-many).

!!! tip
    While `select_related` can be used for one-to-many relationships, it may result in row duplication and decreased performance. For collections or reverse relations, `prefetch_related` is generally recommended.

```python
# Eager load with JOIN
articles = await Article.objects.select_related("author").fetch(db)

# Eager load with separate query
articles = await Article.objects.prefetch_related("tags").fetch(db)
```

## 7. Complex Expressions (Beta)

!!! warning "Beta Feature"
    `Q` objects and `F` expressions are in **Beta**. The API and behavior are subject to change.

### Q Objects

Encapsulate and combine query conditions using bitwise operators (`&`, `|`, `~`).

!!! note
    While manual resolution via `.resolve(Model)` is currently required, automatic resolution within `filter()` and `exclude()` is planned for a future release.

```python
from flash_db.expressions import Q

# Combine conditions (manual resolution currently required)
condition = (Q(name="John") | Q(name="Jane")) & ~Q(status="retired")
resolved = condition.resolve(User)

users = await User.objects.filter(resolved).fetch(db)
```

### F Expressions

Reference model fields within queries.

!!! note "Current Limitation"
    `F` expressions currently require manual resolution before being passed to update methods. Automatic resolution within `update()` is planned.

```python
from flash_db.expressions import F

# Increment stock by 1 (Manual Resolution)
expr = (F("stock") + 1).resolve(Product)
await Product.objects.filter(id=1).update(db, stock=expr)
```