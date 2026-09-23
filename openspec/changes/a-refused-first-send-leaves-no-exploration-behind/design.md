# Design — a refused first send leaves no exploration behind

**Built on the recommended answers to D-B12-1 (discard, not archive) and D-B12-2 (refuse the send
when the document cannot be created).** If the operator answers D-B12-1 with "archive", D3 below
becomes a phase move to `archived` through `spec_lifecycle` instead of a delete. The file then stays
in `spec/` and the spec list keeps the row, so F330 would be only half fixed (see D-B12-1). If the
operator answers D-B12-2 with "send anyway", D2's creation failure is turned into a
`waiting_reason`-style notice on a `200`, and the vitest case *"still starts the conversation when
the document cannot be created"* stays as it is.

## Context

- The composer creates the document first and triggers second
  (`NewConversationSurface.tsx:83-107`). A refusal throws at `:110-117` and nothing cleans up.
- `POST /project/documents` (`spec.py:1419-1467`) does four things. It mints a path
  (`spec_service.mint_document_path`), creates the row (`spec_lifecycle.create_document`,
  `spec_lifecycle.py:208-222`, which also writes a `created` event), and calls `save_document`. That
  **writes the file** (`spec_service.py:238`), records a content event and reindexes. Finally it
  commits. The file is written before the commit, so a failed commit already leaves a file with no
  row today.
- A file under `spec/` with no row is not inert. Discovery and adoption find it
  (`spec-document-authority` *Document discovery covers every safe document*, `:315`;
  `spec-document-adoption`). So a discard must remove the file as well as the row.
- `POST /agent/trigger` (`agent_trigger.py:1405-1671`) commits the conversation and the entry at
  `:1586`, then calls `schedule_agent`. Where the scheduler's refusal names this entry,
  `withdraw_refused_entry` runs and the route raises the refusal's status (`:1613-1641`).
- The composer restores the typed text whenever `onSubmit` throws (`Composer.tsx:216-217`).

## Decisions

### D1 — The trigger route creates the document, after its own refusals

`TriggerAgentRequest` gains `start_exploration: bool = False`. It is refused with 400 when combined
with `spec_document` or `conversation_id`, because an exploration belongs to a new conversation.

The document is created immediately before `new_entry` (`:1570`). That is after every route-level
refusal, so none of those can leave a document behind. It is created in the route's own session,
with the operator as actor, as `spec.py:1444-1462` does today. Rather than copying that body, both
routes share it: move the mint, create and save sequence into
`spec_service.start_exploration(session, workspace, project_id, title, actor)` and call it from
both. `trigger_agent` passes `title=body.message.strip()[:120]`, which is exactly what the composer
sends today (`NewConversationSurface.tsx:87`). The entry's `spec_document` is the new path.

**Rejected: the composer archives the document on refusal.** The row and the file would remain.
The spec list, whose default view R2 should check, and `spec/changes/` would still hold one entry
per retry. A network failure or a closed tab would still leave the orphan, because nothing would run
the cleanup.

**Rejected: create the document at dispatch** (the queue entry carries an intent; the Hub mints
when the turn starts). This is the only design with no discard at all. But it needs a queue-entry
column, and so a migration. It also leaves a *queued* first send (agent busy) with no document the
composer can open, and `onStarted(agent, conversation, path)` needs the path at once. Its dispatch
refusals roll back the database (`turn_scheduler.py:448`) but not a file already written, so it
would need the same compensation D3 describes, one layer further down.

### D2 — What the route returns when a function it calls raises

| raised | where | answer | what is left |
|---|---|---|---|
| `NamingExhaustedError` | mint | 409 `{"code": "naming_exhausted"}`, the same shape as `spec.py:1432-1436` | nothing: no row, no file, no entry |
| `PhaseError` | `create_document` | 409 `{"code": exc.code}` | nothing |
| `OSError` from `write_document` | `save_document` | 500. The session is rolled back, and any partial file at that path is removed if one exists (D3) | nothing, if the removal succeeds |
| anything | the commit at `:1586` | the error propagates as today (F329 answered 500). The file is removed before re-raising | nothing, if the removal succeeds |
| a refusal naming this entry | `schedule_agent` | the refusal's own status and detail, as F108 does today | the document is discarded (D3) |
| none; the turn starts or waits | | 200 with `spec_document` set | the document, which is correct |

If removing the file itself fails (`OSError`), the route still answers with the original error and
logs the path. It does not replace a refusal with a cleanup error. What remains is a file with no
row, which adoption can take in. That is the same outcome as today, and no worse.

### D3 — The discard is the request undoing itself, not a deletion route

`spec_service.discard_unused_exploration(session, workspace, document_id)` deletes the file first,
then the document's `spec_document_events`, `spec_requirements` and `spec_requirement_revisions`
rows (there should be none of the last two for an empty payload, but they are deleted by
`document_id` all the same), then the row. It commits and broadcasts `spec_updated` with the path.
It refuses, and returns `False` without touching anything, unless **all** of these hold:

- `phase == "exploring"`;
- every `spec_document_events` row for the document is one the request wrote: `created`, plus the
  content event `save_document` recorded, and no later one;
- no `tasks.spec_document_id` and no `loops.spec_document_id` names it (`db/models.py:713`,
  `:1502`).

It is called in exactly two places: the commit-failure branch, where only the file is removed
because the rows were rolled back, and the F108 branch after `withdraw_refused_entry` returns
`True`. There is **no route** that reaches it. That is why it does not contradict
`spec-document-authority`'s *A document that produced nothing can be archived*, which governs a
document someone has seen. R2 should check that sentence's "rather than a separate deletion path"
against this argument and either agree or push back.

The file is removed first because a row without its file is reported as "registered but its file is
missing" (`agent_actions.py:1418-1422`), while a file without its row is merely adoptable. So if
the delete is interrupted part-way, the leftover state is the milder of the two.

### D4 — The composer sends one request

`NewConversationSurface.handleSubmit` sends `{agent, message, start_exploration: exploring,
overrides}` and reads `spec_document` from the JSON response for `onStarted`. The `postJson(…
/project/documents)` block (`:82-96`) and its catch-and-continue are removed. The vitest case
*"still starts the conversation when the document cannot be created"* is replaced by D-B12-2's
case.

### D5 — Shipping order, because `:8000` runs this checkout

The Python half must be running on `:8000` before the bundle half reaches it. A new bundle against
an old Hub would send `start_exploration`, and `RequestModel` refuses unknown fields
(`hub/hub/schemas/common.py:21-27`, F116). So **every** explore send would be refused until
`:8000` restarts. A composer that detected an old Hub from the response cannot help, because it
never gets a response. So the change ships as two commits: the route first, and the bundle only
after the operator restarts `:8000` past the route's commit. This is the same restart gating UI-1
already has (`ROUNDS.md` UI-1's
precondition, `:8000` restarted past `c18a87b`).

## Round log

- **R1 (2026-09-24):** proposed. Decisions D-B12-1 and D-B12-2 are recorded in
  `spec-queue/tracks/B12.md`.
