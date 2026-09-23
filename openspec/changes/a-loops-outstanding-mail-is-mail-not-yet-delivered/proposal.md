# Proposal — a loop's outstanding mail is mail not yet delivered

**Round 1, 2026-09-24** (bundle B10, decision D6, surface "the message-read flag"). Finding:
**F259 (B)**, re-verified on HEAD `404c7d5` (worktree `ce086b6`). **Nothing here is implemented
yet.**

## Why

`Message.read` is written in exactly one place, `PATCH /messages/{id}/read`
(`hub/hub/api/v1/messages.py:400-415`). Its only clients are `useMarkRead`
(`hub/ui/src/api/messages.ts:46`), used by the dead `MessageCard` (F260), and the CLI transport's
`archive_message` (`src/agentweave/transport/http.py:300-312`), which nothing in `src/` calls
(`grep -rn archive_message src/`: its definition and its abstract declaration only). **Nothing in the
product ever marks a message read.** The F259 measurement was 82 of 82 messages unread over ten
days.

Two product decisions read the flag anyway:

| Reader | What it decides | Effect of a flag nobody sets |
|---|---|---|
| `_pending_loop_request` (`hub/hub/scheduler.py:490-515`, `Message.read == False` at `:498`) | The `pending_request` recorded on `loop_queue_exhausted` when a loop stops on an empty queue (`agent-loops` *"An empty queue with a request still in flight…"*) | Every executor→creator message ever sent in the project qualifies. The newest is reported as *"outstanding"*, however long ago the creator received and answered it |
| `GET /status` `message_counts.pending` (`hub/hub/api/v1/status.py:42-46`) | The project's pending-mail count | Always equals `total`. Rendered raw in Settings → Diagnostics (`DiagnosticsPanel.tsx:8-10`, a JSON dump). F259's amendment says it reaches no screen, and this corrects that: it reaches one, raw |

F264's project filter (fixed 2026-09-22, `scheduler.py:493-495`) narrowed the first reader to one
project. It left the `read` predicate as dead as before, and F264's own foot says F259 is untouched.

**The Hub already records the fact these readers need.** Every message an agent or the operator
sends creates exactly one inbound queue entry carrying its `message_id` (`messages.py:265-276`;
`agents.py:2228-2236`). That entry's `state` is `queued` until `deliver_entries_with_run` moves it
to `delivered` (`hub/hub/inbound_queue.py:175-195`). `return_run_entries` puts it back to
`queued`, or ends it `withdrawn` (`:225-295`). The conversation timeline already derives each
message's `delivery_state` from exactly that (`hub/hub/api/v1/agent_chat.py:73`, `:210`).

The exceptions are the two `sender="hub"` rows written by `POST /agents/{name}/compact` and
`/new-session` (`agents.py:2979`, `:3016`). They get no entry, so nothing ever delivers them. Their
only clients are hooks that no component renders (the R-1 unrendered-hook list). Under this change
they correctly count as not pending, because they will never arrive. Under the flag they count as
pending forever.

## What changes

1. `_pending_loop_request`'s message branch counts a message as outstanding while its inbound
   entry is `queued`, or `delivered` into a creator run that is still `running` (R2: the creator is
   reading it and has not answered). This replaces `Message.read == False` with an `IN` subquery
   over `InboundQueueEntry` (design D2). The project filter and the newest-first order stay.
2. `GET /status`'s `message_counts.pending` counts messages whose entry is `queued`: mail not yet
   delivered.
3. `agent-loops`' requirement is MODIFIED to say what *outstanding* means (the delta), and to drop
   the word *unread*, which named a flag.

## What does not change

- **The messages API.** `Message.read`, `read_at`, `PATCH /messages/{id}/read` and
  `GET /messages`' default unread filter stay as they are. `agent-conversation-workspace`'s *"Agents
  and Messages are removed as navigation destinations"* says *"the messages API … MUST remain
  unchanged"* (`openspec/specs/agent-conversation-workspace/spec.md:162-179`). After this change the
  flag is only an API client's own bookkeeping. No product decision reads it.
- No migration. Nothing is backfilled: the entries already record every delivery, including past
  ones.

## Impact

- `hub/hub/scheduler.py` (`_pending_loop_request`), `hub/hub/api/v1/status.py`.
- `hub/tests/test_scheduler.py` (two tests restaged, two added), `hub/tests/test_status.py` (one
  added).
- Spec: `agent-loops`, one MODIFIED requirement.
