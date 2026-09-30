# Test guide — a runner that cannot collaborate says so where it is bound

## Agent-verifiable

1. **The collaboration verdict reaches a screen.** Task 1.1 fails before and passes after.
2. **No false warnings.** Controls 1.2 and 1.3 pass before and after.
3. **The dead card is gone.** `grep -rn "AgentCard" hub/ui/src` finds nothing. `vitest` shows one
   test file fewer, and the removed tests are exactly `agentCardCollaboration.test.tsx`'s.
3a. **Fixing the runner clears the warning.** Task 1.5 fails before and passes after.
4. **No query surface moved.** `test_surface_ceilings.py` passes with no warning about a lowered
   count.

## Human-only (trial Hub `:8010`, never `:8000`)

1. Create a Codex runner with flags `["--no-app-server"]` **through the API** (`POST
   /api/v1/projects/<pid>/runners`; the app cannot set flags, F469), keep the agent's permissions off
   Full access, and bind an agent to it. Open the agent's settings, Execution. Below the runner
   picker, the line reads *"This agent will run, but cannot collaborate: This Codex agent's runner
   opted out …"*, ending with its two remedies: bind a runner without `--no-app-server`, or set
   Full access. Judge whether it reads as something to act on.
2. Without reloading, set the agent's permissions to Full access: the line goes at once. Set them
   back: it returns. Rebind the agent to a Codex runner created in the app (no flags): the line goes.
   Then rename, on the Runners page, the runner the agent is bound to, and return: the picker shows
   the fresh verdict without a reload (design D6). Deleting a bound runner is refused with "Unbind
   before deleting", so it cannot leave a stale verdict.
3. Bind a Claude runner. There is no collaboration line.
