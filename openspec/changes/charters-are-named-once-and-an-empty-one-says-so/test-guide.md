# Test guide — charters are named once, and an empty one says so

## Agent-verifiable

1. **Blank content is refused at both doors** (F134). Tasks 1.1 and 1.2 fail today and pass after.
2. **Real content is stored as written.** Control 1.3.
3. **An empty row that exists anyway is described, not delivered as a bare heading.** Task 1.4.
4. **A taken name is refused at both doors** (F183). Task 1.5; controls 1.6.
5. **Existing duplicates survive the migration, renamed, bindings intact.** Task 1.7.
6. **The race is closed by the index.** Task 1.8.
7. **Live** (3.1): the refusals render in the form, and the picker has no two options alike.

## Human-only

1. After `:8000` restarts onto this change (the operator's call), the Charters screen and the binding
   picker look as before: `:8000` had no duplicates and no blank charters on 2026-09-24.
