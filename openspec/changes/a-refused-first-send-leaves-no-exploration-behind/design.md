# Design — a refused first send leaves no exploration behind

**Built on R2's recommended answers to D-B12-1 and D-B12-2** (R2 reversed R1's D-B12-1; see D3 and
`spec-queue/tracks/B12.md`).

- **D-B12-1 (R2): nothing that was committed is ever deleted.** The document is created after every
  refusal the route can answer itself, and in the same transaction as the conversation and the
  queue entry, so a route-level refusal or a failed commit leaves no row, and the route removes the
  one file it wrote before the commit. The only refusal that arrives *after* the commit, a
  dispatch refusal naming this entry (F108), archives the document through the phase machine, as
  the operator's own act, with the refusal as its reason. R1 recommended deleting the row, its
  events and its file in that case. That contradicts two requirements of the main
  `spec-document-authority` spec, not one: *Every change to a document is recorded as an attributed
  event* (`openspec/specs/spec-document-authority/spec.md:208-230`: "A recorded event MUST NOT be
  edited or removed", scenario *History cannot be rewritten*) and *A document that produced nothing
  can be archived* (`:1891-1902`: "rather than a separate deletion path"). If the operator prefers
  deletion anyway, this change must carry MODIFIED deltas to both requirements; it does not today.
- **D-B12-2: refuse the send when the document cannot be created.** If the operator answers "send
  anyway", D2's creation failure becomes a notice on a `200`, and the vitest case *"still starts the
  conversation when the document cannot be created"* stays as it is.

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
  `spec-document-adoption`). So the commit-failure branch must remove the file the request wrote, since the rows roll back and the file does not.
- `POST /agent/trigger` (`agent_trigger.py:1405-1671`) commits the conversation and the entry at
  `:1586`, then calls `schedule_agent`. Where the scheduler's refusal names this entry,
  `withdraw_refused_entry` runs and the route raises the refusal's status (`:1613-1641`).
- The composer restores the typed text whenever `onSubmit` throws (`Composer.tsx:216-217`).

## Decisions

### D1 — The trigger route creates the document, after its own refusals

`TriggerAgentRequest` gains `start_exploration: bool = False`. It is refused with 400 when combined
with `spec_document`, `conversation_id`, `session_mode="resume"` or `review_task_id`: an exploration
belongs to a new conversation (a resume can land on an existing one, `agent_trigger.py:1478-1491`),
and a review turn's subject is a commit, not a document being explored.

**Every refusal the route raises before the creation point (R2, `agent_trigger.py:1415-1565`):**
invalid agent name (400), bad `session_mode` or missing `session_id` (400), archived agent (409),
workspace unavailable (`raise_workspace_http_error`), `work_dir` against a writing agent or invalid
(400), a closed or unknown conversation (409), `task_id` unresolvable (`TaskBindingError`) or
already decided (409), `review_task_id` with no commit or refused by `review_dispatch_refusal`, and
overrides with no runner, a vanished runner or invalid values (409/400). All of them are before
`new_entry` (`:1567`), so none can leave anything behind. The only failures after it are the
commit (`:1586`) and `schedule_agent`'s refusals.

The document is created immediately before `new_entry` (`:1570`). That is after every route-level
refusal, so none of those can leave a document behind. It is created in the route's own session,
with the operator as actor, as `spec.py:1444-1462` does today. Rather than copying that body, both
routes share it: move the mint, create and save sequence into
`spec_service.start_exploration(session, workspace, project_id, title, actor)` and call it from
both. `trigger_agent` passes `title=body.message.strip()[:120]`, which is exactly what the composer
sends today (`NewConversationSurface.tsx:87`). The entry's `spec_document` is the new path.

**Rejected: the composer archives the document on refusal.** The row and the file would remain.
The spec tree's current view hides archived documents (R2: `specNavigation.ts:53`), but the browser lists them under *Archived*, and `spec/changes/` would still hold one entry
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
| a refusal naming this entry | `schedule_agent` | the refusal's own status and detail, as F108 does today | the document, **archived** as the operator's act with the refusal as its reason (D3) |
| an environment-level refusal (no runner, runner busy) | `schedule_agent` | 200 `queued` with `waiting_reason`; it produces no `refusal` (`:1654-1658`) | the document, correctly: the input is still queued and will run with it |
| anything unexpected | `schedule_agent`, `persist_event` or the broadcast, all after the commit | 500, as today | the document and the still-queued entry, correctly: the input will be delivered. The composer's thrown error is the only wrong signal, as it is for every send today |
| none; the turn starts or waits | | 200 with `spec_document` set | the document, which is correct |

If removing the file itself fails (`OSError`), the route still answers with the original error and
logs the path. It does not replace a refusal with a cleanup error. What remains is a file with no
row, which adoption can take in. That is the same outcome as today, and no worse.

### D3 — After the commit, a refused send archives its document; nothing is deleted (R2)

R1's D3 deleted the file, the events, the index rows and the row. R2 reverses that, for three
reasons found in the code and the main spec:

