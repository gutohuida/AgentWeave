# Proposal — an "Ask me" card says what "Workspace only" would decide

**Round 1, 2026-09-24** (bundle B4, spec track S10). Findings: **F230 (C)**, **F284 (C)**.
**Built on the recommended answer to operator decision D4, second half** (*"Does the manual card
show the workspace verdict?"* — yes, as advice; see `design.md`). Nothing here is implemented.

## Why

Under "Ask me" (`manual`), `approve_tool_call` sends every non-Hub tool call to the operator
(`hub/hub/mcp_server.py:1700-1707`) and never consults `_decide`, the workspace judge. The card the
operator answers names the tool and the path or command and nothing else
(`PermissionRequestCard.describe`, `hub/ui/src/components/agents/PermissionRequestCard.tsx:21-47`);
`requestKind` labels an in-worktree write and a write to the project root identically
"File change" (`:49-59`). The response schema has no boundary field
(`PermissionRequestResponse`, `hub/hub/api/v1/permissions.py:31-45`), nor does the row
(`PermissionRequest`, `hub/hub/db/models.py:1592-1626`). Re-verified at `ce086b6`: F230's drive
(default posture refused a write the manual posture let through on one click) and F284's
(two cards nine minutes apart, one inside `.agentweave/worktrees/asker`, one in the project root,
indistinguishable) both still describe the code.

The operator is the last person who could stop the call, deciding in seconds under a timeout, and is
given less than the Hub already computes. `manual` reads as the safer posture; it is the one in which
a human judges without the inputs.

## What changes

1. **The approver works out the "Workspace only" verdict before asking.** `_ask_operator` calls
   `_decide(tool_name, tool_input)` — the same pure, total function that answers under "Workspace
   only" — and sends its `{allow, reason}` as `workspace_verdict` with the request. The operator
   still decides; the verdict is advice, never an answer.
2. **Codex's operator path does the same** with the check its "Workspace only" posture uses
   (`codex_appserver.decide_approval`'s `_within(cwd or grantRoot, workspace)`), in
   `_await_operator_permission` (`hub/hub/api/v1/agent_trigger.py:2777-2830`).
3. **The Hub stores and returns it**: an optional `workspace_verdict` on `PermissionRequestCreate`
   (`agent_actions.py:1013-1018`), a nullable JSON column on `permission_requests` (migration 0106),
   and the field on `PermissionRequestResponse`. A request opened without one (an older approver, or
   the Hub's own archive request, `operator_direction.py:182`) stores `null`.
4. **The card shows it.** Beside the path or command: *"Outside this agent's workspace — Workspace only
   would refuse this: …reason…"* in the warning style, or *"Workspace only would allow this"* muted,
   or nothing when the verdict is `null`. It never says a command "stays inside".
5. **An allow says what it did not check.** `_decide`'s allow reason for a shell command that names a
   variable or a substitution becomes *"inside your workspace as far as its text shows; it names a
   value the shell decides when it runs"*. Today nobody reads an allow reason
   (`record_permission_decision` records refusals only, `agent_actions.py:969-1010`); the card would
   be its first reader, and *"inside your workspace"* would overclaim for `cp x $DEST` (D5).

## Not changed

- What "Ask me" does: every call is still put to the operator; nothing is auto-refused.
- The default posture (the sibling change `the-permissions-pill-shows-the-posture-the-run-gets`).

## Impact

- **Code:** `hub/hub/mcp_server.py` (`_ask_operator`, `_decide`'s allow reason) — reaches `:8000`'s
  next run on edit; `hub/hub/api/v1/agent_actions.py`, `permissions.py`, `agent_trigger.py`,
  `codex_appserver.py`, `db/models.py`, a migration (reaches `:8000`'s real data on their next
  restart; `.claude/rules/db-migrations.md`); `hub/ui/src/api/permissions.ts`,
  `PermissionRequestCard.tsx` and a UI bundle.
- **The window between edit and restart is the hazard** (design D2): a new approver talking to an
  un-restarted Hub. Handled by one retry without the field on a 422.
- **Tests:** below; migration head assertions in `hub/tests/test_migrations.py` and
  `hub/tests/test_project_persistence.py`.
- **Spec:** `agent-run-sandboxing` — one added requirement.
