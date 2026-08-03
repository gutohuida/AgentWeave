## Why

The conversation composer (`hub/ui/src/components/agents/Composer.tsx`, shipped by the archived
`2026-08-02-agent-conversation-workspace` change) is a plain autosizing `<textarea>`: no way to
reference a workspace file, invoke a skill, or run a built-in command while composing a message,
and no way to redirect an in-flight conversation to a different agent without leaving it. Both
gaps were identified and deliberately deferred during that change — see
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` phase 11 (items 11.2–11.5) and phase
12 (item 12.1), both annotated `SUPERSEDED (2026-08-02) — re-cut as its own change ... ready to
propose`. This closes that deferred slice.

## What Changes

- Add trigger detection to the composer: typing `@` opens a workspace-path picker, `/` at line
  start opens a built-in-command picker, `$` opens a skill picker. Detection returns
  `{kind, query, rangeStart, rangeEnd}`; a null result means no menu.
- Add range replacement: accepting a menu result rewrites the exact matched span and repositions
  the cursor immediately after the inserted (quote-escaped, if it contains whitespace) reference —
  never at the end of the whole composer value.
- Add a keyboard-navigable trigger menu (arrow keys move, Enter/Tab accept, Escape dismiss).
  Dismissal must restore focus and leave the typed text untouched.
- Add a new backend endpoint that lists workspace paths under the project's working directory
  (files and directories, respecting `.gitignore`), so the `@path` source has something to query
  against — no such endpoint exists today.
- Wire the `@path` source to that new endpoint (unscoped) and the `$skill` source to the same
  endpoint scoped to the project's skill directories — there is no existing Hub-side skill-listing
  API to reuse; skill discovery today is purely a CLI-side template-copy mechanism
  (`src/agentweave/templates/skills/`), not something the Hub serves (design.md justifies this
  reuse over a second bespoke endpoint). Wire `/command` to a small static built-in list — no
  backend involvement, since it's just the commands the composer itself supports.
- Add a searchable, in-place agent/runner selector to the composer chrome: lets the operator
  redirect the *next* turn of the current conversation to a different configured agent, showing
  each candidate's launchability (present / authorized / runnable) from the existing
  `GET /api/v1/agents/launchability` endpoint (`hub/hub/api/v1/agents.py:124`,
  `hub/hub/launchability.py:36`'s `probe_agent`). Selecting a different agent does not migrate the
  conversation's history or its bound provider session — those stay scoped to the original agent
  per `agent-conversation-workspace`'s immutable-scope requirement; redirecting starts a new
  conversation with the newly selected agent.

## Capabilities

### New Capabilities
- `agent-composer`: trigger detection, range replacement, the trigger menu, its three result
  sources (workspace paths, skills, built-in commands), and the in-place agent/runner selector.
  Distinct from `agent-conversation-workspace`, which owns the composer's shell (autosizing,
  drafts, submit/stop) and does not change here.

### Modified Capabilities
(none — this only adds a new capability layered on top of the existing composer shell; no
existing capability's requirements change)

## Impact

- **New backend route**: a workspace path-listing endpoint (module TBD in `hub/hub/api/v1/`,
  design.md picks the exact shape) — the one net-new backend surface this slice needs.
- **Frontend**: `hub/ui/src/components/agents/Composer.tsx` gains the trigger-detection wiring; a
  new self-contained trigger-detection module (mirrors the boundary rules described in
  `openspec/changes/2026-07-30-hub-native-experience/design.md`'s "B. Composer trigger detection"
  — adopt the *behavior*, write a fresh implementation, do not port T3's file); a new menu
  component; a new agent-selector component consuming the existing launchability endpoint.
- **No changes** to `hub/ui/src/lib/composerDrafts.ts`, conversation/run/queue backend models, or
  any `agent-conversation-workspace` requirement.
