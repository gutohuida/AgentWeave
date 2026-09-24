# Design — a loop's outstanding mail is mail not yet delivered

## Operator review, 2026-09-24

The Opus adversarial review found one defect, in a test rather than in the design. The operator
decided to fix it and approve the design otherwise unchanged.

- **Task 1.4 now seeds explicit timestamps.** As written, it relied on
  `order_by(Message.timestamp.desc())` (`scheduler.py:500`) without setting `timestamp`. The column
  defaults to `_now()` at insert (`hub/hub/db/models.py:537`), so two rows seeded together can tie
  or be ordered by accident, and the test would not prove the newest-first rule. The test now sets
  each `timestamp` several seconds apart, and it adds a third, older `queued` message so the
  assertion picks the newest qualifying message out of more than one candidate.

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

**R2 changed what "outstanding" means for the loop, and the query shape.** R1 counted a message as
outstanding only while its entry is `queued`. That drops a message **delivered into a creator turn
that is still running**. The creator is reading it right now and has not answered: it may be about
to add the work the loop is waiting for. That is the plainest case of *"a request still in flight"*,
the requirement's own title. So for the loop, a message is outstanding while its entry is `queued`,
**or** `delivered` into a run whose `status` is still `running` (`entry.delivered_in_run_id`,
indexed by `ix_inbound_queue_delivered_run`). `/status`'s `pending` stays *not yet delivered*
(`queued` only), which is what the word means there (D3).

```python
# scheduler._pending_loop_request, message branch
in_flight = (
    select(InboundQueueEntry.message_id)
    .outerjoin(Run, Run.id == InboundQueueEntry.delivered_in_run_id)
    .where(
        InboundQueueEntry.project_id == job.project_id,
        InboundQueueEntry.agent == creator_agent,
        InboundQueueEntry.message_id.is_not(None),
        or_(
            InboundQueueEntry.state == "queued",
            and_(InboundQueueEntry.state == "delivered", Run.status == "running"),
        ),
    )
)
select(Message).where(
    Message.project_id == job.project_id,
    Message.sender == job.agent,
    Message.recipient == creator_agent,
    Message.id.in_(in_flight),
).order_by(Message.timestamp.desc())
```

```python
# status.py, message_counts.pending
select(func.count()).select_from(Message).where(
    Message.project_id == project_id,
    Message.id.in_(
        select(InboundQueueEntry.message_id).where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.state == "queued",
            InboundQueueEntry.message_id.is_not(None),
        )
    ),
)
```

- **An uncorrelated `IN` subquery, not a join (R2).** This settles R1's duplicate question by
  construction. A message counts once however many entries name it, so there is no double count to
  hide or to test for. Today each message gets exactly one entry: the two creation sites are
  `messages.py:265-276` and `agents.py:2228-2236`, and they are the only `new_entry(...,
  message_id=...)` calls. Requeue and withdrawal change that entry's `state` in place
  (`inbound_queue.py:259-292`). So no duplicate test is planned.
- **A message with no entry** (pre-queue rows, the two `sender="hub"` rows) is in no subquery, so it
  is neither outstanding nor pending. It will never be delivered.
- **No index on `message_id` is needed, and no migration (R2).** The subquery is constrained on the
  entry side by `project_id`, `agent` and `state`. Those are the leading columns of the existing
  `ix_inbound_queue_project_agent_state_arrival (project_id, agent, state, sequence)`
  (`models.py:667-673`). For `/status`, `project_id` is a usable prefix. SQLite evaluates an
  uncorrelated `IN` once, into a temporary b-tree, and then probes `messages` by primary key. An
  index on `message_id` would help only a **correlated** `EXISTS` or a join driven from `messages`,
  and neither is planned. IMPL confirms the plan with one `EXPLAIN QUERY PLAN` on the trial DB, and
  records it in the task (task 3.3).

**What each route returns when what it calls raises.** `GET /status` gathers seven queries with
`asyncio.gather` (`status.py:38`). If the join raises, the route returns 500, as any of the seven
already would. `_pending_loop_request` runs inside the firing's stop path
(`scheduler.py:3192`). Its caller's own exception handling is unchanged, so a failure there
behaves exactly as a failure in today's query does. The subquery adds no new kind of failure.

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
