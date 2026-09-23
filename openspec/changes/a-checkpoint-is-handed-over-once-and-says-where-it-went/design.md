# Design — a checkpoint is handed over once, and says where it went

**Built on the recommended answers to B8's design questions D1–D6 below.** The bundle carries no
`DECISIONS.md` question; these are choices R1 made and the operator may overturn. If the operator
answers otherwise:

- **D2 answered "per checkpoint only":** drop the partial unique index (from task 2.1 and the
  migration), tasks 1.3, 1.4 and 1.12's index half, and D6. Also drop scenario *"A second checkpoint
  cannot hand the same conversation over again"*. F293 and F294 stay closed; the cross-checkpoint
  race stays open. (R3 corrected this line, which named task 2.3. Task 2.3 is the compare-and-set,
  and it stays under this answer.)
- **D3 answered "in-process claim":** replace the compare-and-set with an `asyncio.Lock`-guarded set
  like `_checkpoint_claims`. Drop the index. Rewrite the requirement's *"enforced by the database"*
  sentence.
- **D5 answered "no backfill":** delete task 3.2 and its tests. Record that legacy cutovers stay
  re-armable by unarchive.
- **D6 answered "generate anyway":** delete task 2.7 and task 1.8's decline assertions. The
  per-turn billed generation on a reopened, handed-over conversation is then accepted.

**Round 1, 2026-09-24. Nothing here is implemented yet.**

## Context — the code at `404c7d5`

`cut_over(db, predecessor, checkpoint, *, hop_depth, auto_continue)`
(`hub/hub/checkpoint_cutover.py:63`):

| Line | What it does |
|---|---|
| `:83-87` | Refuses unless `checkpoint.status == "ready"`. A cutover does not change the status, so a spent checkpoint passes |
| `:97-103` | **F126's guard.** Refuses when `predecessor.lifecycle == "archived"`, with the text *"…if it was archived by hand, unarchive it first."* |
| `:105-107` | `archivable(db, predecessor)`: a run in progress or undelivered entries refuse |
| `:109-131` | Builds the successor (`origin="handoff"`, derived title, inherited overrides, bindings, `lineage_id`) and `db.add`s it |
| `:133-142` | Builds the `InboundQueueEntry` (`origin_type="checkpoint"`, `content=delivery_content(checkpoint)`, addressed to the successor) |
| `:144-145` | `archive(predecessor)`; `await db.commit()` |
| `:149-198` | `auto_continue`: `schedule_agent` after the commit |

Callers (the only two, `grep -rn "cut_over(" hub/hub`):

- **The route** `POST /projects/{p}/checkpoints/{id}/cutover` (`hub/hub/api/v1/checkpoints.py:370-404`).
  It turns `CutoverRefusedError` into **409** (`:391-394`). Any other exception propagates as 500.
  Nothing is pending on its session before the call: it only reads (`:378-384`).
- **The automatic trigger** (`hub/hub/checkpoint_trigger.py:319-336`). It turns `CutoverRefusedError`
  into `payload["cutover_refused"]` on a `checkpoint_ready` broadcast. Any other exception reaches
  `_run`'s `except Exception` (`:376-377`), which logs a warning. Nothing is pending on its session
  before the call either: `generate_checkpoint` commits at `checkpoint_generation.py:604`, and
  when it probes, `probe_checkpoint` commits at `:639` and then either returns with nothing
  changed (the probe did not run) or commits again at `:664`. `:291-317` only builds a dict, from
  plain values read before `cut_over`. The trigger never reaches `cut_over` for a conversation
  that is not `open`: `consider` declines it at `checkpoint_trigger.py:187-190`.
- **No third path** (R3, `grep -rn "cut_over\|cutover" hub/hub src`). `mcp_server.py` has no
  cutover tool, and `checkpoint_handover.py` (flows) never cuts over. The route's `get_project`
  accepts only an `aw_live_` operator credential (`auth.py:88-105, 134-159`), so no agent's run
  credential can reach it. The UI reaches it only through `api/checkpoints.ts:86`, which Handoff
  (`writeCheckpoint`) and the cutover banner call.

`unarchive` (`hub/hub/conversations.py:479-482`) sets `lifecycle = "open"` and `archived_at = None`.
Its route (`hub/hub/api/v1/agent_chat.py:623-635`) is never refused.

