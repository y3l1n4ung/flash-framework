# Roadmap

Here is a list of planned features and improvements for `flash_db`.

## Core API Enhancements

- [ ] **Transaction Management:** Add a decorator or context manager for atomic transactions.
- [ ] **`get_or_create()`:** Implement the `get_or_create()` method on the `ModelManager`.
- [ ] **`update_or_create()`:** Implement the `update_or_create()` method on the `ModelManager`.
- [ ] **Model Validation Hooks:** Introduce `clean()` or `full_clean()` methods on models for data validation before saving.
- [ ] **Simplified Session Management:** Investigate decorators or other patterns to reduce boilerplate for session handling.

## Querying

- [ ] **`Q` Objects:** Add support for `Q` objects to enable complex queries with `OR` and `NOT` conditions.
- [ ] **`F` Expressions:** Implement `F` expressions to allow referring to model fields within queries.
- [ ] **Advanced `QuerySet` Methods:**
    - [ ] `exclude()`: For excluding records.
    - [ ] `distinct()`: For retrieving unique records.
    - [ ] `aggregate()`: For performing aggregation functions like `Count`, `Sum`, etc.

## Signals

- [ ] **Signal Dispatcher:** Implement a signal dispatcher to allow other parts of an application to listen to database events.
- [ ] **`pre_save` / `post_save` signals:** Fire events before and after a model is saved.
- [ ] **`pre_delete` / `post_delete` signals:** Fire events before and after a model is deleted.
- [ ] **`m2m_changed` signal:** Fire an event when a many-to-many relationship is modified.

## Migrations

!!! note "Note on Current Status"
    `flash_db` does not yet have a built-in migration system. This is a planned feature.

- [ ] **Alembic Integration:** Provide a tighter, more seamless integration with Alembic for database schema migrations.
- [ ] **Simplified Migration CLI:** Create a simplified command-line interface for common migration tasks (e.g., `flash db makemigrations`, `flash db migrate`).

## Testing

- [ ] **Increase Test Coverage:** Expand the test suite to ensure all features are thoroughly tested.
- [ ] **Integration Tests:** Add more integration tests that cover the interaction between different components of the ORM.
