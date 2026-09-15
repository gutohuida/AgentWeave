---
paths:
  - "hub/hub/db/**"
  - "hub/hub/migrations/**"
---

# Database and migration rules (loaded when a model or migration file is read)

A migration reaches the operator's **real** database the next time they restart their `:8000` Hub,
which runs this checkout (`.claude/reference/hubs.md`). Treat every migration as a change to their
data.

## Adding a database column

1. Add the field in `hub/hub/db/models.py`.
2. New migration in `hub/hub/migrations/versions/` — guard for a missing table, as `0033`/`0034` do,
   because upgrades starting from an early revision reach it with only that revision's tables.
3. Bump the head assertions in `hub/tests/test_migrations.py` **and**
   `hub/tests/test_project_persistence.py`.
4. Expose it on the relevant Pydantic schema if the UI needs it.
