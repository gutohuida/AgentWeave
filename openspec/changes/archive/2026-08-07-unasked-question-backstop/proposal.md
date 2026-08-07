# A question the agent asked but never routed

**Approved:** 2026-08-07, operator (*"Ok, fix #1"*)

## Why

`2026-08-07-hub-answered-permission-approver` gave agents `ask_user`: a blocking tool that posts a
structured question and waits for the operator. It works, and when an agent calls it the operator
sees a card and answers in four seconds.

The problem is that calling it is a disposition, not a guarantee.

### Measured: Codex writes the question as prose and ends the turn

Told *"Ask me which package manager to use"*, Claude called `ask_user`. Codex wrote the question into
its final assistant message and ended the turn. No `Question` row was created, no card appeared, and
the operator — the one person who could answer — was never told a question existed. Told explicitly
to use the tool, Codex did it perfectly, with full structure. So the capability is present and the
disposition is not.

An agent that ends a turn on an unanswered question has stopped working and is waiting for something
that will never arrive. From the operator's side this is indistinguishable from a finished turn.

### A tool call cannot be forced, so it has to be detected

Nothing in either provider's protocol lets the Hub require that a turn end via a particular tool.
The structure requirement added by the previous change (`options`, `header`, `multi_select` are
mandatory) makes a call that happens *correct*; it cannot make a call *happen*.

What the Hub does have is the run's final assistant text and the set of `Question` rows the run
opened. A turn that ends in a question mark while having opened no question row is exactly the
failure above, and the Hub can see it.

### The precedent to copy is the request card, not the denial event

The obvious instruction — surface this the way `permission_denied` already is — was checked against
the running code and rejected. `permission_denied` is not surfaced in the conversation at all: it
reaches the global Activity log and the agent's Messages tab as the bare string `permission_denied`,
and its `reason` payload is never rendered in either. Copying it would produce a second invisible
signal, which is the bug this change exists to fix.

`PermissionRequest` is the pattern that demonstrably reaches the operator: a durable row with a
status, listed by a project-scoped endpoint, rendered as a card in the composer footer, refreshed by
SSE. This change copies that.

## What changes

- A run that completes having produced a trailing question and opened no `Question` row records an
  `UnaskedQuestion` row and broadcasts `question_not_asked`.
- The operator sees a card above the composer naming the question the agent failed to ask, with two
  actions: **Ask this properly** — re-prompts the agent to put that exact question through
  `ask_user` — and **Dismiss**.
- Detection is suppressed when it would be noise: a failed, stopped or interrupted run, and a run
  whose agent still has queued input (the next turn starts on its own, so nothing is stranded).
- `permission_denied` rows are persisted with `severity="warn"`, the value the rest of the codebase
  and the whole UI use, instead of `"warning"`, which nothing reads.

## Impact

- **New table** `unasked_questions` (migration 0032) and its operator-facing endpoints.
- **`hub/hub/api/v1/agent_trigger.py`** — both completion sites gain the same detection call.
- **Hub UI** — a new card in the composer footer, beside `PermissionRequestCard`.
- No change to the `ask_user` contract, to either provider's launch arguments, or to any posture.

## Explicitly not in this change

- **Making the agent ask correctly.** This is a backstop for the failure, not a fix for the
  disposition. Prompt-side work to raise the call rate is separate.
- **Batching** (the operator's follow-up #2) — one question at a time is unchanged here.
- **Answering the detected question in place.** The turn has ended; there is no blocked tool call to
  return a value to. The only honest action is to re-prompt the agent, which starts a new turn.
