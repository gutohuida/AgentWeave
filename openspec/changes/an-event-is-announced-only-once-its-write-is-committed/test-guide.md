# Test guide — an event is announced only once its write is committed

## Agent-verifiable

1. **A refused review announces nothing.** Task 1.1 fails before the fix and passes after, with the
   spy on `SSEManager.publish` — the one funnel (design D2). A spy on `broadcast` alone would pass
   on a broken fix; do not accept one.
2. **A real review still announces, once.** Control 1.2 passes before and after.
3. **The order the app receives is unchanged.** 1.3: `run_divergence_resolved` precedes
   `task_updated` from the real PATCH route.
4. **Rollback, close-without-commit and double commit publish nothing extra.** 1.4.
5. **A bad payload cannot turn a committed write into a 500.** 1.5.
6. **The shape cannot come back.** 1.6's AST guard fails on today's tree at
   `hub/hub/run_divergence.py:104` only.
7. **On the wire**, on a trial Hub from source (not `:8000`): reproduce the 2026-09-13 delivery leg
   (`scripts/drive/t_d1_0913_render.py Q`, a review queued behind a running turn whose commit is
   then pruned) with `curl -N` on `/api/v1/events`. Before: `event: run_divergence_resolved` on the
   wire, 0 rows. After: no such frame. Then a true resolution (operator PATCH to `under_review`)
   still carries it, followed by `task_updated`.

## Human-only

None. Nothing on screen changes in this change: the app still drops `run_divergence_resolved`
until `every-event-the-hub-sends-reaches-the-app` lands.
