# Test guide — a runner that cannot collaborate says so where it is bound

## Agent-verifiable

1. **The collaboration verdict reaches a screen.** Task 1.1 fails before and passes after.
2. **No false warnings.** Controls 1.2 and 1.3 pass before and after.
3. **The dead card is gone.** `grep -rn "AgentCard" hub/ui/src` finds nothing. `vitest` shows one
   test file fewer, and the removed tests are exactly `agentCardCollaboration.test.tsx`'s.
4. **No query surface moved.** `test_surface_ceilings.py` passes with no warning about a lowered
   count.

## Human-only (trial Hub `:8010`, never `:8000`)

1. Create a Codex runner with flags `["--no-app-server"]`, with yolo off, and bind an agent to it.
   Open the agent's settings, Execution. Below the runner picker, the line reads *"This agent will
   run, but cannot collaborate: This Codex agent's runner opted out …"*. Judge whether it reads as
   something to act on.
2. Remove the flag, or enable yolo. The line disappears within the query's 30 s stale time, or on
   reload. (Rebinding invalidates it at once. Editing the runner's flags may not: record which.)
3. Bind a Claude runner. There is no collaboration line.
