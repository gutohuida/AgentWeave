## Context

Two unrelated-looking bugs share one shape: a value the code carries correctly all the way through
and no human-facing control ever reaches. Severity: `persist_event` (`hub/hub/utils.py:25`) is the
single choke point every one of the 21 call sites writes through, but it does not normalise —
`severity` is a free-form string, written verbatim (`utils.py:49`). Twenty of those call sites use
`"info"`, `"warn"`, or `"error"`; one (`run_divergence.py:613`) uses `"warning"`. `POST /logs`
(`hub/hub/api/v1/logs.py:71-97`) also reaches `persist_event`, with `severity` taken directly from
the request body (`schemas/logs.py:25`, `Field(default="info", max_length=64)` — no enum). Three
consumers key on the exact string `"warn"`: `EventRow.tsx`'s `SEVERITY_CHIP` (~37) and
`SEVERITY_BORDER` (~44), and `ActivityLog.tsx`'s `SEVERITY_FILTERS` (~31) with its strict-equality
filter (~165). `GET /events/history` (`events.py:42-43`) and `GET /logs` (`logs.py:58-59`) filter
`EventLog.severity` the same way. `"warning"` matches none of them: the `turn_produced_nothing`
event — precisely the one meant to draw attention — renders with no chip, no border, and is
reachable only when the severity filter is `all`.

Titling: `conversation_titles.generate_conversation_title` (`conversation_titles.py:168`) is
complete — gated on `project.conversation_title_mode == "generate"` (`:185`), called from
`agent_trigger.py` at run completion, bounded by a concurrency gate, and correctly declines to
overwrite an operator-set title (`:181`, `:213`). The field is modelled
(`db/models.py:96` `conversation_title_mode`, `:103` `conversation_title_runner_id`), schema'd
(`api/v1/projects.py:87-89`, `Literal["truncate", "generate"]`), typed on the frontend
(`ui/src/api/projects.ts:88-89`), and the settings endpoint already validates and persists both
(`PUT /projects/{id}/settings`, `projects.py:446-496`, including the cross-project runner-id check
at `:485-496`). `ProjectSettingsPanel.tsx` has zero references to either field. The panel's own test
(`projectSettingsPanel.test.tsx:23-24,146-147`) fixtures `conversation_title_mode: 'generate'` and
asserts the round trip, so the suite is green over a value no operator control produces.

`agent-capability-plane`'s existing requirement ("Operator-facing severity values are the ones the
operator's view understands") already states the general rule this change enforces, but its only
scenario is a refused-action event — it was never exercised against the general case, which is
exactly how `run_divergence.py:613` drifted unnoticed. `conversation-lifecycle`'s existing
requirement ("Title generation is a project setting, off by default") documents the setting's
existence and behaviour but never requires it be operator-settable through the UI.

## Goals / Non-Goals

**Goals:**
- Close the severity-spelling class, not just the one instance: normalise inside `persist_event`
  itself, the one place every writer (internal call site or external `POST /logs` caller) passes
  through.
- Make `conversation_title_mode` / `conversation_title_runner_id` settable from
  `ProjectSettingsPanel.tsx`, using the endpoint that already validates them.
- Strengthen the two existing spec requirements that this change makes newly true, rather than
  writing new ones that duplicate them.

**Non-Goals:**
- No database `CHECK` constraint on `EventLog.severity`. The column is `String(10)` with no
  existing constraint; adding one would need a migration that first repairs the three existing
  `"warning"` rows in any already-running database, which is a data-migration concern distinct from
  closing the write path. Left as a possible follow-up, not part of this change.
- No backfill of the three existing `"warning"` rows already persisted. They are historical and
  reachable by the `all` filter today; this change stops new ones, not old ones.
- No change to `LogEventCreate`'s schema validation (still `str`, not a `Literal`). `persist_event`
  normalising is the enforcement point; adding a second one at the schema layer is redundant and
  this change keeps to one.
- No new capability, no rename of `"Hub"`, no touch to any other severity-adjacent behaviour (e.g.
  the `debug` value some UI code already reserves but nothing yet emits).

## Decisions

**Normalise in `persist_event`, against an enumerated set, mapping anything unrecognised to
`"warn"`.** Alternatives considered: (a) fix only `run_divergence.py:613` — rejected, matches the
exploration's own conclusion that this "closes the instance, not the class," and leaves `POST
/logs`'s external input path completely open; (b) validate at the API boundary
(`LogEventCreate`/`Literal`) only — rejected as incomplete on its own, since it would leave every
internal call site free to typo a new spelling that `persist_event` still wrote verbatim; the fix
belongs at the point every path already converges. Mapping an unrecognised value to `"warn"` rather
than `"info"` is deliberate: an unrecognised severity is more likely a drifted spelling of something
that mattered (as `"warning"` was) than routine noise, and `"warn"` is the direction that fails
toward visibility rather than away from it.

**Enumerated set is `{info, warn, error, debug}`.** These are exactly the values `EventRow.tsx`'s
`SEVERITY_CHIP` and `ActivityLog.tsx`'s `SEVERITY_FILTERS` already recognise today, so the set is
read off the UI's own vocabulary rather than invented. `debug` has no current writer but is already
reserved by both UI maps; including it now means a future writer does not have to touch the
normalisation function to use a spelling the UI already understands.

**`run_divergence.py:613` changes to `severity="warn"` directly**, rather than relying solely on the
new fallback to rewrite it silently. The call site should say what it means; the normalisation
exists to catch what a call site gets wrong next, not to launder a known-wrong literal forever.

**Conversation-title row modelled on the existing "Checkpoint runner" / "Checkpoint model" pair**
(`ProjectSettingsPanel.tsx:243-272`): a `Select` for `conversation_title_mode`
(`truncate`/`generate`), and, following the same pattern as `checkpointRunner`, a runner `Select`
for `conversation_title_runner_id` populated from `useRunners()`. Alternative considered: gate the
runner select's visibility on `mode === 'generate'` — rejected in favour of matching the checkpoint
pair's own precedent, which shows its runner select unconditionally (`checkpoint_runner_id` matters
only when checkpointing is on, and the panel does not hide it either); consistency with the existing
row it is modelled on outweighs a marginal reduction in visible controls.

**No backend change for the titling half.** `PUT /projects/{id}/settings` already accepts, merges,
and validates both fields (including the cross-project runner-id check). Confirmed by reading
`projects.py:446-496` — this is a pure UI-reachability fix.

## Risks / Trade-offs

- [Risk] Mapping an unrecognised severity to `"warn"` could surprise a future caller that
  deliberately wants a severity the current UI does not yet render (e.g. introducing a new value
  ahead of UI support) → Mitigation: the fallback is documented at the normalisation function
  itself, and the enumerated set is intentionally the UI's own vocabulary — a caller wanting a new
  severity must add UI support in the same change, which is the discipline this change exists to
  enforce.
- [Risk] Making `conversation_title_runner_id` reachable means an operator can now point titling at
  a runner whose CLI is unsupported by `_SUPPORTED_CLIS` → Mitigation: not a new risk —
  `generate_conversation_title` already declines silently (`:189-190`) when the resolved runner's
  CLI is unsupported; this change does not touch that guard.

## Migration Plan

No database migration. Both `EventLog.severity` (already a free-form indexed `String(10)`) and
`Project.conversation_title_mode`/`conversation_title_runner_id` (already columns, already exposed
on the settings schema and endpoint) exist today. This change edits `persist_event`, one call site,
and one React component.

## Open Questions

None outstanding — both halves were fully explored against the code before this design was written,
and both fixes are UI/application-layer only.
