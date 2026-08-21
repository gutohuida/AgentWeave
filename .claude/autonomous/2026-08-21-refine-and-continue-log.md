# 2026-08-21/22 overnight — refine and continue

## Iteration 1 — 2026-08-21T23:26:30+01:00 — C1: conversations-continue phase 1

**Branch state on entry.** `master` was at `2bc7ba1` (a correction commit that fixed
`parent_sha` in STATE.json from `f1d6c08` to `aa12ba7`, landed directly on master by the prep
session rather than on the autonomous branch — that is correct: prep runs interactively on
master before the branch exists). The autonomous branch itself did not exist yet, locally or on
the remote. Two untracked handoff files (`0071`, `0072`) were sitting on disk, never staged.

Cut `autonomous/2026-08-21-refine-and-continue` from `master` at `2bc7ba1` (current HEAD, not
the `f1d6c08` or `aa12ba7` named earlier in STATE.json — both predate the correction commit and
would have missed it). Committed the two stray handoffs on the new branch first, so the tree
started clean, then pushed with `-u`.

**C1 — the line of work.** Read `proposal.md`, `design.md`, `tasks.md` in full. Followed
design.md D3 exactly: `lineage_id`, not a predecessor pointer.

- `hub/tests/test_migrations.py::test_migration_0085_adds_lineage_id` written first, upgrading
  a synthetic 0034-era database (`_create_0034_conversations_state`, one row `conv-existing`)
  to head and asserting: `lineage_id` column present, backfilled to `conv-existing` for the
  existing row, `ix_conversations_lineage_id` present, and a downgrade to `0084` drops the
  column while leaving the row intact.
- `Conversation.lineage_id` added in `hub/hub/db/models.py` — `String(64), nullable=True,
  index=True`. Nullable at the DB layer deliberately, matching this codebase's existing
  convention for columns that are always-set-in-practice-but-not-DB-enforced (`task_id`,
  `bound_sender_conversation_id`, `color_index` backfilled by `0016`) — avoids a batch-recreate
  just to flip a NOT NULL that nothing in this phase needs enforced yet.
  design.md doesn't ask for a NOT NULL constraint either, only for the backfill.
- `hub/hub/migrations/versions/0085_conversation_lineage.py` — add column, backfill
  `lineage_id = id` for any NULL row, create the index. Guarded via `_columns()` returning
  `None` when `conversations` doesn't exist yet, same shape as `0033`/`0034`/`0041`. Modelled
  directly on `0016`'s add-column-then-backfill-then-index shape (0041's column-add is the same
  shape too) rather than a `batch_alter_table(recreate=...)` — no CHECK constraint or primary
  key is touched, so no recreate is needed.
- `HEAD_REVISION` bumped to `"0085"` in `test_migrations.py`, and the head assertion in
  `test_project_persistence.py` (`assert version == "0085"`).
- `new_conversation()` in `hub/hub/conversations.py` now sets `lineage_id=conversation_id` at
  construction — its own id, matching design.md's "own lineage until a checkpoint cutover says
  otherwise."
- Re-swept the 8 call sites of `new_conversation(` (`conversations.py` itself plus 7 callers:
  `scheduler.py`, `api/v1/agents.py`, `api/v1/agent_trigger.py`, `output_recording.py`,
  `checkpoint_cutover.py`, `api/v1/questions.py`, `api/v1/messages.py`) — same file set
  design.md's open question 3 lists. Nothing has changed since design.md was written earlier
  the same day; the sweep still holds. `checkpoint_cutover.py:91` remains the only site that
  will need to override the freshly-set self-lineage with the predecessor's — that's phase 2
  (C2), not this one.

**Verified, not assumed.**
- `pytest tests/test_migrations.py -k 0085 -q` → 1 passed.
- `pytest tests/test_migrations.py tests/test_project_persistence.py -q` → 76 passed, 1 skipped
  (the skip is `test_error_summary_rejects_501_chars`, SQLite-only skip, pre-existing and
  unrelated), 126s. Full file-chunk run, not a whole-suite run — the runway note's ~7 minute /
  600s cap warning is for `hub/tests/` as a whole, not this pair.
- `pytest tests/test_conversations.py -q` → 4 passed, sanity check that `new_conversation`'s
  new default field didn't disturb its existing callers.

Ticked `tasks.md` boxes 1.1–1.6 — all six ran and passed as described above, nothing ticked on
the strength of a plan.

**Next:** C2 — conversations-continue phase 2 (the cutover keeps the line of work). Per the
brief, expect the sender-side test added in 2.1 to fail before 2.2/2.3 land; that's the known
pre-existing defect, not a regression introduced here.

## Iteration 2 — 2026-08-21T23:36:00+01:00 — C2: a cutover keeps the line of work

Entry state matched STATE.json exactly: branch `autonomous/2026-08-21-refine-and-continue` at
`086e1eb`, C1 landed, current/next_action pointed at C2. No reconciliation needed.

**2.2 — `hub/hub/checkpoint_cutover.py`.** Added `successor.lineage_id = predecessor.lineage_id`
alongside the existing `bound_sender_*` copy at what were lines 108-109.

