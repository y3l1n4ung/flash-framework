# Roadmap

Our development goals prioritize building a lightweight, Django-inspired async ORM.

## Features

- [ ] **Transaction Management:** Atomic transactions via decorator or context manager.
- [x] **Shortcuts:** `get_or_create()` and `update_or_create()` patterns.
- [ ] **Model Validation:** `clean()` hooks for data integrity.
- [x] **Advanced Querying:** `exclude()`, `distinct()`, `only()`, `defer()`.
- [x] **Complex Lookups:** `Q` Objects and `F` Expressions (Beta), Prefetching.
- [x] **Performance:** `bulk_create`, `bulk_update` (Beta).
- [ ] **Signals:** `pre_save`, `post_save`, `pre_delete`, `post_delete`.