`Checkpoint` (`hub/hub/db/models.py:1668-1804`) has no column recording a handover.
`InboundQueueEntry` has no checkpoint id either. The only durable link today is inside the entry's
`content`. `delivery_content` = `_DELIVERY_PREAMBLE` (`checkpoint_cutover.py:28-36`, which opens
*"This conversation continues earlier work."*) + `render_checkpoint`, whose first line is
`# Checkpoint {checkpoint.id}` (`checkpoint_generation.py:285`). Checkpoint notes requests share
`origin_type="checkpoint"` (`checkpoint_trigger.py:237-246`), but their content is `_NOTES_REQUEST`,
which does not open with the preamble. Nothing in `hub/hub` deletes an `InboundQueueEntry`, a
`Checkpoint` or a `Conversation` (`grep` for `delete(` over all three: no hits).

## Measured in R1 (HEAD `404c7d5`)

A throwaway test (created under `hub/tests/`, run with `-s`, then deleted) used the suite's own
fixtures (`_conversation`, `_ready_checkpoint` from `test_checkpoint_cutover.py`) on the suite's
file-backed SQLite:

- **F293:** `cut_over` → `unarchive` + commit → `cut_over` with the same checkpoint. Result:
  **two** `handoff` successors (`conv-2997cf6e3357`, `conv-2ecad0277068`). Still open.
- **F294:** two sessions, each loads the conversation and checkpoint, then an `asyncio.Barrier(2)`,
  then `cut_over` concurrently. Result: **both** returned successors
  (`conv-9433b9e6954f`, `conv-e632a122f613`). Still open. Without the barrier the second press read
  after the first commit and was refused. The barrier is what makes the test deterministic, so
  task 1.2 keeps it.
- Read-only (`mode=ro`) on the operator's `:8000` database (`~/.agentweave/hub/data/agentweave.db`,
  head `0105`): 16 checkpoints, 8 ready, **0** `origin_type='checkpoint'` entries, **0** `handoff`
  conversations. The trial database: 0 checkpoints. The backfill writes nothing on either.

## History — the three asks, and why none landed

