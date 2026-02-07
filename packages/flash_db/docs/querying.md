# Querying with Flash DB

This guide details how to perform database operations using the `flash_db` API.

## 1. Create

Use `objects.create()` to persist a new record.

```python title="create.py"
# Create and refresh a new model instance
user = await User.objects.create(db, name="John Doe", email="john@example.com")
```

## 2. Read

Retrieve records using `all()`, `filter()`, or `get()`.

```python title="read.py"
# Fetch all records
users = await User.objects.all().fetch(db)
# SELECT * FROM users;

# Filter by criteria
active_users = await User.objects.filter(User.is_active == True).fetch(db)
# SELECT * FROM users WHERE is_active = true;

# Retrieve a single record (raises DoesNotExist or MultipleObjectsReturned)
user = await User.objects.get(db, User.email == "john@example.com")
# SELECT * FROM users WHERE email = 'john@example.com' LIMIT 2;
```

## 3. Update

Modify a record by its primary key using `update()`.

```python title="update.py"
# Update by primary key
user = await User.objects.update(db, pk=1, name="John Updated")
# UPDATE users SET name = 'John Updated' WHERE id = 1 RETURNING *;
```

## 4. Delete

Remove a record by its primary key using `delete_by_pk()`.

```python title="delete.py"
# Delete by primary key
count = await User.objects.delete_by_pk(db, pk=1)
# DELETE FROM users WHERE id = 1;
```

## 5. Query Construction

### Filter and Exclude

- `filter(*conditions)`: Include records matching the conditions.
- `exclude(*conditions)`: Include records *not* matching the conditions.

```python title="filter_exclude.py"
# Select users NOT named "John"
users = await User.objects.exclude(User.name == "John").fetch(db)
# SELECT * FROM users WHERE name != 'John';
```

### Ordering and Limits

- `order_by(*criterion)`: Sort results.
- `limit(count)`: Restrict the number of results.
- `offset(count)`: Skip the specified number of results.
- `latest(field)`: Retrieve the most recent record.
- `earliest(field)`: Retrieve the oldest record.

```python title="ordering.py"
# Retrieve the most recently created user
latest_user = await User.objects.latest(db)
# SELECT * FROM users ORDER BY created_at DESC LIMIT 1;
```

### Column Selection

- `only(*fields)`: Load only specific columns.
- `defer(*fields)`: Defer loading of specific columns.

```python title="selection.py"
# Load only name and email
users = await User.objects.only("name", "email").fetch(db)
# SELECT name, email FROM users;
```

### Raw Values

- `values(*fields)`: Return a list of dictionaries.
- `values_list(*fields, flat=False)`: Return a list of tuples (or a flat list if `flat=True`).

```python title="values.py"
# Retrieve a list of user names
names = await User.objects.values_list(db, "name", flat=True)
# SELECT name FROM users;

# Retrieve dictionaries with specific fields
users_data = await User.objects.values(db, "id", "name")
# SELECT id, name FROM users;
```

### Creation Shortcuts

- `get_or_create(defaults, **kwargs)`: Retrieve an object or create it if missing.
- `update_or_create(defaults, **kwargs)`: Update an object or create it if missing.

```python title="shortcuts.py"
user, created = await User.objects.get_or_create(
    db,
    email="john@example.com",
    defaults={"name": "John Doe"}
)
```

### Existence and Aggregation

- `exists(*conditions)`: Check for matching records.
- `count(*conditions)`: Count matching records.

```python title="aggregation.py"
# Check existence
if await User.objects.exists(db, User.email == "john@example.com"):
    print("User exists!")
# SELECT EXISTS (SELECT 1 FROM users WHERE email = 'john@example.com');

# Count active users
active_count = await User.objects.count(db, User.is_active == True)
# SELECT count(*) FROM users WHERE is_active = true;
```

## 6. Relationships

To prevent N+1 queries, use the following methods:

- `select_related(*fields)`: Uses SQL `JOIN`. Ideal for many-to-one or one-to-one relationships.
- `prefetch_related(*fields)`: Uses separate `SELECT IN` queries. Ideal for many-to-many or reverse foreign keys (one-to-many).

!!! tip
    While `select_related` can be used for one-to-many relationships, it may result in row duplication and decreased performance. For collections or reverse relations, `prefetch_related` is generally recommended.

```python title="relationships.py"
# Eager load with JOIN
articles = await Article.objects.select_related("author").fetch(db)
# SELECT articles.*, authors.* FROM articles JOIN authors ON articles.author_id = authors.id;

# Eager load with separate query
articles = await Article.objects.prefetch_related("tags").fetch(db)
# SELECT * FROM articles;
# SELECT * FROM tags WHERE id IN (...);
```

## 7. Complex Expressions (Beta)

!!! warning "Beta Feature"
    `Q` objects and `F` expressions are in **Beta**. The API and behavior are subject to change.

### Q Objects

Encapsulate and combine query conditions using bitwise operators (`&`, `|`, `~`).

!!! tip
    `Q` objects are automatically resolved when passed to `filter()` or `exclude()`.

```python title="q_objects.py"
from flash_db.expressions import Q

# Combine conditions using bitwise operators
condition = (Q(name="John") | Q(name="Jane")) & ~Q(status="retired")

# Q objects are automatically resolved when passed to filter/exclude
users = await User.objects.filter(condition).fetch(db)
# SELECT * FROM users WHERE (name = 'John' OR name = 'Jane') AND status != 'retired';
```

### F Expressions

Reference model fields within queries.

!!! note "Current Limitation"
    `F` expressions currently require manual resolution before being passed to update methods. Automatic resolution within `update()` is planned for a future release.

```python title="f_expressions.py"
from flash_db.expressions import F

# Increment stock by 1 (Manual Resolution)
expr = (F("stock") + 1).resolve(Product)
await Product.objects.filter(id=1).update(db, stock=expr)
# UPDATE products SET stock = stock + 1 WHERE id = 1;
```