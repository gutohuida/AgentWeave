# Test guide — drift watches the files its evidence is about

## Agent-verifiable

1. **One unrelated commit raises nothing.** Task 1.1 fails before and passes after. It is the
   measurement R1 made, turned into a test.
2. **The named file still drifts.** Control 1.2 passes before and after.
3. **Agent evidence is watched after it lands (F217).** Task 1.6 fails before and passes after, and
   asserts `reachable_from_main` so it cannot pass because of some other difference.
4. **A resolution survives the basis flip.** Task 1.7.
5. **What is not watched is listed.** Tasks 1.5 and 1.8 read `unwatched` with both reasons.
6. **The migration is at head** in `test_migrations.py` and `test_project_persistence.py`.
7. **Nothing else moved.** The full-suite count in 2.6, with only 1.9's rewrites named.
8. **Drive** (3.1): F217's leg-3 table re-measured; the agent row now raises one candidate.

## Human-only

Nothing to check by eye: drift has no screen until `drift-is-scanned-and-answered-on-the-document`
ships. After it does, the checks in that change's guide exercise this one too.
