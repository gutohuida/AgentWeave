# Test guide — the workspace judge reads paths, not patterns

## Agent-verifiable

1. Group 1 fails and passes as recorded in `tasks.md` 1.10 and 2.4. Every control row was refused
   before the change and is still refused after it.
2. For each command in `tasks.md` 1.1, `_decide("PowerShell", …)` answers allow, and
   `_decide("Shell", …)` and `_decide("Bash", …)` still refuse.
3. After drive 3.1, in the trial database (`mode=ro`):
   - `event_logs` holds no `permission_denied` row for the run;
   - the run's `agent_outputs` contain the listing.
4. After drive 3.2, a `permission_denied` row names the outside path.
5. The full Hub suite passes, with no existing assertion edited.
6. (R2) After drive 3.3, the subagent's shell call is confirmed keyed `"PowerShell"` (allowed, not
   refused by the `"Shell"` bash reading). If it is keyed `"Shell"`, the change does not fix the
   *observed* drive failures and a finding is recorded. The trial DB alone cannot settle this — the
   raw `tool.execution_start.toolName` is not stored — so the Hub log (or a captured fixture) is the
   evidence.

## Human-only

1. Is the line drawn in the right place? A regex or wildcard pattern after `-match`, `-notmatch`,
   `-like`, `-notlike`, `-replace` or `-split`, inside an expression, is no longer read as a path.
   Everything else still is. Do you want `Select-String -Pattern` and `rg`/`grep` patterns as well
   (`wpc2-c`)?
2. In drive 3.1, did the Copilot agent's listing now finish its turn without a refusal? Did
   anything else in that turn get refused that you would have expected to pass?
3. The judge still lets a variable or a computed path through (`Remove-Item $x`). Is that
   acceptable as the posture's known limit, or should it be the next finding?
