# Test guide — an "Ask me" card says what "Workspace only" would decide

## Agent-verifiable

| What | How | Passes when |
|---|---|---|
| The approver sends the verdict | `py -3.11 -m pytest hub/tests/test_permission_approver.py -q` (tasks 1.1, 1.2) | outside → `allow: false` with the judge's reason; an allow over a variable says so |
| An un-restarted Hub still gets asked | same (task 1.3) | a 422 is retried once without the field; a 500 is not retried |
| The Hub stores and returns it | route test (task 1.4) | stored, returned, `null` when absent, 422 when overlong |
| Codex too | task 1.5 | an outside `cwd` stores `allow: false` |
| The card shows it, in the route's order | `cd hub/ui && npm test` (task 1.6) | warning on the outside card, muted on the inside one, nothing on `null` |
| Migration | task 1.7 | head assertions pass |

## Human-only

1. On the trial Hub `:8010`, set an agent to "Ask me" and ask it to write `notes.txt` in its own
   workspace, then `../notes.txt`. **Expect:** two cards; the second says *Outside this agent's
   workspace — Workspace only would refuse this* and names the path; the first says *Workspace only
   would allow this*.
2. Ask it to run `cp notes.txt $DEST`. **Expect:** the card does not claim the command stays inside
   ("A shell command is read, not sandboxed").
3. Allow the outside write. **Expect:** it lands, and the activity log records it as a write outside
   the workspace (unchanged behaviour).
