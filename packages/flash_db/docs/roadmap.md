# Roadmap

Our goal for `flash_db` is to build a lightweight, yet powerful, async ORM that feels intuitive to Django developers.

## Core API Enhancements

- [ ] **Transaction Management:** Atomic transactions via decorator or context manager.
- [x] **`get_or_create()` / `update_or_create()`:** Streamline create/update patterns.
- [ ] **Model Validation Hooks:** `clean()` methods for data validation.
- [ ] **Simplified Session Management:** Reduce boilerplate for session handling.

## Advanced Querying

- [ ] **`Q` Objects:** Support for complex `OR` and `NOT` conditions.
- [ ] **`F` Expressions:** Reference model fields within queries.
- [x] **Advanced `QuerySet` Methods:** `exclude()`, `distinct()`, `only()`, `defer()`, and aggregation functions.
- [ ] **Prefetching:** Efficiently load many-to-many and reverse foreign key relationships.
- [ ] **Bulk Operations:** Implement `bulk_create` and `bulk_update` for high-performance batch processing.
- [ ] **Complex Joins:** Simplified API for complex filtering and joining across multiple tables.
- [ ] **Rich Expressions:** Support for more database functions and expressions (e.g., `Coalesce`, `Subquery`).

## Signals

Signal dispatcher for database events:
- [ ] `pre_save` / `post_save`
- [ ] `pre_delete` / `post_delete`
- [ ] `m2m_changed`