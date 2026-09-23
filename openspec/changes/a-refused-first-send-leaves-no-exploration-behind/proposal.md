# A refused first send leaves no exploration behind

## Why

**F330 (C).** An operator can arm "explore" on the new-conversation composer. When they do,
`NewConversationSurface.tsx` makes two requests (`hub/ui/src/components/agents/NewConversationSurface.tsx:83-107`):

1. `POST /project/documents` (`hub/hub/api/v1/spec.py:1419-1467`). This mints a placeholder path,
   creates the `spec_documents` row and its `created` event, **writes the file** under `spec/`
   through `spec_service.save_document` (`hub/hub/spec_service.py:238`), and commits.
2. `POST /agent/trigger` (`hub/hub/api/v1/agent_trigger.py:1405`), with `spec_document` set to that
   path.

The order is deliberate. The first turn has to carry the document, as the comment at `:72-80`
explains. But when step 2 is refused, nothing removes what step 1 made (`:110-117` only sets the
error and throws). Each retry mints another placeholder. F329 produced eight of them in
`LoopEngine/spec/changes/` (`emerald-fenrir`, `silver-thunderbird`, …): each is an empty `exploring`
document, both in the repository and in the spec list, for turns that never ran.

Step 2 can be refused in three ways:

- **A route-level refusal before anything is queued**: an archived agent (`:1428-1435`), an
  unavailable workspace (`:1437-1440`), an invalid `work_dir` (`:1442-1457`), a closed conversation
  (`:1461-1476`), or overrides with no runner or invalid values (`:1537-1556`).
- **A dispatch refusal that names this request's entry** (F108, `:1613-1641`). The entry is
  withdrawn and the route answers with the refusal's status.
- **An unexpected failure**, such as F329's 500 at the commit, or the network.

Deleting a document is not something the product otherwise does. *A document that produced nothing
can be archived* (`openspec/specs/spec-document-authority/spec.md:1891`) routes retirement through
the phase machine on purpose. But a document created for a send that was refused never had a
subject, a reader or a turn. The cleanest fix is for that document never to be committed by a request
that is refused before committing, and to be archived through its phase, not deleted, by one refused
after (R2; design D3).

## What Changes

- **`POST /agent/trigger` creates the exploration itself.** `TriggerAgentRequest` gains
  `start_exploration: bool`, which cannot be combined with `spec_document`. The route creates the
  document only after every route-level refusal has passed, in the **same transaction** as the
  conversation and the queue entry. The entry carries the new path as its `spec_document`. The
  response returns that path as `spec_document`.
- **A refusal after that point leaves nothing new in the current view, and deletes nothing that
  was recorded** (R2's answer to D-B12-1). If the commit fails, the rows roll back and the file the
  request wrote is removed before the error propagates. If the dispatch refusal names this entry
  (the F108 path), the route **archives** the document it created in this request, through the
  phase machine, as the operator's act with the refusal as its reason, and broadcasts
  `spec_updated`. It does so only while the document is still `exploring` with no event besides
  the ones this request wrote. The archived document leaves the spec tree's current view; its file
  stays under `spec/`. R1 proposed deleting the row, its events and its file instead; that removes
  append-only history, which the main spec forbids (design D3).
- **If the document cannot be created, the send is refused** (recommended answer to D-B12-2), with
  the reason, such as `naming_exhausted`. The composer already puts the operator's text back on a
  refusal (`hub/ui/src/components/agents/Composer.tsx:216-217`), so nothing typed is lost. Today
  the turn is sent without a document, which is the very symptom the explore control was added to
  prevent (`NewConversationSurface.tsx:72-76`).
- **The composer makes one request.** `NewConversationSurface` stops calling `POST
  /project/documents`. It sends `start_exploration: true` and reads `spec_document` from the
  response.
- Out of scope: input that was **queued**, answered `200`, and later given up by the scheduler after
  three delivery attempts (`turn_scheduler.py:596-608`). The operator was told it was accepted, and
  the document is theirs to archive through the existing phase route. This is named in the spec as
  outside the guarantee.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-composer`: adds *An exploration started with a conversation exists only if that
  conversation's first input was accepted*.

## Impact

- `hub/hub/api/v1/agent_trigger.py`: `TriggerAgentRequest`, `TriggerAgentResponse` (a new optional
  `spec_document`), and `trigger_agent`.
- `hub/hub/spec_service.py`: `start_exploration(...)` (the mint, create and save sequence, moved
  out of `POST /project/documents` and shared) and `retire_refused_exploration(session, document,
  *, reason)`, which archives through `spec_lifecycle.transition`. No code path deletes a document
  row or event.
- `hub/ui/src/components/agents/NewConversationSurface.tsx` and its test. This is a UI bundle, so
  `make ui` is needed and `hub/ui/src` and `hub/hub/static/ui` are committed together. **A
  committed bundle reaches `:8000` on its next reload.** The composer change must not ship before
  the route change is running there. See design D5.
- No migration. No MCP change.