**2.3 — `hub/hub/conversations.py`, `peer_bound_conversation`.** Widened the forward lookup from
bare equality (`bound_sender_conversation_id == sender_conversation_id`) to equality **or**
membership in the set of conversation ids sharing the sender conversation's `lineage_id`, via a
scalar subquery (`select(lineage_id) where id == sender_conversation_id`) feeding a second
subquery (`select(id) where lineage_id == <that>`). Kept the literal-equality condition alongside
the widened one rather than replacing it — see the regression below for why that turned out to be
load-bearing, not belt-and-suspenders.

**2.1 — five tests added to `hub/tests/test_checkpoint_cutover.py`** (new `# lineage` section):
successor shares predecessor's lineage; sending from a successor reaches its already-bound
recipient thread (the sender-side case, confirmed failing before 2.3 by temporarily stashing the
`conversations.py` change and re-running just that test — it failed with `found is None` as
predicted, then passed once unstashed); a correspondent reaches the recipient's newest open
(successor) conversation after the recipient's own cutover; lineage resolves with zero checkpoint
rows in the picture (two conversations related only by a direct `bound_sender_conversation_id`
value, no `cut_over` involved); a fresh conversation is its own lineage.

Had to fix the file's own `_conversation()` test helper first: it builds `Conversation(**fields)`
directly rather than going through `new_conversation()`, so every row it created carried
`lineage_id=None` and all six new tests failed for the same wrong reason. Added
`lineage_id: conversation_id` to its default fields — matching what `new_conversation` does for
every real row.

**2.4 — self-lineage regression test.** `test_a_self_lineage_row_resolves_exactly_as_the_old_equality_did`:
two independent sender/recipient pairs, neither cut over, asserts the widened query still picks
the right one and ignores the unrelated pair — the backfill's safety net, exercised directly.

**A regression the first cut of 2.3 caused, caught by 2.5.** Running the widened lookup alone
(subquery membership, no literal-equality fallback) against the *existing* suite broke
`test_agent_message_routing.py::test_three_messages_on_one_line_of_work_land_in_one_thread`: three
messages that should land in one thread instead minted three. Cause: that test's `_active_run`
helper sets `Run.conversation_id = "conv-one"` but never creates an actual `Conversation` row with
that id — a synthetic identifier that was never a row, which real production traffic doesn't do
(`source_conversation_id` in `messages.py` always comes from a live run's real conversation) but
the test fixture does. The lineage subquery resolves to `NULL` for a nonexistent id, and
`NULL`-vs-`NULL` matches nothing in SQL, so the widened-only condition found no sibling and minted.
Fixed by keeping the original literal-equality condition **alongside** the lineage-membership one
(`or_(...)`) rather than replacing it — the literal match is what still finds a binding keyed on an
identifier with no conversation row behind it. Documented the reasoning in
`peer_bound_conversation`'s docstring so a future reader doesn't "simplify" the OR back down to the
subquery alone.

**Verified, not assumed.**
- Sender-side test failure/pass confirmed both ways via `git stash` on `conversations.py` alone
  (5 warnings, 1 failed as predicted / 36 passed once restored).
- `pytest tests/test_checkpoint_cutover.py tests/test_conversations.py
  tests/test_agent_message_routing.py tests/test_archived_send_refusal.py -q` → 60 passed (was 1
  failed before the OR fix).
- `pytest tests/test_migrations.py tests/test_project_persistence.py -q` → 76 passed, 1 skipped
  (same pre-existing SQLite-only skip as iteration 1), 98s — re-run as a sanity check since this
  phase touches `conversations.py` and `checkpoint_cutover.py`, both exercised by that pair.
- `npx openspec validate conversations-continue --strict` → valid.

Ticked `tasks.md` boxes 2.1-2.5 — all five ran and passed as described above.

**Next:** C3 — conversations-continue phase 3 (a reply continues the conversation). Add reverse
resolution and wire it into `messages.py` **between** the forward lookup and the mint, without
reordering the forward lookup (design.md D1 depends on forward-first). Include the 3.4 regression
test: three alternating messages produce two conversations, not three.

## Iteration 3 — 2026-08-21T23:58:39+01:00 — C3: a reply continues the conversation

Entry state matched STATE.json exactly: branch `autonomous/2026-08-21-refine-and-continue` at
`45d50f1`, C2 landed, current/next_action pointed at C3. No reconciliation needed.

**3.2 — `reply_bound_conversation` in `hub/hub/conversations.py`.** Implements design.md D2
exactly: given `sender_conversation_id`, look up the sender's own conversation `src`; if
`src.bound_sender_conversation_id` is unset, fail. Otherwise look up the named conversation; fail
unless it belongs to the given `project_id` **and** its `agent` is the recipient (this is what
keeps a message to a third agent from continuing an unrelated thread — the named conversation is
whoever the sender's own thread is bound to, not necessarily who this send is addressed to).
Resolves to the newest **open** conversation sharing that named conversation's `lineage_id`, not
the named conversation itself, so a cutover on the recipient's side is followed to the successor
rather than stranding a reply on an archived predecessor.

**3.3 — wired into `hub/hub/api/v1/messages.py`.** Added a second `if recipient_conversation is
None:` block calling `reply_bound_conversation`, placed immediately after the existing
`peer_bound_conversation` call and before the pre-existing mint block. The forward lookup itself
is untouched — same call, same arguments, same position — so design.md D1's "every case that
resolves today resolves identically" holds by construction, not just by testing.

**3.1 / 3.4 — `hub/tests/test_conversation_reply.py`, new file, 7 tests.** Chose a new file over
extending `test_agent_message_routing.py`: the six 3.1 scenarios plus the 3.4 regression are all
reverse-resolution-specific and read better grouped under their own docstring than interleaved with
the forward-lookup suite. Reused that file's helper shapes (`_active_run`, `_sync_agents`,
`_conversation_of`) rather than importing them, matching the existing convention of small
per-file private helpers over a shared test-utility module.

Covers: a reply reaches the thread it answers; an exchange settles into exactly two conversations
(A→B mint, B→A reverse-resolve, A→B forward-resolve — three sends, two conversations); a message
to a *third* agent from a thread that is bound back to someone else does not continue that
unrelated thread; a reply continues into an operator-origin conversation, with the replying agent
recorded as `origin_agent` on the resulting queue entry (D5 — confirmed already true, nothing new
needed for attribution); continuation survives the replying side's own cutover (reply from a
successor conversation, bound to the same predecessor id, still resolves via the successor's own
`bound_sender_conversation_id` copy — this exercises the C2 lineage plumbing and the C3 reverse
rule together); an archived line with no open successor in its lineage falls through to minting,
same as an ordinary forward miss; and the 3.4 regression itself, three messages alternating
A→B→A→B... landing in exactly two conversations.

