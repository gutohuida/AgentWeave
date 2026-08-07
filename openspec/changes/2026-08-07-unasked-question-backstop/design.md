# Design

## Decision 1 — a durable row with a status, not an event

`EventLog` rows have no status, so a card driven by one could never be resolved: it would either
persist forever or have to be inferred away by scanning for a later run. `PermissionRequest` already
solved this exact shape — pending row, project-scoped list endpoint, card in the composer footer,
SSE invalidation — and that path is live-verified. `UnaskedQuestion` mirrors it.

The status set is `pending` → `asked` | `dismissed`. `asked` is not "answered": the operator
re-prompted the agent, and whether the agent then asks properly is the agent's business.

An `EventLog` row is *also* written, because the timeline is where an operator reconstructs what
happened after the fact. It is a record, not the mechanism.

## Decision 2 — detect on the final assistant text, not on the whole turn

The signal is the *last* thing the agent said. An agent that asks a question mid-turn and then
answers it itself, or asks rhetorically and continues working, has not stranded anything. Only a
turn whose final assistant output ends in a question has stopped and waited.

So detection reads the highest-`sequence` `AgentOutput` row for the run with `kind="text"` — the
kind both transports use for assistant prose — and looks at its last non-empty line.

### What counts as a question

Deliberately narrow, because a false positive puts a card in front of the operator for a turn that
was fine:

- The last non-empty line, after stripping markdown list markers, emphasis and trailing whitespace,
  ends with `?`.
- Text ending inside an unclosed code fence is never a question — a trailing `?` there is code.
- A line that is only punctuation is not a question.
- The captured text is bounded (400 chars) so a pathological line cannot bloat the row.

Rhetorical questions will occasionally slip through. That is the acceptable direction of error: a
dismissible card costs one click, while a missed question costs a stalled agent nobody knows about.

## Decision 3 — three suppressions, each for a measured reason

1. **Only a completed run.** A failed or stopped run has a louder story to tell, and its trailing
   text is often truncated mid-sentence.
2. **Only when the run opened no `Question` row.** `Question.created_by_run_id` already exists and is
   indexed, so this is the direct check. An agent that asked properly *and* signed off with a
   question mark is not the failure case.
3. **Only when the agent's inbound queue is empty.** `turn_scheduler.schedule_agent` runs immediately
   after this point and starts the next turn if anything is queued — the question is answered by the
   next turn's input, not stranded. Checked with the scheduler's own `queued_entries`, so the two
   cannot disagree.

## Decision 4 — "Ask this properly" is a server-side re-prompt

The button posts to `/unasked-questions/{id}/ask`, which flips the status and triggers the agent with
a canned instruction naming the exact question and requiring `ask_user` with structure.

Rejected: having the UI send an ordinary composer message. It would work, but the wording of the
re-prompt is part of the mechanism's correctness — it is what converts prose into a tool call — and
leaving it in a click handler puts it out of reach of the backend tests that can actually verify it.

Status flips before the trigger and is not rolled back if the trigger fails; the endpoint returns the
failure. Re-prompting twice would produce two turns racing on one question, which is worse than an
error the operator can see and retry from.

## Decision 5 — `severity="warning"` becomes `"warn"`

Not scope creep — it is the same defect class in the same feature. Nine `persist_event` call sites
across the Hub pass `"warn"`. The two `permission_denied` sites pass `"warning"`. The UI's severity
chips, borders and filter list know only `"warn"`, so denials render with no chip and are hidden by
the operator's "warn" filter. The new `question_not_asked` row uses `"warn"` from the start.

## Risks

- **False positives on conversational sign-offs** ("Want me to run the tests?"). Mitigated by the
  narrow rule and one-click dismiss, and bounded by the queue-empty suppression, which removes the
  common case where the operator is mid-exchange anyway.
- **A long-running turn's final text arriving after detection.** It cannot: detection runs after the
  read loop has drained and every `AgentOutput` row for the run is committed.
- **Two runs for one agent in flight.** The row is keyed by `run_id`, and the card filters by agent,
  so the worst case is two cards, each naming its own question.
