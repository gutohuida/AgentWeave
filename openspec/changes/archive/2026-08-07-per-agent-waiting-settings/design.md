# Design

## Decision 1 — the agent's tab, not a gear

Grounded in what is already there rather than in taste:

- `AgentInfoTab` already renders editable `<select>`s for the runner and charter bindings, with
  `aria-label="Runner for {agent}"`. It is a settings surface with an information-sounding name.
- `ConversationControls`' overflow menu already has "Agent details", and there is a test asserting it
  opens **without unmounting the conversation**. The mid-chat path a gear would serve exists.

So the work is renaming and reorganising, not building a new surface. A gear would add a third home
for settings — alongside the composer pills and this tab — and blur the one distinction that
currently makes the pills legible: pills are *this conversation*, the tab is *this agent*.

## Decision 2 — two explicit columns, not a settings blob

A JSON `settings` column would take "and future things" literally and cost nothing today. Rejected
anyway: a blob has no schema, so nothing validates a range, nothing fails a bad key, and every reader
invents its own defaulting. Two nullable integers are checked by the database, the API and the type
checker.

When there are enough of these to feel repetitive, that is the moment to reconsider — with the real
list in hand rather than a guess at it.

`NULL` means "the built-in default" rather than copying the default into every row. A row storing 240
would keep saying 240 after the default moved, silently pinning every existing agent to a number
nobody chose.

## Decision 3 — the values travel in the run's environment

`mcp_server.py` runs as a separate process, imports only stdlib and fastmcp, and cannot reach the
database. The workspace boundary (`AW_WORKSPACE_DIR`) and the permission posture
(`AW_PERMISSION_POSTURE`) already reach it the same way, so this follows the established path rather
than inventing a second one.

The Codex app-server wait runs inside the Hub and reads the value directly; there is no process
boundary to cross there.

A malformed or absent variable falls back to the default rather than failing the run. A turn that
dies because a setting was mistyped is worse than one that waits the standard time.

## Decision 4 — bounded 10 to 600 seconds, defaults unchanged

The lower bound stops a wait so short the operator cannot answer it — under about ten seconds, the
card has barely rendered.

The upper bound is 600s, which is beyond anything measured. What *was* measured is narrower and worth
restating, because it is easy to read the defaults as arbitrary: the permission-prompt tool was
observed tolerating at least 150s and an ordinary MCP tool call at least 240s, and both figures were
the spike's own limits rather than a proven ceiling. So the defaults stay where measurement put them,
and values above those figures are permitted but untested — which the settings row says plainly
rather than leaving the operator to find out from a hung turn.

## Decision 5 — validation lives in the API, not only the UI

`PATCH /agents/{name}` takes a raw `dict`, so a bad value would otherwise reach the column. The range
is enforced there, and the UI's `min`/`max` are a convenience on top rather than the only guard.

## Risks

- **An operator sets 600s and an agent hangs for ten minutes.** Their choice, made explicitly, and
  the row says the measured figures. The turn still ends.
- **The environment variable is read once at spawn**, so changing a setting does not affect a run
  already in flight. Correct: a run's rules should not shift underneath it mid-turn.
