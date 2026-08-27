## Why

Two features in this codebase work correctly end-to-end and are unreachable by a human at one end
of the pipe. `run_divergence.py:613` persists `turn_produced_nothing` — an agent's turn that ended
having written nothing and asked nothing, precisely the event that wants attention — with
`severity="warning"`, while `EventRow.tsx`'s `SEVERITY_CHIP`/`SEVERITY_BORDER` and
`ActivityLog.tsx`'s `SEVERITY_FILTERS` (and its strict-equality filter) all key on `"warn"`. The
event renders with no chip, no border, and is invisible under every severity filter except `all`.
`persist_event` (`hub/hub/utils.py:25`) writes whatever string a caller passes, with no
normalisation, so a second bad spelling is one call site away — and `POST /logs`
(`hub/hub/api/v1/logs.py:85`) already accepts an arbitrary caller-supplied `severity` string (the
schema only bounds it to 64 characters), so the input is not even limited to this codebase's own
call sites. Separately, `conversation_titles.generate_conversation_title` is fully implemented and
wired — gated on `project.conversation_title_mode == "generate"`, called at run completion — and the
field exists on the model, the API schema, and the TypeScript type, but
`ProjectSettingsPanel.tsx` renders no control for it. The only way to turn on AI-generated
conversation titles today is writing to the database by hand; its own test fixtures the value
without any UI path producing it.

Both are the same defect: a value the code carries correctly that no operator control makes
reachable. `agent-capability-plane`'s existing requirement — "Operator-facing severity values are
the ones the operator's view understands" — already states the general principle but is pinned by
only one scenario (a refused action), so a second call site drifting out of vocabulary was never
guarded against. `conversation-lifecycle`'s existing requirement — "Title generation is a project
setting, off by default" — documents that the setting exists but never requires that an operator be
able to set it without direct database access.

## What Changes

- `persist_event` normalises `severity` against an enumerated set (`info`, `warn`, `error`,
  `debug`) before writing, so a call site (or an external `POST /logs` caller) cannot introduce a
  spelling the operator's views do not recognise. An unrecognised value is mapped to a defined
  fallback rather than written verbatim. `persist_event` returns the normalised value.
- `run_divergence.py:613` is corrected to `severity="warn"` — the instance the normalisation above
  also closes as a class.
- `POST /logs` (`hub/hub/api/v1/logs.py`'s `push_log`) uses `persist_event`'s returned, normalised
  severity in the SSE broadcast payload it builds afterwards, instead of the raw `body.severity` it
  builds that payload from today. Found during Q1-R2 (compare-to-code): the broadcast dict at
  `logs.py:87-96` is built independently of the write and reads `body.severity` again, so an
  out-of-vocabulary severity would still reach a live `ActivityLog` subscriber over SSE
  unnormalised even after the persisted row is fixed — only a later fetch of history (`GET
  /events/history`, `GET /logs`) would see the corrected value. Closing only the write path would
  leave the live path open, the same class of bug this change exists to close.
- `ProjectSettingsPanel.tsx` gains a "Conversation titles" row exposing `conversation_title_mode`
  (`truncate` / `generate`) and, when generation is selected, `conversation_title_runner_id` —
  modelled on the panel's existing "Checkpoint runner" / "Checkpoint model" rows. No backend change
  is needed for this half: `PUT /projects/{id}/settings` already validates and persists both fields.

## Capabilities

### New Capabilities

(none — both halves correct existing capabilities' behaviour rather than introducing new ones)

### Modified Capabilities

- `agent-capability-plane`: "Operator-facing severity values are the ones the operator's view
  understands" is strengthened from a per-call-site correctness expectation to an enforced
  normalisation at the point of persistence, with a scenario covering a caller (internal or
  external) supplying a severity spelling outside the enumerated set.
- `conversation-lifecycle`: "Title generation is a project setting, off by default" gains a
  requirement that the setting is presented as an operator-facing control, not reachable only by
  direct API or database access.

## Impact

- `hub/hub/utils.py` (`persist_event`) — add normalisation, return the normalised value.
- `hub/hub/run_divergence.py:613` — fix the one known bad spelling.
- `hub/hub/api/v1/logs.py` (`push_log`) — broadcast the normalised severity, not `body.severity`.
- `hub/ui/src/components/environment/ProjectSettingsPanel.tsx` — add the settings row.
- `hub/ui/src/__tests__/projectSettingsPanel.test.tsx` — currently fixtures
  `conversation_title_mode`/`conversation_title_runner_id` with no control exercising them; extend
  to cover the new row.
- No database migration: both `conversation_title_mode` and `conversation_title_runner_id` already
  exist on `projects` and are already validated by `PUT /projects/{id}/settings`.