**A test-construction bug caught by the tests, not the code.** The first draft of four of the seven
tests referenced the *sender's own* conversation (`conv-a1`, `conv-a`, `conv-alt-a`) only as a
string passed to `_active_run`, the way `test_agent_message_routing.py`'s senderless-traffic tests
do — never creating an actual `Conversation` row for it. That pattern is correct for the forward
lookup's literal-equality fallback (a sender id with no row behind it, as `Run.conversation_id` can
be for the Hub/scheduler), but wrong here: `reply_bound_conversation` starts by resolving `src =
get_conversation_by_id(db, sender_conversation_id)`, and a sender's own thread not existing as a
row means there is nothing to read `bound_sender_conversation_id` off of. All four failed with the
reply landing back in a fresh mint instead of the expected thread. Fixed by giving the sender side
a real row (`_open_conversation(..., origin="operator")`) before starting its run, matching what an
actual agent conversation looks like in production. Confirmed the fix was real and not
coincidental: reverted `conversations.py`/`messages.py` via `git stash`, reran — 5 of 7 tests failed
(the two structurally forward-only ones still passed, correctly, since they don't depend on 3.2/3.3
at all) — then restored and reran clean.

**Verified, not assumed.**
- `pytest tests/test_conversation_reply.py -q` → 7 passed.
- `git stash -- hub/api/v1/messages.py hub/conversations.py` then rerun → 5 failed, 2 passed
  (as predicted); `git stash pop` restored the change, rerun → 7 passed.
- `pytest tests/test_conversations.py tests/test_agent_message_routing.py
  tests/test_archived_send_refusal.py tests/test_checkpoint_cutover.py
  tests/test_conversation_reply.py -q` → 67 passed.
- `pytest tests/test_conversation_archive.py tests/test_conversation_archive_refusal.py
  tests/test_conversation_attention.py tests/test_conversation_context_usage.py
  tests/test_conversation_contract.py tests/test_conversation_loop_marker.py
  tests/test_conversation_origin.py tests/test_conversation_task_binding.py
  tests/test_conversation_titles.py tests/test_messages.py -q` → 82 passed.
- **Full `hub/tests/` suite, chunked** (177 files split into three `split -n l/3` groups, since the
  whole suite is ~7min and exceeds the 600s single-command cap): chunk 1 → 750 passed, 1 skipped, 1
  xpassed (277s); chunk 2 → 1017 passed, 9 skipped (353s); chunk 3 → 980 passed, 2 skipped (241s).
  2747 passed total, zero failures, all skips/xpass pre-existing and unrelated (SQLite-only skips,
  a documented xfail-that-now-passes elsewhere in the suite). No delivery test changed behaviour —
  the forward path was not disturbed.
- `py -3.11 -m ruff check` and `black --check` on the three touched/added files → clean.
- `npx openspec validate conversations-continue --strict` → valid.

Ticked `tasks.md` boxes 3.1–3.5 — all five ran and passed as described above.

**Next:** C4 — conversations-continue phase 4 (starting a thread deliberately). Add
`start_new_thread: bool = False` to the message-create schema, honour it in `messages.py` (skip
both lookups, mint directly), and refuse it in combination with an explicit `conversation_id` per
design.md D4. Read D4 first to confirm which route(s) the flag belongs on.
