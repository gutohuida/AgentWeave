# Test guide — a firing is counted once, however many agents it starts

## Agent-verifiable

1. **The counter counts firings.** Tasks 1.1 and 1.2 fail before the fix (2 and 3) and pass after
   (1 and 2). Reversing the fix (restoring the increment in `_stage_selection`) makes both fail
   again.
2. **Nothing else moved the counter.** Controls 1.3 and 1.4 pass before and after.
3. **The card's word.** Task 1.5 fails before (`0 runs`) and passes after (`0 fired`).
4. **The live route.** Task 3.1: one press on a two-agent flow reads `run_count: 1` with two history
   rows.

## Human-only

1. On the Jobs page, find a flow that has fired at least once since this change. The badge reads
   *"N fired"*. Press Run once while two of its tasks are startable and two agents are free; the
   number goes up by one, not two.
2. **Expected, not a defect:** a flow that fired wide *before* this change keeps its old, higher
   number. The history is pruned, so the Hub cannot recount it (design D3).