1. **It deletes append-only history.** `spec_document_events` is append-only by contract
   (`spec-document-authority` *Every change to a document is recorded as an attributed event*, and
   the model's own docstring, `db/models.py:2085-2092`). The `created` and content events R1's D3
   deleted are recorded events. R1 argued only against `:1891`'s "separate deletion path" and did
   not weigh this requirement.
2. **Most of the benefit does not need it.** Every route-level refusal is before creation (D1), and
   a failed commit rolls the rows back. F330's recorded case (F329's 500 at the commit, eight
   orphans) and its reproduction (an archived agent) both fall there. What remains after the commit
   is a dispatch refusal naming this entry, which for a new operator conversation means cases such
   as an agent with no row (`agent_trigger.py:676-687`), a runner with no execution adapter
   (`:731-738`, `:1170-1174`) or an argument refusal (`:650-656`).
3. **The archive path already exists and fits.** `spec_lifecycle.transition(..., to_phase=ARCHIVED,
   actor=operator)` permits `exploring -> archived` for a document with no requirements and no
   tasks (`spec_lifecycle.py:320-341`), and archiving is the operator's act, which this is, since
   the operator's own request is being answered. An archived document is left out of the spec
   tree's current view (`specNavigation.ts:53`, `:103-104`) and shown under *Archived* in the
   browser (`SpecDocumentBrowser.tsx:136-149`).

So `spec_service.retire_refused_exploration(session, workspace, document, *, reason)` calls
`transition` to `archived` with `_operator()` and the refusal's detail as the reason, then
`spec_service.rerender_phase(session, workspace, document)`, commits, and broadcasts
`spec_updated`: the same three steps, in the same order, as the operator's own `POST
/documents/phase` (`spec.py:1606-1629`). R3: without `rerender_phase` the row would say `archived`
while the file's visible status still said `exploring` (`rerender_phase`'s docstring,
`spec_service.py:788-813`: the file's metadata is a copy refreshed there). If `rerender_phase`
raises `OSError`, the phase is still committed, since the row is the authority, and the route
logs it. It does nothing, and returns `False`, unless the document is still `exploring`
and its only events are the `created` and content events this request wrote. `transition`'s own
guard already refuses a document with requirements or tasks. It is called in the F108 branch
**whether or not** `withdraw_refused_entry` returns `True`: `False` means the scheduler withdrew the
entry first (`inbound_queue.py:443-447`), and the route raises the refusal either way, so the
composer never learns the path in either case. If the transition itself raises, the route still
answers with the original refusal and logs the path.

The commit-failure branch removes only the file (the rows were never committed). That is not a
deletion of anything the Hub recorded.

**Reachability from the composer (R3).** The composer sends only `agent`, `message` and
`overrides` (`NewConversationSurface.tsx:98-106`), for an agent picked from its rows. Of
`trigger_agent_directly`'s request-level refusals (`agent_trigger.py`, every `request_level=True`):
the name check (`:656`) and the archived check (`:708`) are restated by the route before creation
(`:1415-1435`); the review and batching refusals (`:444`, `:459`, `:832-921`) need a review entry,
which D1 refuses; the `work_dir` refusals (`:930`, `:942`) need a `work_dir`, which the route also
checks first; and the two unsupported-runner refusals (`:738`, `:1173`) cannot fire, because a
runner's `cli` is validated against `RUNNER_CLIS = ("claude", "codex")` (`db/models.py:311`), both in
`SUPPORTED_RUNNERS` (`runner_commands.py:60`) and both built by `build_command`. That leaves an agent
with no row (`:676-687`), which the composer cannot name (no route deletes an `Agent` row), and an
agent **archived between the route's check and the dispatch** in the same request. So from the real
composer this branch fires only on that race; an API caller naming a non-existent agent reaches it
directly, which is how tasks 1.2/1.2b stage it. It is kept because it is cheap, it is correct for the
race, and a request-level refusal added to `trigger_agent_directly` later lands in it rather than
reopening F330 (the argument against pre-checking every refusal, below). F330's recorded case and
its reproduction are both closed by D1 and the commit compensation, not by this branch.

What the operator sees in that case: the composer's error with the refusal's sentence, their text
back in the box (`Composer.tsx:216-217`), no new document in the current tree, and the archived
placeholder under *Archived* in the browser. The conversation row this request committed stays,
with its entry withdrawn; that is F108's existing behaviour for every refused first send and is not
changed here.

**The residual, stated:** after a post-commit dispatch refusal the file stays under `spec/changes/`
and the row stays, archived. The operator is not shown it in the current tree. This is what
`:1891` already prescribes for a document created by mistake.

**Rejected: delete (R1's D3).** It needs MODIFIED deltas to two main-spec requirements, for a case
that is rare once D1 holds. It stays available if the operator wants the file gone too (D-B12-1,
option a).

**Rejected: pre-check every dispatch refusal in the route.** The route already mirrors three of
`trigger_agent_directly`'s guards; mirroring all of them is a second authority that drifts, and a
request-level refusal added later would silently reopen the gap.

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
- **R2 (2026-09-24):** D-B12-1 reversed to archive-after-commit (D3), because R1's delete removes
  append-only events. D1 gains the full refusal list and two more 400 conflicts. D2 gains the
  environment-level and unexpected-raise rows. The F108 branch retires the document whether or
  not this call withdrew the entry.
- **R3 (2026-09-24):** D3's retire now also calls `rerender_phase`, as the operator's phase route
  does, so the file does not keep showing `exploring`. D3 gains the reachability argument: from the
  real composer the archive branch fires only on an archive race; D1 and the commit compensation are
  what close F330's recorded cases. No decision changed.