1. **F126, 2026-08-30** (`b039d47`, row 15's cutover drive). Shape (2) was recommended: *"Give
   `Checkpoint` a `cut_over_to_conversation_id` … One migration."* The night of 2026-09-06 shipped
   shape (1) in `3142a91` instead, the lifecycle guard. Its fix note gives two reasons. A migration
   *"fails the day-window carve-out's second condition"*, so an unattended window may not make it.
   And shape (1) as worded (*"a queue entry that names this checkpoint"*) needed the very link
   shape (2) adds. The shipped guard is a proxy, and the note flags it as *"wider than the finding
   asked for"*.
2. **F293, 2026-09-06 D-2** (`6f58c27`). Recommendation (1) was *"Shape (2) from F126, now with a
   second reason."* F294 in the same drive showed the column alone races too. The night's closing
   log (`523e66d`) carried *"F293 + F294 want one change between them … Neither is specced."*
   Nothing specced it: `git log --all --grep "F293\|F294"` finds no proposal commit. The recorded
   reasons are these. The drain (`DECISIONS.md:1519`) does cover B, but the night playbook works
   severity A first, and five A's were unproposed that night (`523e66d`). A finding with no
   proposal needs a day window first, and the drain's FILL proposed As ahead of it. From 2026-09-22
   the Merge Week O5 froze new change directories until 2026-09-28 (`ROUNDS.md` §"Read this first"
   2). R1 found no record of a window that considered F293/F294 and declined them. The finding was
   simply never reached.
3. **`ROUNDS.md` S2, 2026-09-22** (`eeadf70`) scheduled it as a spec track from 2026-09-28. This
   bundle is that track.

The pattern: every time, the migration was the reason a window could not act. This change is the
migration, done in an interactive session under the round discipline.

## Decisions

### D1 — Where the handover identity lives: on the checkpoint

Options:

- **(a) `Checkpoint.cut_over_to_conversation_id`** (recommended). The row the operator already
  reads (`CheckpointSummary`) answers *"where did this checkpoint go"*. It is the column the ledger
  asked for three times.
- **(b) `Conversation.handed_over_by_checkpoint_id`** on the successor. The successor→predecessor
  direction is already answerable through `lineage_id` and `origin="handoff"`. Only the checkpoint
  is missing, and putting it on the conversation leaves the checkpoint listing unable to say it is
  spent. It would also widen `ConversationResponse`, which the whole navigation tree consumes.

Column: `String(64)`, nullable, **no `ForeignKey`**. SQLite does not enforce foreign keys here (no
`PRAGMA foreign_keys` in `hub/hub/db/engine.py`). Adding a constraint to `checkpoints` on SQLite
means a batch rebuild of a table whose constraint names `0088` pinned deliberately
(`models.py:1686-1693`). The value is written only by `cut_over`, from a successor it created in
the same transaction.

### D2 — "At most once" is per conversation, not only per checkpoint

Options:

- **(a) Per checkpoint only.** A second cutover of the *same* checkpoint is refused. A *different*
  checkpoint of the same conversation can still mint a second successor.
- **(b) Per conversation** (recommended): a partial unique index
  `ix_checkpoints_one_handover_per_conversation` on `checkpoints(conversation_id) WHERE
  cut_over_to_conversation_id IS NOT NULL`.

(a) leaves two real routes open. The first is **sequential**: cut over with C1, unarchive, keep
working, take C2, cut over again. That gives two open successors on one `lineage_id`, the fork
`conversation-checkpoint`'s *"Lineage is recorded and participation is derived"* rules out
(*"Lineage is linear"*). The second is **concurrent**, and it reaches the product with no unarchive
at all. When the automatic trigger's cutover is refused (a run in progress), it broadcasts
`checkpoint_ready` with `cutover_refused` (`checkpoint_trigger.py:327-333`). The UI then offers C1
to the operator. The next context reading can generate C2 and cut over automatically, while the
operator presses C1. Both read the predecessor as `open`. A claim on the checkpoint row cannot see
the other row.

**The app's own Handoff button always takes route one.** `writeCheckpoint`
(`hub/ui/src/store/checkpointOperationStore.ts:37-75`) calls `takeCheckpoint` and then cuts over
*that new* checkpoint. So an operator who unarchives a handed-over conversation and presses Handoff
again never re-presses the spent checkpoint. They press a fresh one. Under (a), F293's outcome (a
second successor on one line) stays reachable from the UI with one click. Only the API re-press
and the `context_pressure` banner would be closed. That alone decides (a) against.

(b) releases one thing (a) would allow: after an unarchive, a conversation cannot be handed over
again by a new checkpoint. The operator keeps working in the reopened predecessor or in its
successor. The refusal names the successor. That matches the lineage requirement, so R1
recommends it.

