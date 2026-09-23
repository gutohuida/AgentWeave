# Design — a loop's outstanding mail is mail not yet delivered

**Built on the recommended answer to D6 for F259: retire the flag's authority. Neither delete the
flag nor start setting it.** Product decisions derive "outstanding" from the delivery the inbound
queue already records. The flag stays as the messages API's own bookkeeping, which
`agent-conversation-workspace` requires to remain unchanged. If the operator answers otherwise, see
D1 for what each alternative would change here.

## D1 — the three options

| | (a) Mark read on delivery | (b) Derive from delivery (recommended) | (c) Delete the flag |
|---|---|---|---|
| Write sites | `deliver_entries_with_run` sets `read`/`read_at`. `return_run_entries` must unset on requeue (`inbound_queue.py:225-295`) | none | none |
| Read sites | unchanged (3) | `scheduler.py` and `status.py` join `InboundQueueEntry` | the same two joins, plus `GET /messages`' default filter |
| Migration | a data backfill from `inbound_queue_entries` on the operator's live DB, which runs on `:8000`'s next restart | none | drop `read`, `read_at` and `ix_messages_project_read` (a SQLite table rebuild of `messages`) |
| Withdrawn or abandoned mail | stays "unread", so it is outstanding forever unless a third write site is added | not outstanding: its entry is `withdrawn` | same as (b) |
| Spec | agent-loops MODIFIED | agent-loops MODIFIED | agent-loops MODIFIED, plus agent-conversation-workspace MODIFIED (*"the messages API … MUST remain unchanged"*) |
| API | unchanged | unchanged | `PATCH /messages/{id}/read` removed, and the CLI transport's `archive_message` with it |

(a) keeps two stored facts for one event. They must be kept in step at every transition of the
entry, and there are four: deliver, requeue, withdraw, abandon. That is the stored-copy pattern this
codebase refuses (F97: *"a stored copy would outlive it"*, `inbound_queue.py:252-254`). The
timeline already derives its `delivery_state` from the entry instead (`agent_chat.py:210`). (c) is
the cleanest end state. It modifies a requirement written to keep that API unchanged, and it runs a
table-rebuild migration against `:8000` for a column that no longer harms anything once (b) is in.
**(b) removes every consequence F259 names, and it needs no migration and no API change.** (c) stays
available as a later, separate cleanup if the operator wants the column gone.

## D2 — the queries

```python
# scheduler._pending_loop_request, message branch
select(Message)
.join(InboundQueueEntry, InboundQueueEntry.message_id == Message.id)
.where(
    Message.project_id == job.project_id,
    Message.sender == job.agent,
    Message.recipient == creator_agent,
    InboundQueueEntry.state == "queued",
)
.order_by(Message.timestamp.desc())
```

```python
# status.py, message_counts.pending
select(func.count(Message.id)).select_from(Message)
.join(InboundQueueEntry, InboundQueueEntry.message_id == Message.id)
.where(Message.project_id == project_id, InboundQueueEntry.state == "queued")
```

- **An inner join**, deliberately. A message with no entry (pre-queue rows, the two `sender="hub"`
  rows) will never be delivered, so it is not outstanding and not pending.
- **One entry per message** (both creation sites, `new_entry(..., message_id=...)`), so the join
  cannot double-count. `count(Message.id)` rather than `count()` makes that assumption visible.
  `func.count(distinct(Message.id))` would hide a duplicate rather than count it. R2 should decide
  whether a duplicate should fail a test instead.
- `inbound_queue_entries.message_id` has no index (`models.py:611`). Both queries are bounded:
  the scheduler query by project, sender and recipient, and status by project. This runs once per
  empty-queue stop and once per status read. R1 adds no index, because an index would be a
  migration. R2 may measure.

**What each route returns when what it calls raises.** `GET /status` gathers seven queries with
`asyncio.gather` (`status.py:38`). If the join raises, the route returns 500, as any of the seven
already would. `_pending_loop_request` runs inside the firing's stop path
(`scheduler.py:3192`). Its caller's own exception handling is unchanged, so a failure there
behaves exactly as a failure in today's query does. The join adds no new kind of failure.

## D3 — what `pending` means to its reader

The only reader is Diagnostics' raw JSON (`DiagnosticsPanel.tsx`). The TS type
(`hub/ui/src/api/status.ts:10`) calls it `pending`. "Not yet delivered" is what *pending* means for
mail, so the field keeps its name. The dead `StatusBar.tsx:25` rendered it as `N msgs`, which is not
this change's concern (F260/F259 amendment).

## D4 — the interaction with the other D6 answers

- **F260 (delete the dead Messages screen)** removes `useMarkRead`, the flag's only UI writer. With
  (b), nothing in the product depended on that writer. With (a) or (c), the order of the two
  changes would matter. With (b) it does not.
- **F225 (loop controls)** does not touch `_pending_loop_request`. Both this change and
  `a-loop-is-stopped-archived-and-delegated-from-its-own-tab` add `agent-loops` deltas, on different
  requirements. Run the R-2 collision script at archive.
