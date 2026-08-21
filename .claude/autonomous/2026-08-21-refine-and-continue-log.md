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
