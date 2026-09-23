# Test guide — the Permissions pill shows the posture the run gets

## Agent-verifiable

| What | How | Passes when |
|---|---|---|
| Catalog default = spawn default | `py -3.11 -m pytest hub/tests/test_permission_approver.py -q` (tasks 1.1, 1.2) | both providers agree; argv at rest equals argv with the named posture |
| The list says what a run gets | agents-list test (task 1.3) | `workspace` / `acceptEdits` / `bypassPermissions` / `null` per case |
| The pill and the select read it | `cd hub/ui && npm test` (tasks 1.4, 1.5) | "Workspace only" for a fresh Claude agent; no override sent |
| Nothing else moved | full suites (task 2.5) | counts recorded |

## Human-only

1. On the trial Hub `:8010`, create a Claude agent and set no default posture. **Expect:** the
   composer's Permissions pill reads "Workspace only", and the agent's settings read "Built-in
   default (Workspace only)".
2. Send it "run `ls /`". **Expect:** refused (the pill told the truth); the refusal names `'/'`.
3. Choose "Edit files" in the pill for one message. **Expect:** that run's command carries
   `--permission-mode acceptEdits`, and the agent's default is unchanged.
