# Test guide — charters are named once, and an empty one says so

## Agent-verifiable

1. **Blank content is refused at both doors** (F134). Tasks 1.1 and 1.2 fail today and pass after.
2. **Real content is stored as written.** Control 1.3.
3. **An empty row that exists anyway is described, not delivered as a bare heading.** Task 1.4.
4. **A taken name is refused at both doors** (F183). Task 1.5; controls 1.6.
5. **Existing duplicates survive the migration, renamed, bindings intact.** Task 1.7.
6. **The race is closed by the index.** Task 1.8.
7. **Runner names are unique too** (F183, runners). Tasks 1.9-1.11: both runner doors answer 409
   naming the name, including in a race; controls 1.10 (other project, own name, case differs).
8. **The Hub never 500s on a name it chose itself.** Tasks 1.12-1.13: find-or-create suffixes past a
   taken name; a race answers 409 and leaves nothing behind.
9. **The migration covers both tables, truncates, and rebuilds neither.** Tasks 1.14-1.16.
10. **Live** (3.1, 3.2): the refusals render in both forms, and neither picker has two options alike.

## Human-only

1. After `:8000` restarts onto this change (the operator's call), the Charters screen and the binding
   picker look as before: `:8000` had no duplicate charter or runner names and no blank charters on
   2026-09-24, so nothing is renamed.
2. The Runners screen and the agent-creation runner picker look as before on `:8000`.