A cutover of the *successor* is unaffected: its checkpoints carry its own `conversation_id`.
Driven chains (F294's *"What held"*: a two-hop chain) keep working, and task 1.6 pins that.

### D3 — Serialisation is done by the database, not by a process-local claim

Options:

- **(a) An in-process claim** like `_checkpoint_claims` (F294's own recommendation). It needs no
  migration, but it guarantees nothing across processes, and it keys on the checkpoint or on the
  conversation, not on both.
- **(b) Compare-and-set plus the D2 index** (recommended). `UPDATE checkpoints SET
  cut_over_to_conversation_id = :successor WHERE id = :id AND cut_over_to_conversation_id IS NULL`,
  with rowcount 1 required. This is the "row claim" `ROUNDS.md` S2 names. The D2 index is the
  backstop for the cross-checkpoint race. Migration `0104` already follows this pattern
  (`ix_questions_open_subject_key`: *"the database refuses the second insert instead of a `SELECT`
  racing it"*), and so does its handler (`hub/hub/refused_capability.py:216-230`: catch
  `IntegrityError`, roll back, re-read, answer).

The migration is needed for the column anyway, and the column is where a claim can be recorded
durably, so (b) costs nothing (a) saves. The claim is the column written conditionally, not an
extra field that another request can read and race on. That is the gap F294 named in *"the column
alone races identically"*.

**Why this serialises on the Hub's SQLite.** `engine.py:36-40` sets no pragmas and no isolation
level, so pysqlite runs in legacy transaction mode. It emits `BEGIN` implicitly before the first
DML, not before a `SELECT`, and the reads in `cut_over` hold no snapshot. The first flushed `INSERT`
takes the write lock. A concurrent second request's `INSERT` waits on the busy handler (5 s default)
until the first commits. Its compare-and-set then evaluates against the committed row and matches
nothing. R1 checked this against the code, not against a live run. **Task 1.2 is the measurement**:
if SQLite answers `database is locked` instead of waiting, the test fails with an
`OperationalError`, and IMPL must stop and report rather than widen the catch.

**Measured in R2 (2026-09-24), in both journal modes.** The suite does not run the journal mode
production runs. `hub/tests/conftest.py:112-115` sets `journal_mode=WAL` and `busy_timeout=30000`
on every test connection, "production keeps SQLite's defaults". The operator's database reads
`journal_mode = delete` (read with `mode=ro`), and a connection built with `engine.py:36-40`'s
arguments reads `busy_timeout = 5000`. So task 1.2 alone measures WAL, not production. R2 ran the
real `cut_over` through a session proxy. The proxy's `commit` did step 2's flush, a raw
compare-and-set against a column and partial index added by DDL, and then steps 3–5. Each scenario
ran five times, under the suite's WAL/30 s and on a separate engine with SQLite's defaults
(rollback journal, 5 s):

| Scenario | WAL / 30 s | rollback journal / 5 s |
|---|---|---|
| Same checkpoint, barrier (task 1.2) | 5/5: one success, one compare-and-set miss; 1 successor, 1 entry | 5/5, same |
| Two checkpoints, barrier (task 1.4) | 5/5: one success, one `IntegrityError` → refusal; 1 successor, 1 entry | 5/5, same |
| Any `OperationalError` | none | none |

The loser waited 15–46 ms, which is the busy handler working and not failing. The argument holds
in both modes. Task 1.11 keeps the production-mode run as a test.

**What R2 found that R1 did not: a rollback expires every instance in the session.** In all 20
refusals, reading `checkpoint.id` on the caller's instance after the rollback raised
`MissingGreenlet`. That is an async lazy load of an expired attribute. Two places read ids after
step 3's or step 4's rollback:

- `cut_over`'s own refusal text and re-read (`checkpoint.id`, `predecessor.id`). If these are
  read after the rollback, the route answers **500, not 409**. Tasks 1.2, 1.4 and 1.10 would catch
  that.
- The trigger's `return checkpoint.id` at `checkpoint_trigger.py:332`, in its
  `except CutoverRefusedError` branch. It runs *after* the `checkpoint_ready` broadcast, so the
  operator still sees the event. `consider` then raises instead of returning, and `_run`
  (`:376-377`) logs *"checkpoint consideration failed"*, a false alarm on every such refusal. Only
  task 1.8 reaches it, and only if the test asserts the return value.

So step 0 below captures the ids before any write. `refused_capability.py:216-230` does the same
thing: its re-read after the rollback uses `project_id` and `gate.subject_key`, which are plain
values, never an ORM instance.

Order inside `cut_over`, after the pre-checks:

0. Capture `checkpoint_id = checkpoint.id`, `predecessor_id = predecessor.id` and
   `conversation_id = checkpoint.conversation_id` as plain strings. After a rollback, use only
   these.
1. `db.add(successor)`, `db.add(entry)`, `archive(predecessor)` (as today).
2. `await db.execute(update(Checkpoint)…compare-and-set…)`. The ORM autoflushes 1 first, so the
   `INSERT`s take the lock before the claim is evaluated.
3. rowcount 0 → `await db.rollback()`, re-read the checkpoint, and raise `CutoverRefusedError`
   naming its `cut_over_to_conversation_id`.
4. `IntegrityError` from 2 or from the commit → `await db.rollback()`, re-read the conversation's
   handed-over checkpoint, and raise `CutoverRefusedError` naming its successor and its checkpoint.
5. `await db.commit()`.

**R3 additions to the order (2026-09-24):**

- Step 2 is preceded by an explicit `await db.flush()`. The ORM `update(Checkpoint)` does
  autoflush today (SQLAlchemy 2.0.50, `BulkUDCompileState` with `_autoflush = True`), but the
  lock order D3 depends on should not rest on the statement staying ORM-enabled: a Core or
  `text()` UPDATE skips the autoflush, and then the claim is evaluated before this request holds
  the write lock.
- Step 4's re-read may find **no** handed-over checkpoint for the conversation. The
  `IntegrityError` then came from some other constraint, not from the D2 index. In that case
  `cut_over` re-raises the original `IntegrityError` (the route answers 500, the trigger's `_run`
  logs it). It never builds a refusal naming `None`.
- **Which refusals roll back.** Only steps 3 and 4 do, and only a race reaches them. Every
  sequential refusal (spent checkpoint, handed over by another checkpoint, archived by hand,
  `archivable`, not ready) is raised by task 2.2's pre-checks **before any write**, so the
  session is never rolled back and nothing expires. A sequential test therefore cannot catch
  a missing step 0 or a missing task 2.6. Only a race can, which is why task 1.12 exists.

Rolling back is safe for both callers because neither has anything pending (see *Context*). IMPL
adds a comment at the rollback saying so. A future caller that stages changes before `cut_over` would
otherwise lose them silently. The comment also says that the caller's instances come back
**expired**. The trigger's `except CutoverRefusedError` branch therefore returns an id captured
before the call, not `checkpoint.id` (task 2.6).

### D4 — The hand-archived refusal stays, and becomes honest

F126's guard also refuses a conversation archived by hand. Its fix note flagged this as a widening
that *"if the operator wants the narrower rule … needs shape (2)'s column"*. With the column, the
narrower rule is possible. R1 recommends keeping the refusal anyway. Allowing it would skip
`archivable`, whose first line returns `None` for an archived conversation
(`conversations.py:395-396`). A cutover would then run with no check
for an in-progress run or stranded entries. The remedy is also one press.

What changes is the order and the wording. The spent-checkpoint and handed-over checks run
**first**, so *"unarchive it first"* is said only to a conversation that was never handed over,
where following it is correct.

Refusal texts (IMPL may polish them; the tests assert the ids and key phrases only):

- Spent checkpoint: *"Checkpoint {id} was already cut over to {successor}; that conversation holds
  the work."*
- Conversation already handed over by another checkpoint: *"Conversation {pred} was already handed
  over to {successor} (checkpoint {other}); continue there, or keep working in this one."*
- Archived by hand, never handed over: today's text with the *"if this one was cut over already…"*
  clause dropped, since that case is now named precisely above.

### D5 — Backfill the column from delivered entries

For each `inbound_queue_entries` row with `origin_type = 'checkpoint'` whose `content` starts with
`This conversation continues earlier work.`, parse `^# Checkpoint (ckpt-\S+)$` (multiline), in
`sequence` order. Set that checkpoint's `cut_over_to_conversation_id` to the entry's
`conversation_id` (the successor), but only where it is still NULL **and** no other checkpoint
whose own `checkpoints.conversation_id` (the predecessor) equals this checkpoint's has been set
yet. That is the index's key. The entry's `conversation_id` is the successor, so keying on it would
never find a collision. The first handover wins. Later duplicates from the F126/F293/F294
era stay NULL, so the unique index can be created on a database that already holds a fork. The
migration logs how many it set and how many it skipped. The preamble's opening line is unchanged
since it was introduced (`git log -S "This conversation continues earlier work" -- hub/hub` → only
`5706285`).

Without the backfill, a legacy cutover stays protected only by the lifecycle guard, and unarchiving
it re-arms F293 for that row. The link is exact, not heuristic, because the checkpoint id is in the
delivered text. R1 therefore recommends the backfill, even though it writes zero rows on both local
databases today.

### D6 — The automatic trigger does not spend a checkpoint on a conversation it cannot hand over (R3)

D2 (b) creates a state that did not exist before: an **open** conversation that can never be handed
over again (handed over, then reopened). `consider` does not know that. Under `automatic`, every
run in it that ends past the threshold leaves `_nothing_new_since_last_checkpoint`
(`checkpoint_trigger.py:111-136`) false, so the next reading calls `generate_checkpoint`, which is a
billed model call plus a billed probe (`checkpoint_generation.py:552, 641`). Then `cut_over`
refuses. The result is one wasted generation per turn, for as long as the operator keeps working
there. Today the same state costs one generation and produces a fork. After this change, without
D6, it costs one generation per turn and produces a refusal each time.

Options:

- **(a) Decline in `consider`** (recommended). Right after the `lifecycle != "open"` decline
  (`:187-190`), check whether any checkpoint of this conversation has
  `cut_over_to_conversation_id IS NOT NULL`. If one does, `_declined(conversation_id, "already
  handed over to {successor}; its line continues there")` and return `None`. That covers every
  branch after it: notes request, `offered` warning, final warning and automatic generation. Each
  of them ends in a handover that D2 now forbids.
- **(b) Generate anyway**, keeping the checkpoint as a record. The operator pays each turn for a
  record nobody asked for, and receives a `checkpoint_ready` event with `cutover_refused` each turn.
- **(c) Decline only the automatic generation**, and keep the `offered` warnings. The warning's only
  action is Handoff, and `writeCheckpoint` would take a billed checkpoint and then get a 409.

The operator can still take a checkpoint by hand (`POST …/checkpoint` is not gated). Only the
trigger stops offering a handover it can no longer perform. The race case is still covered: a
handover can commit between this check and `cut_over`, for example an operator pressing Handoff
during the ~19 s generation. In that case `cut_over`'s claim or index refuses (task 1.12).

A related cost remains, and it is not fixed here. The app's Handoff on such a conversation still
takes a new, billed checkpoint before it receives the 409. The UI could read
`cut_over_to_conversation_id` and not offer Handoff. That is a UI change, left out as the banner
filter is (proposal *Out of scope*).

## Migration `0106` — the checklist (`.claude/rules/db-migrations.md`)

1. **Model** — `Checkpoint.cut_over_to_conversation_id: Mapped[Optional[str]] =
   mapped_column(String(64), nullable=True)`. Add
   `Index("ix_checkpoints_one_handover_per_conversation", "conversation_id", unique=True,
   sqlite_where=text("cut_over_to_conversation_id IS NOT NULL"))` to `__table_args__`. Use the same
   name and predicate text as the migration: the F329 parity test
   (`test_an_empty_database_migrated_alone_gets_the_schema_init_db_builds`,
   `test_migrations.py:3669`) compares `create_all`+alembic against alembic+`create_all` DDL clause
   for clause.
2. **Migration** `hub/hub/migrations/versions/0106_checkpoint_cut_over_to.py`, `down_revision =
   "0105"`. Guard for a missing `checkpoints` table (return early, like `0104`'s `_columns`). Then
   add the column if absent, backfill (D5; skip it if `inbound_queue_entries` is absent), and
   create the index if absent. **Downgrade**: drop the index, then the column, both guarded.
   **Renumber at IMPL** to the next free number. **Three** other unarchived changes also name
   `0106` (R2 found two, R3 a third: `a-footprint-names-the-line-of-work-its-commit-is-on`,
   `design.md:49`, `tasks.md:29`). `agents-no-longer-register-themselves` (B3)
   gives it as *"next free number at IMPL time"* (`proposal.md:73`), and
   `worker-spend-counts-against-the-budget` gives it at `proposal.md:42,79`. The number in this
   document is not renumbered now. Whichever change is built second takes `0107`, and the third
   takes `0108`, the fourth `0109`. That includes the `HEAD_REVISION` bumps and every test name here that says `0106`.
3. **Heads** — `HEAD_REVISION = "0106"` (`hub/tests/test_migrations.py:40`) and
   `hub/tests/test_project_persistence.py:227`.
4. **Schema** — `CheckpointSummary.cut_over_to_conversation_id: Optional[str] = None`
   (`api/v1/checkpoints.py:31-71`), set in `.of`. The UI does not need it for this change. It is
   exposed because *"where did this checkpoint go"* is the question the column exists to answer.
   No UI bundle.

**This migration reaches the operator's live database on their next `:8000` restart.** It adds one
nullable column and one partial index, and backfills zero rows (measured, see above).

## What each route returns when the function it calls raises

- `POST …/checkpoints/{id}/cutover` → `cut_over` raises `CutoverRefusedError` for every refusal,
  old and new. The compare-and-set miss and the `IntegrityError` are converted **inside**
  `cut_over`, after a rollback. The route answers **409** with the text, unchanged at `:391-394`.
  An `OperationalError` (lock timeout) is not converted and stays a 500. That is unchanged, and R1
  does not widen it: a 500 there is a real fault, not a refusal.
- `checkpoint_trigger.consider` → a refusal becomes `cutover_refused` on `checkpoint_ready`
  (unchanged). The checkpoint row the trigger generated is already committed (`generate_checkpoint`,
  `checkpoint_generation.py:604`, and `:639`/`:664` when probed), so `cut_over`'s rollback cannot
  remove it. Task 1.12 pins that.
  The rollback does expire the trigger's `checkpoint` instance, though. Unless task 2.6 is done,
  `return checkpoint.id` (`:332`) raises `MissingGreenlet` after the broadcast has gone out, and
  `_run` logs a false *"checkpoint consideration failed"* (R2, measured; see D3). **R3:** only a
  race reaches that rollback. A trigger refused sequentially is refused by task 2.2's pre-check
  before any write, and with D6 it does not reach `cut_over` at all. So task 1.12 (the race) is the
  only test that catches a missing task 2.6. R2's version of task 1.8 was sequential and would
  have passed without 2.6.
- **Every path, on an unexpected exception** (R3). Anything `cut_over` does not convert propagates.
  An `OperationalError` from a lock timeout, an `IntegrityError` that D3 step 4's re-read cannot
  attribute, and a failure inside `auto_continue` after the commit are examples. The route answers
  500, and `get_session`'s context exit rolls the session back (`engine.py:166-169`). In the
  trigger, `consider` raises, the session's `async with` rolls back, and `_run` logs *"checkpoint
  consideration failed"*. No `checkpoint_ready` event is sent, so the generated checkpoint exists
  but nothing announces it. That is today's behaviour for the same exceptions, and this change does
  not widen it. The one exception that is new is the `auto_continue` case: it follows a successful
  commit, so the handover has happened even though the caller sees a failure. That is also
  unchanged from today.
- `GET …/conversations/{id}/checkpoints`, `POST …/checkpoint`, `GET …/checkpoints/{id}` → only
  `CheckpointSummary.of` changes, and it reads a column. Nothing new can raise.

## Open questions

0. D6 (R3): should a reopened conversation that was already handed over still receive checkpoint
   warnings and automatic generation? R3 recommends no (D6 (a)). See D6 for what each other answer
   costs.

1. D2 (b) refuses re-handover of a reopened conversation by a new checkpoint. If the operator
   considers *"reopen and hand over again"* a workflow they use, the answer is D2 (a) plus a
   separate decision about forks. R1 found no drive or finding that exercises it.
2. The route's 409 `detail` stays a string. A structured `{successor_conversation_id}` field would
   let a client link to the successor. No client needs it today, so R1 leaves it out.

## Round log

- **R1 (2026-09-24)**: this document. F293 and F294 re-measured as still open on `404c7d5`.
- **R2 (2026-09-24)**: re-derived against the code at `aaa8757`. F293 and F294 were reproduced
  again: two successors each. D3's locking argument was measured in both journal modes and holds
  (20 of 20 races clean). Three things were added. The suite runs WAL, not production's rollback
  journal (task 1.11). A rollback expires the caller's instances (D3 step 0, task 2.6, and task
  1.8's return-value assertion). And D5's first-wins key is the predecessor. A third change also
  names `0106`. No decision was reversed.
- **R3 (2026-09-24)**: re-derived every path to `cut_over`. There are two callers and no MCP or
  agent path. Five things were added:
  1. **D6.** The trigger declines before generating on a conversation it can no longer hand over.
     Without it, D2 (b) turns a reopened, handed-over conversation into one billed generation per
     turn.
  2. **Task 1.8 was sequential,** so its refusal fired before any write, with no rollback and no
     expiry. It could not catch a missing task 2.6. Task 1.8 now pins D6. The new task 1.12 reaches
     the rollback through a deterministic race.
  3. D3 step 2 is now preceded by an explicit `flush()`.
  4. D3 step 4 re-raises an `IntegrityError` it cannot attribute.
  5. A **fourth** unarchived change names `0106`: `a-footprint-names-the-line-of-work-its-commit-is-on`.

  The D2-answer line in the header was also corrected. D1–D5 stand.
