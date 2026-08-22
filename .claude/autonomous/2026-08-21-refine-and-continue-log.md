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
design.md D4 first to confirm which route(s) the flag belongs on.

## Iteration 4 — 2026-08-22T00:03:50+01:00 — C4: starting a thread deliberately

Entry state matched STATE.json exactly: branch `autonomous/2026-08-21-refine-and-continue` at
`118644c`, C3 landed, current/next_action pointed at C4. No reconciliation needed.

**Two schemas, not one — the thing 4.2 flagged as worth checking.** Read design.md D4 first, which
names `send_message` (the MCP tool) as the surface. Tracing its HTTP call showed the agent-facing
route (`POST /agent-actions/messages`) validates against `AgentMessageCreate`
(`hub/hub/api/v1/agent_actions.py`), a *separate*, `extra: "forbid"` schema from the operator-route
`MessageCreate` in `hub/hub/schemas/messages.py` that only gets built internally afterward
(`agent_actions.py:196-205`) and handed to the shared `create_message_for_actor`. Adding
`start_new_thread` to `MessageCreate` alone — which is what task 4.2's literal wording pointed at —
would have left every agent send 422 on the new field, the same class of total outage the existing
comment on `AgentMessageCreate.conversation_id` warns about for exactly this "`extra: forbid` plus
a missing key" shape. Added the field to both: `MessageCreate` (used directly by the
operator-facing `POST /projects/{id}/messages`) and `AgentMessageCreate` (used by the route
`send_message` actually calls), threading it through the explicit `MessageCreate(...)` construction
in `send_peer_message`.

**4.3 — `hub/hub/api/v1/messages.py`.** Added a guard clause before the existing `if
body.conversation_id:` block: `conversation_id` and `start_new_thread` together is refused with a
409 in the same three-part shape (cause, way out, message content back) as the archived-conversation
refusal a few lines below, plus the same `agent_action_rejected` event the other rejections in this
function persist — the existing refusals all record one and a silent 409 would have been the odd
one out. Added a new `elif body.start_new_thread:` branch, sitting between the `if
body.conversation_id:` branch and the existing `else:` (peer/reply/mint) branch, that mints
directly — same three lines (`new_conversation`, `bound_sender_conversation_id`,
`inherit_runtime_overrides`) as the existing mint-on-miss fallback, since D4 says this is a
deliberate mint, not a fallback, so it gets its own comment rather than sharing the fallback's.

**4.1 / 4.4 — `hub/tests/test_conversation_start_new_thread.py`, new file, 4 tests.** Covers: an
explicit `start_new_thread` request mints a second thread even though a binding to the recipient
already exists (the forward lookup would otherwise have found it); an ordinary follow-up with no
flag afterward resolves to the *new* thread, not the old one — proving 4.4 without adding any new
state, since `peer_bound_conversation`'s existing `.order_by(...desc())` already prefers the
newest; omitting the flag is unaffected (a light regression check); and naming `conversation_id`
together with `start_new_thread` is refused with nothing created and nothing delivered — checked by
snapshotting the full `Message`/`Conversation` table contents before and after the rejected call
and asserting the sets of ids are identical, not just that the response was a 409.

**Verified, not assumed.**
- `pytest tests/test_conversation_start_new_thread.py -q` → 4 passed.
- `git stash -- hub/api/v1/messages.py hub/api/v1/agent_actions.py hub/schemas/messages.py` then
  rerun → 3 failed (the two mint-comparison tests and the refusal test — the refusal test fails
  with a 422 first, since the field is rejected outright by `extra: "forbid"` before reaching the
  409 logic, which is itself confirmation the field genuinely didn't exist on that schema before),
  1 passed (the flag-omitted test, correctly unaffected since it never touches the new field);
  `git stash pop` restored the change, rerun → 4 passed.
- `pytest tests/test_conversation_start_new_thread.py tests/test_conversation_reply.py
  tests/test_agent_message_routing.py tests/test_archived_send_refusal.py
  tests/test_checkpoint_cutover.py tests/test_conversations.py tests/test_messages.py -q` →
  77 passed.
- `pytest tests/test_agent_actions_coordination.py tests/test_agent_message_routing.py
  tests/test_archived_send_refusal.py tests/test_conversation_reply.py
  tests/test_conversation_start_new_thread.py tests/test_mcp_body_contract.py
  tests/test_mcp_server.py tests/test_project_workspace_unavailable.py tests/test_messages.py
  tests/test_conversations.py tests/test_checkpoint_cutover.py -q` → 152 passed — this phase widens
  two shared request schemas, so both mcp_server-contract tests and the coordination suite were
  worth checking explicitly, not just the conversation-specific files.
- **Full `hub/tests/` suite, chunked** (175 files, `split -n l/3`): first pass on chunk 1 hit one
  failure, `test_checkpoint_record.py::test_the_lineage_id_is_carried_forward_not_regenerated` —
  passed alone in isolation, so re-ran the exact same chunk command twice more: once with this
  iteration's changes stashed (a *different* test failed instead,
  `test_evidence_latest_review_signal.py::test_a_later_acceptance_replaces_the_reason_shown`, plus
  the three expected `test_conversation_start_new_thread.py` failures) and once with the change
  restored and nothing else touched (754 passed, 1 skipped, 1 xpassed, zero failures). Different
  tests failing across otherwise-identical runs, with and without this change present, is
  pre-existing order/state flakiness in the suite, not something C4 introduced — not this
  iteration's bug to fix, and not fixed. Clean chunk 1: 754 passed, 1 skipped, 1 xpassed (238s).
  Chunk 2: 1017 passed, 9 skipped (356s). Chunk 3: 980 passed, 2 skipped (238s). Total 2751 passed
  (2747 from iteration 3 plus this file's 4), zero failures on the clean run, all skips/xpass
  pre-existing.
- `py -3.11 -m ruff check` on the three touched files → clean. `black --check` flagged the new test
  file only (a collapsed multi-line expression); ran `black` on it and reran the file's tests to
  confirm the reformat changed nothing behavioural (4 passed).
- `npx openspec validate conversations-continue --strict` → valid.

Ticked `tasks.md` boxes 4.1–4.4 — all four ran and passed as described above.

**Next:** C5 — conversations-continue phase 5 (the tool surface tells the truth). Add
`start_new_thread` to `send_message` in `hub/hub/mcp_server.py:174-208` (stdlib + fastmcp only —
it's a pass-through, `_hub_request`'s payload dict just needs the new key added) and rewrite the
`conversation_id` docstring at lines 191-194, which still says "Leave unset to use their most
recent one" — stale since the binding contract shipped. Also update whatever test asserts
`mcp_server.py`'s restatements agree with the Hub's schema (task 5.4) and add a test that the
published description doesn't claim recency and declares `start_new_thread` with its default (task
5.1). Read design.md D6 first — it's the shortest phase left and names the exact lines.

## Iteration 5 — 2026-08-22T00:55:37+01:00 — C5: the tool surface tells the truth

Implemented `conversations-continue` tasks.md section 5, all five boxes.

- `hub/hub/mcp_server.py`: `send_message` gained `start_new_thread: bool = False`, threaded into
  the `_hub_request` payload dict alongside `conversation_id`. Nothing new imported — the flag is a
  pure pass-through, matching `AgentMessageCreate`'s existing field of the same name from C4.
  Rewrote the `conversation_id` docstring (lines 191-194), which still said "Leave unset to use
  their most recent one" — stale since the binding contract shipped in phases 2/3. It now says
  "continue the thread already bound between you and them, or to start one if none is bound yet",
  and added a paragraph for `start_new_thread` naming the refusal-with-`conversation_id` rule from
  D4.
- `hub/tests/test_mcp_server.py`: updated `test_send_message_payload_contains_no_identity_or_run`'s
  expected body to include `"start_new_thread": False` and fixed its own comment, which repeated
  the same stale "most recent conversation" framing. Added
  `test_send_message_docstring_does_not_claim_recency_and_declares_start_new_thread` (task 5.1) —
  asserts `"recent"` is absent from the docstring (case-insensitive, so it also catches "Recent"),
  `"start_new_thread"` is named, and the parameter's actual default (read via `inspect.signature`,
  not just grepped from the docstring) is `False`.
- `hub/tests/test_mcp_body_contract.py`: added `test_send_message_starting_a_new_thread_is_accepted`
  (task 5.4) — same shape as the existing `conversation_id`-naming test, sends `start_new_thread=True`
  through the real `AgentMessageCreate` route model. This file exists specifically because
  `conversation_id` drifted between the tool and the agent schema once already (see its module
  docstring); `start_new_thread` is a second field added to the same two places, so it gets the
  same join test rather than trusting C4's schema-only test to be a large enough net.

**Verified, not assumed.**
- `pytest tests/test_mcp_server.py tests/test_mcp_body_contract.py tests/test_conversation_start_new_thread.py tests/test_conversation_reply.py -q`
  → 52 passed.
- `git stash -- hub/mcp_server.py` (source only, tests kept) → reran the two mcp test files → 3
  failed exactly as expected: the payload-shape test (old body has no `start_new_thread` key), the
  new docstring test (`TypeError: unexpected keyword argument`), and the new body-contract test
  (same `TypeError`) — 38 passed. `git stash pop` restored the change, rerun → 41 passed.
- **Full `hub/tests/` suite, chunked** (178 files, `split -n l/3`, three ~59-file chunks): chunk 1 —
  750 passed, 1 skipped, 1 xpassed (233s). Chunk 2 — 1 failure,
  `test_evidence_latest_review_signal.py::test_a_later_acceptance_replaces_the_reason_shown`; reran
  that file alone → 4 passed. Same test name as the pre-existing order/state flake iteration 4's
  log already identified on a different chunk split, unrelated to this change (nothing in C5
  touches evidence review) — confirmed rather than assumed, not fixed, matches the "not this
  iteration's bug" precedent. Otherwise 1022 passed, 9 skipped (349s). Chunk 3 — 980 passed, 2
  skipped (236s). Total 2753 passed (2751 from iteration 4 plus this phase's 2 new tests), zero
  failures attributable to this change.
- `py -3.11 -m ruff check hub/` → all checks passed. `black --check hub/` → 396 files unchanged
  (both run over the whole `hub/` tree per task 5.5, not just the touched files).
- `npx openspec validate conversations-continue --strict` → valid.

Ticked `tasks.md` boxes 5.1–5.5 — all five ran and passed as described above. Phase 5 of 7 is now
complete; phase 7 remains explicitly out of scope (human verification).

**Next:** C6 — conversations-continue phase 6 (tasks.md section 6, "the outbound message folds").
Carry `subject` through `TimelineEntry` (`hub/hub/api/v1/agent_chat.py`) and
`hub/ui/src/api/agentChat.ts`, then fold the OUTBOUND branch of `MessageEntry` in
`hub/ui/src/components/agents/AgentTimeline.tsx` — `WorkRow` in the same file is the existing
pattern to reuse. Do not fold the inbound branch (design.md explains why in phase 6's section, not
yet reread this iteration — read it first). This is the only queue item permitted to touch
`hub/ui/src`; ends with `cd hub/ui && npm run build` then `py -3.11 scripts/refresh_ui_bundle.py`
FROM THE REPO ROOT, committing `hub/ui/src` and `hub/hub/static/ui` together. Likely two iterations
given the UI build step.

## Iteration 6 — 2026-08-22T01:24:39+01:00 — C6: the outbound message folds

Implemented `conversations-continue` tasks.md section 6, all seven boxes, in one iteration —
smaller than the two-iteration estimate since design.md carried no separate rationale for phase 6
beyond tasks.md itself (checked: no "phase 6" heading, no fold-specific D-entry; D5 only touches
attribution, already implemented).

- `hub/hub/api/v1/agent_chat.py`: added `subject: Optional[str] = None` to `TimelineEntry`
  (nullable — `send_message` requires it going forward per phase 4/5, but the column predates that
  and older rows have none) and set it from `msg.subject` in `_message_to_timeline`, which
  previously discarded it.
- `hub/ui/src/api/agentChat.ts`: added the matching `subject?: string | null` field to the
  `TimelineEntry` interface.
- `hub/ui/src/components/agents/AgentTimeline.tsx`: split `MessageEntry`'s shared peer-traffic
  render into two paths. Inbound is untouched — still the same always-open bubble. Outbound routes
  to a new `OutboundMessageEntry`, following `WorkRow`'s shape exactly as directed: a clickable
  header row (agent name → recipient, an inline truncated preview, the timestamp) plus `useState`
  for expansion, body rendered below only when open. Preview text is `entry.subject` when present,
  else the first line of `entry.content`, else the literal `'Message'` — task 6.5's readable
  fallback for the nullable column. `queuedTag`/`withdraw` are still threaded through defensively
  (outside the toggle button, not nested inside it — button-in-button is invalid HTML) even though
  checking `groupIntoTurns` confirmed `outbound_peer` entries are never queued in practice: they're
  always `delivered` per `_message_to_timeline`'s default, so that combination cannot occur today.
- `hub/ui/src/__tests__/agentTimeline.test.tsx`: added a new describe block covering all five
  task-6.1 scenarios (folds by default with the subject showing and the body hidden; two same-
  recipient messages with different subjects produce two distinct visible lines; clicking expands
  to reveal the content; an expanded entry survives a rerender that appends a later turn — checked
  first that turn-level folding is never automatic on append, only by hand, so this wasn't
  incidentally testing the wrong mechanism; an inbound message renders its full content
  unconditionally) plus a sixth for the no-subject fallback (task 6.5). Left the pre-existing
  outbound test (line 71) unmodified — its single-line, no-subject content happens to equal its
  own fold preview, so it remains a valid (if incidental) assertion that folding didn't break it.
- `hub/tests/test_agent_chat.py`: added `subject` as an optional keyword to the `_add_outbound_message`
  test helper (previously had no way to set it) and two new tests — `subject` recorded correctly
  when set, and defaults to `None` (not a `KeyError`/missing key) when omitted, covering the
  nullable-column case from the API side.

**Verified, not assumed.**
- `pytest tests/test_agent_chat.py -q` → 12 passed (10 pre-existing + 2 new).
- `cd hub/ui && npx vitest run src/__tests__/agentTimeline.test.tsx` → 34 passed (28 pre-existing +
  6 new).
- Full UI suite: `npx vitest run` → 121 files, 1226 passed (1220 from prep's runway check + 6 new;
  the two "Error: boom" stack traces in stderr are `ErrorBoundary.test.tsx` intentionally throwing
  to test the boundary, not a failure — file-level result confirms pass).
- `npm run lint` → clean. `npx tsc --noEmit` → clean, no output.
- `py -3.11 -m ruff check` and `black --check` on both touched Python files → clean.
- **Full `hub/tests/` suite, chunked** (`ls tests/*.py | split -n l/3`, three ~59-file chunks, run
  from `hub/` per the dead-end note about root-relative paths): chunk 1 — 752 passed, 1 skipped, 1
  xpassed (265s). Chunk 2 — 1023 passed, 9 skipped (350s), no flake this split. Chunk 3 — 1 failure,
  `test_spec_index.py::test_a_changed_acceptance_criterion_is_a_rewording` (an FR revision-ordering
  assertion — nothing in this phase touches spec indexing or FR revisions); reran that file alone →
  17 passed, confirming it as the same class of pre-existing order/state flakiness this log has
  already attributed to other tests on other chunk splits across iterations 4 and 5, not this
  phase's bug. Otherwise 979 passed, 2 skipped (239s). Total passed across the chunked run: 2754;
  with the isolated-clean flake counted, 2755 — exactly 2753 (iteration 5's total) + 2 (this
  phase's new `test_agent_chat.py` tests). Zero failures attributable to this change.
- `npx openspec validate conversations-continue --strict` → valid.
- `npm run build` → clean (2695 modules, one pre-existing >500kB chunk-size advisory, not new).
  `py -3.11 scripts/refresh_ui_bundle.py` → refreshed `hub/hub/static/ui` and recorded the build
  stamp.

Ticked `tasks.md` boxes 6.1–6.7 — all seven ran and passed as described above.

**`conversations-continue` phases 1–6 of 7 are now complete and verified.** Phase 7 (human
verification, 7.1–7.8) remains explicitly out of scope for this loop — it needs a live trial Hub
with two real agents exchanging messages, which only the operator can drive and judge. Do not tick
its boxes or claim the change is done; phases 1–6 are done, the change is not.

**Next:** the queue moves to the second half of the night — U0a, "UI system pass 1 - foundations".
Read `design/IDENTITY.md` first (not yet read this run). Research via WebSearch and the T3 Code
sourcemaps, then produce `design/mocks/_system/foundations.html`: the motion scale applied, an
elevation scale from the existing surface steps, and every interaction state (hover, press,
focus-visible, disabled, loading, selected, empty). This is a mock only — the UI-half limit applies
from here on: do not touch `hub/ui/src` for any further queue item unless it is later explicitly
part of `conversations-continue` (it is not; that change is done).

## Iteration 7 — 2026-08-22T01:36:27+01:00 — U0a: UI system pass 1, foundations

First UI-half iteration. Branch/log/STATE.json all reconciled cleanly on entry — no drift to fix.

Read `design/IDENTITY.md` in full (not yet read this run) before anything else, per its own
instruction. Its rejection test — especially clause 5, "the same application, improved" — governed
every choice below.

**P1 — explore.** Read the current product rather than guessing: `hub/ui/src/index.css` (all 124
tokens), `buttonVariants.ts` (the raised/ghost/outline/destructive states and the
lit-from-above/inverts-under-press pattern), `TaskCard.tsx` (its manual hover-border handling and
the `task-live-pulse` reduced-motion pattern — the one already-shipped considered animation in the
product), and `EmptyState.tsx` (confirmed IDENTITY.md's "plainest thing in the product" claim: icon
circle + title + optional description, no motion, no variation by cause). `grep -r skeleton
hub/ui/src` → zero matches — no skeleton pattern exists anywhere today. Two `WebSearch` calls
(elevation/dark-UI surface layering; motion duration/easing/state best practices) plus a third
(skeleton vs spinner, empty-state patterns) confirmed the existing token scale already brackets
current best practice correctly (150/250/500ms durations, expo-out easing, lighter-surface-not-shadow
elevation) — nothing needed inventing, only naming and applying. Spot-checked the T3 sourcemaps at
the path in STATE.json for "skeleton" (3 files matched) but the actionable takeaway was the same one
the general research gave, so nothing further was read closely or quoted, matching IDENTITY.md's
"structure transfers and implementation does not." Wrote `design/mocks/_system/RESEARCH.md` — six
concrete gaps found (elevation isn't a named scale, focus-visible weight is inconsistent, disabled
has one idiom used in two places, loading has zero shape-matched patterns, selected/active/hover
collapse outside `.row-item`, empty states don't vary by cause), each validated against the
rejection test's fixed constraints before being carried into the mock.

**P2 — validate + mock.** Built `design/mocks/_system/foundations.html`, self-contained,
`<link>`-importing `../../../hub/ui/src/index.css` so every colour is a real token (verified: the
`@tailwind` directives are simply unrecognised at-rules a browser skips, the `@layer base` custom
property declarations parse and apply natively, and the `@fontsource` imports 404 harmlessly to the
declared system-font fallback — so the tokens resolve without a build step). Covers: a four-tier
elevation scale named from the existing `--bg → --rail → --surface → --surface-2 → --surface-3`
steps plus `--lift-hi`/`--press-lo`; the three durations demoed with a hover-triggered fill so the
*feel* of each is visible, not just its number; every button variant (primary/ghost/outline/
destructive) in rest/hover/press/focus-visible/disabled, forced via `data-force` attributes so every
state renders without a live pointer (screenshots capture all of them at once); a row and a card
generalised from `.row-item` and `TaskCard`'s own patterns in rest/hover/press/selected/live/
disabled; an input in rest/hover/focus/error/disabled; three skeleton shapes (task card, roster row,
message body) using a `color-mix` shimmer sweep gated behind `prefers-reduced-motion`, reusing
`task-live-pulse`'s existing reduced-motion pattern rather than inventing a new one; and three empty
states sharing `EmptyState.tsx`'s exact icon-circle-plus-text shape but varying the cause (nothing
exists yet / filter matched nothing / still loading, which is a skeleton, not this component at
all). Empty-state icons are hand-written lucide-style inline SVGs (ListChecks, Search — matching the
`Icon.tsx` names `task_alt`/`search` already used for this purpose elsewhere), not emoji — caught
and fixed a clause-5 violation before it shipped (emoji is a third icon source).

**Verified, not assumed.** No test suite applies to a static mock, so verification was
`py -3.11` + Playwright opening the file directly (`file://` URL — the dead-ends note says
`uishot.py` expects the live app's own dark-mode toggle button and won't drive a standalone mock),
screenshotting both themes at full-page height, and reading both PNGs. Both render legibly: no new
hue anywhere, `--blue`/`--ring` appears only on focus rings and the two intentionally-blue "selected"
swatches, radii are visibly one scale, no glass/gradient/shadow-as-decoration, and side by side with
the current app the elevation/button/row swatches read as the same application's own components
named and demonstrated — not a redesign. Screenshots were verification-only, not committed: the
repo's `.gitignore` has a blanket `*.png` rule (line 80), so the PNGs were deleted after reading
rather than force-added against that rule. **This is a real problem for the Z queue item**, which
wants "before/after screenshots inline" in the eventual review index — under the current
`.gitignore`, a screenshot cannot be committed at all. Flagging as a finding rather than silently
force-adding (`git add -f`) or silently deciding to change `.gitignore` myself: recorded in
STATE.json's `dead_ends_inherited` for whichever iteration reaches Z to solve (an allowed extension,
inlining as a data URI in the HTML itself, or an operator decision to carve a `.gitignore` exception
for `design/mocks/**`).

**Not done this iteration, deliberately:** a formal P3/P4 iterate-and-critique pass and a
`RATIONALE.md` — U0a's `next_action` scoped this iteration to "P1_explore + P2_validate_and_mock
shape," and the screenshot-and-read above already served as verification, not the numbered screens'
separate iterate pass. If a later iteration wants to deepen `foundations.html`, treat it as
available inventory rather than a hard requirement — U0b is next in the queue either way.

**Next:** U0b — "UI system pass 2 - component vocabulary." Produce
`design/mocks/_system/controls.html`: the full button taxonomy already read in `buttonVariants.ts`
(sizes xs/sm/md/lg/icon/icon-sm/icon-xs/pill, not just the four variants foundations.html covered),
form/input controls, toggles, selects, menus, badges/chips, and a colour-coding system using the
semantic tokens (`--green`/`--amber`/`--red`/`--purple`) and the 8-colour agent scale
(`--agent-1..8` with their `-tint`/`-border` derivations) consistently — today inconsistent per
IDENTITY.md, and fixing that inconsistency is explicitly in scope; inventing a ninth colour is not.
Read `RowMenu.tsx`, `Badge.tsx`, and wherever selects/toggles currently live before mocking them —
same "read the current comments first" discipline as this iteration.

## Iteration 8 — 2026-08-22T01:49:57+01:00 — U0b: UI system pass 2, component vocabulary

Branch/log/STATE.json all reconciled cleanly on entry — clean tree, HEAD matched the "released
heartbeat" commit, no drift.

**P1 — explore.** Read `buttonVariants.ts` in full again for the sizes `foundations.html` had not
covered (`xs/sm/md/lg/icon/icon-sm/icon-xs/pill` — it only demoed the four variants at one size),
`RowMenu.tsx` (the existing menu pattern and its 2026-08-08 operator quote on why it's hover/focus,
never right-click), `Badge.tsx`/`StatusBadge` (the `tone()` derivation and the status/variant
colour tables), and every native `<select>`/`<input type=checkbox>` call site
(`AgentSettingsControls.tsx`, `JobForm.tsx`, `ProjectSettingsPanel.tsx`) — confirmed all are the
bare UA control with only background/border/radius on the box; `grep -rn "role=\"switch\""
hub/ui/src` → zero matches, no toggle/switch component exists anywhere. Two `WebSearch` calls
(button taxonomy/hierarchy conventions; semantic colour-coding systems) confirmed the existing
four-variant taxonomy (`primary`/`outline`/`ghost`/`destructive`) already matches the mainstream
primary/secondary/tertiary/destructive split under different names — nothing needed inventing, only
naming and completing the size matrix. Also found, by reading rather than assuming: `Badge.tsx`'s
`INFO = tone('var(--blue)')` colours `in_progress` with `--blue`, which IDENTITY.md's clause 2
reserves for focus/selection only — an existing inconsistency between shipped code and the
identity doc, not something to fix (source is out of scope) but something not to carry forward into
the new colour-coding system. Confirmed `--purple` is already used as a category (not status) colour
at every existing site — `EventRow.tsx`, `LogLine.tsx`, `MessageCard.tsx`, every entry in
`fileIcons.ts`. Appended a "U0b research" section to `design/mocks/_system/RESEARCH.md` with all of
the above, sources, and the validated-against-rejection-test argument for the one new visual
element (a checkbox/toggle checked-fill using `--ring`/`--blue`, defended as "selection" under
clause 2, not a new brand or status role).

**P2 — validate + mock.** Built `design/mocks/_system/controls.html`. Covers: the full 4×8
button taxonomy grid (every variant at every size, matching `buttonVariants.ts`'s exact
height/radius/padding per size); a 4-variant × 5-state grid (rest/hover/press/focus-visible/
disabled) at one representative size, since state treatment doesn't vary by size — repeating it
across all eight would have been redundant, not more thorough; text input/textarea/select in
rest/hover/focus/error/disabled, with the select's UA arrow replaced by a lucide-style chevron via
`appearance: none` (no new icon source — same `Icon`-style inline SVG convention as everywhere
else in this mock series); a checkbox, radio, and toggle/switch (the toggle is the one genuinely
new shape — nothing like it exists in the product today) each in checked/unchecked/hover/focus/
disabled; `RowMenu.tsx`'s pattern restated as static markup (trigger, item, disabled-with-reason,
separator, danger item); three badge/chip families (status pills reusing `StatusBadge`'s tone
recipe, `--purple` category chips, and 8-colour agent identity chips with their `-tint`/`-border`
derivations); and a colour-coding rules table — one row per token family (`--green`/`--amber`/
`--red`/`--purple`/`--agent-1..8`/`--blue`), each with an explicit "answers" and "never" column,
closing with `--blue`'s row stating plainly that `Badge.tsx`'s current "in progress = blue" breaks
this rule today and is not reproduced here.

**Verified, not assumed — and caught a real bug.** `py -3.11` + Playwright, `file://` URL (same
reasoning as U0a: `uishot.py` expects the live app's own toggle), both themes, full-page
screenshots, read as PNGs. First render: the "disabled, checked" checkbox and "disabled, on" switch
cells rendered as merely disabled — no checked fill, no visible checkmark/thumb position — because
both were driven by the same `data-force` attribute and `data-force="disabled"` silently overrode
the checked look. Root cause: `data-force` was being used for two unrelated axes (interaction state
vs. checked state) that need to compose, not exclude each other. Fixed by splitting into an
independent `data-checked` attribute, applied it consistently across checkbox/radio/switch markup
and CSS, re-screenshotted, and confirmed both combinations now render correctly in both themes.
Final screenshots pass the rejection test: no new hue anywhere, `--blue`/`--ring` appears only on
focus rings and the two checked-control fills (selection, per clause 2 — never a button fill or a
status colour), one radius scale, no glass/gradient/shadow-as-decoration, and beside the current
components everything reads as the same application's own vocabulary, named and completed rather
than redesigned. Also removed one piece of dead CSS (`​.chip .dot`, written then never used in the
final markup) before shipping. Screenshots deleted after reading — not committed, per the blanket
`*.png` `.gitignore` rule already flagged in `dead_ends_inherited` for whoever reaches the Z queue
item.

**Next:** S1, "Screen 1 - conversation + composer + left navigation," the main screen and the first
of the four-pass numbered screens. This iteration's `next_action` scopes the very next firing to
P1 (explore) only: read `ConversationView.tsx`, `AgentTimeline.tsx` (including the `OutboundMessageEntry`
this loop's own C6 phase added, and the blue-tinted-bubble-removal comment IDENTITY.md already
cites by name), `Composer.tsx` + its control row, and the actual sidebar/nav components (confirm
real filenames — `SidebarItem` in the queue's S1 description may not be the literal component name),
then `WebSearch` for chat/conversation UI patterns, and write `design/mocks/S1/RESEARCH.md`. Do not
build the mock in that iteration — P2 (validate + mock) is the following one, per the established
one-pass-per-firing rhythm from `_system`.

## Iteration 9 — 2026-08-22T01:58:22+01:00 — S1 P1: explore, conversation + composer + navigation

Branch/log/STATE.json all reconciled cleanly on entry — clean tree, HEAD matched the previous
"released heartbeat" commit, no drift.

**P1 — explore.** Read in full, comments included: `ConversationView.tsx` (the shell hosting the
timeline/composer/panel — its long comment block on document-attach vs. tab-store sync was read but
is out of scope for this screen's visual pass), `AgentTimeline.tsx` (`MessageEntry`, `WorkRow`,
`WorkBlockDisclosure`, `OutboundMessageEntry` — the fold this loop's own C6 phase added — and the
working-indicator gating, whose comment explains two separate operator-reported bugs it fixes),
`Composer.tsx` plus its control row (`ComposerModelControls.tsx`, `ComposerTriggerMenu.tsx`,
`ComposerSpecControl.tsx`), `ConversationControls.tsx` (the header's Stop/Checkpoint/Fold-all set),
`ContextUsageIndicator.tsx`, `AgentOutputPanel.tsx`'s header/body/composer wrapper (lines 840–1010,
to see how the pieces actually compose), `Sidebar.tsx`, `AgentTree.tsx`, and `SidebarItem.tsx`.
Also read `buttonVariants.ts` in full specifically to check a hypothesis against the real CSS rather
than assume it (see finding 2 below). Two `WebSearch` calls (chat/conversation UI: message grouping,
timestamps, composer affordances; sidebar/nav treatments for a dense tool) plus a close read of the
T3 Code sourcemaps for the directly equivalent surfaces — `MessagesTimeline.tsx`, `ChatComposer.tsx`
+ `ComposerPrimaryActions.tsx` + `ComposerBannerStack.tsx`, `ChatHeader.tsx`,
`ContextWindowMeter.tsx`, `ThreadStatusIndicators.tsx`, `Sidebar.tsx`, `NoActiveThreadState.tsx`,
`DraftHeroHeadline.tsx` — extracted via a small Python script reading the sourcemap's
`sourcesContent` into `testbed/scratch/t3ref/` (gitignored, confirmed with `git check-ignore -v`
before writing anything there) so they could be read with the `Read` tool, then deleted immediately
after with `rm -rf` — confirmed via `git status --short` afterward that nothing tracked was left
behind. Nothing from them is quoted at length in the tracked research doc, per IDENTITY.md's
reference-material rule — findings are restated as structure only.

Wrote `design/mocks/S1/RESEARCH.md`. Six concrete, code-verified gaps, not generic "make it nicer"
notes:

1. No copy-to-clipboard exists anywhere in `AgentTimeline.tsx`, for any message kind.
2. **`ComposerSpecControl`'s armed/`data-active` state has zero visual effect today** — verified
   directly rather than assumed: `buttonVariants.ts` (read in full) defines no `data-active`
   handling in the base classes or any variant, and `index.css`'s only `data-active` rule
   (lines 422–430) is scoped to `.row-item`, which this `Button` doesn't carry. So pressing
   "Explore" today changes only its own label text ("Explore" → "Exploring") with no other visible
   difference — a control whose entire job is to announce a mode change currently doesn't look
   different when that mode is on. This is the strongest finding of the pass: a real, present-tense
   bug in the existing UI's completeness, not a matter of taste.
3. The composer's send button collapses "sending" and "disabled for an unrelated reason" into one
   visual state (dimmed via `disabled:opacity-[0.64]`), no distinct busy/spinner treatment.
4. `ContextUsageIndicator.tsx` (read in full) is a bare 4px linear bar with a native HTML `title` —
   no rich disclosure, no breakdown, unlike T3's ring-plus-popover for the same concept.
5. Timestamps in the timeline are bare `HH:mm` with no tooltip and no path to full precision.
6. The empty state, folded-turn pill, and work-block `<details>` disclosure all predate U0a's
   motion/empty-state vocabulary — and this is the screen the operator has open most, making it the
   highest-value place in the product to apply what U0a/U0b already built.

Also recorded, as importantly, what is **already good and must not be redesigned**: the per-agent
bubble colour system, the deliberately-neutral operator bubble (the exact comment IDENTITY.md
already cites), the `.row-item`/`.row-action` hover-reveal convention (this pass *extends* it to
messages, it does not invent a new interaction language), the two-signal working-indicator gating,
and the fold-nothing-automatically model. Confirmed via T3's own `Sidebar.tsx` that its row-action
hover-reveal pattern (`opacity-0` → `group-hover`-revealed, absolutely positioned so nothing shifts)
is structurally the *same* idiom AgentWeave's `.row-action` already implements — external research
validated the existing direction here rather than suggesting a new one.

**Verified, not assumed.** This is a research-only pass with no code or mock changes, so
verification here was: `grep`-confirming the copy-button absence and the `data-active` claim
against the actual source rather than trusting a skim, and `git status --short` after deleting the
T3 scratch dump to confirm no tracked file carries any of it.

**Not done this iteration, deliberately:** no mock file. `screen_pass_protocol.P1_explore` scopes
this iteration to research and its write-up only; `P2_validate_and_mock` is the next queue firing.

**Next:** S1 P2 — validate the six findings against IDENTITY.md's rejection test formally, then
build `design/mocks/S1/<variant>.html`, 2–3 variants exploring degree of refinement, self-contained
and importing the real tokens the same way `_system`'s mocks do. At minimum: a message row with
hover-reveal copy + exact-timestamp tooltip, the composer's armed-pill fix (finding 2) and a
busy-send state (finding 3), and a context-usage ring-plus-popover (finding 4) — plus at least one
sidebar/tree row shown in both resting and hover states, per clause 7 of the rejection test.


## Iteration 10 — 2026-08-22T02:10:51+01:00 — S1 P2: validate + mock, conversation/composer/navigation

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 9's commit.

**Validate.** Re-checked all six RESEARCH.md findings against IDENTITY.md's rejection test line by
line before building anything. All six pass: none touches the palette (clause 1), none introduces
--blue outside focus/selection (clause 2 — the spec control's armed fix uses --surface-3/--border-hi,
the same recipe `.row-item[data-active]` already uses; the "considered" live-dot and empty-state
motion cue reuse --green, "something is live," never a new hue), none touches the radius scale
(clause 3/4), no new icon source (clause 5), nothing that costs density (clause 6), and every
control is shown in more than its resting state (clause 7). Nothing was discarded.

**Build.** Two variants, not three — "restrained" and "considered," degrees of the same language
rather than a third distinct one; RESEARCH.md's six findings don't carry enough range to make an
"expressive" reading meaningfully different from "considered" without inventing decoration for its
own sake, which clause 7's "texture means considered detail, not literal texture" rules out anyway.
Read `Composer.tsx`, `ConversationControls.tsx`, `ContextUsageIndicator.tsx`, `AgentTimeline.tsx`
(`MessageEntry`/`OutboundMessageEntry` in full, again, for exact markup), `ComposerSpecControl.tsx`,
`ComposerModelControls.tsx` (`ControlPill`'s popover shape — reused rather than reinvented for the
context-usage disclosure), `SidebarItem.tsx`, and `agentColors.ts` (`--agent-N`/`-tint`/`-border`)
before writing any markup, so the mock's structure and class-level behaviour matches the real
components rather than an impression of them.

`design/mocks/S1/restrained.html` — the smallest fix per finding: hover-revealed copy button on
every message row reusing the product's own `.row-action` idiom; timestamps carry a native `title`
with full date/time; the spec control's armed state gets the `.row-item[data-active]` treatment
(filled `--surface-3` pill, `--border-hi`) so pressing "Explore" now visibly differs from resting;
the send button has four real states (idle/ready/busy-spinner/disabled) instead of one dimmed icon;
context usage is a compact ring instead of a bare 4px bar; work-call and outbound-message disclosure
now animate open/closed on `--dur-base`/`--ease` instead of jumping. Also a first pass at the empty
state (bordered icon tile, a second line) since RESEARCH.md flagged it as the highest-value idle
surface.

`design/mocks/S1/considered.html` — same six fixes taken further: the context ring gains a full
`ControlPill`-shaped popover (used/budget/turns/auto-compact note) instead of the bare `title`; the
timestamp gets a matching tooltip bubble; message rows highlight and lift slightly on hover; the
conversation header's title becomes an actionable trigger with a hover-revealed rename chevron
(T3's `ChatHeader` idiom, confirmed compatible with clause 7 since it costs nothing at rest); the
armed spec pill carries a quiet `--green` live-dot; and the empty state adds a reduced-motion-gated
expanding-ring cue plus a one-press quick-start row against the two agents already in the tree —
recorded in RESEARCH.md as a missing *feature*, not merely unstyled, and mocked per the
pre-authorised note rather than left out. Both variants keep both messages folding (outbound) /
never folding (inbound) exactly as `AgentTimeline.tsx`'s own comment specifies, keep the two-signal
working indicator, and keep the operator bubble neutral — nothing in P1's "must not redesign" list
was touched.

**Verified, not assumed.** Both files opened headless via `py -3.11` + Playwright at `file://`,
both themes, full-page screenshots, read as PNGs (not merely rendered-and-trusted). No console
errors beyond the pre-existing `net::ERR_FILE_NOT_FOUND` for a webfont these standalone mocks don't
carry (present in `_system`'s mocks too — not a regression). Confirmed in both themes: `--blue`/
`--ring` appears only on the composer's focus ring, agent bubble tints are legible, the popover
states (pinned open via `data-force="hover"` for the static capture, same convention as `_system`)
render their full content without clipping against the frame edge, and the empty-state quick-start
chips use the same agent-colour dots the sidebar tree does rather than a new swatch shape.
Screenshots deleted after reading, not committed — blanket `*.png` `.gitignore` rule, same as every
prior pass.

**Not done this iteration, deliberately:** no critique-and-fix cycle. `screen_pass_protocol.P2` is
build-and-lightly-verify; the honest look-and-fix pass against the rejection test is P3, the next
firing, using `scripts/uishot.py` or the same direct-Playwright approach if that script assumes the
live app's own toggle rather than a static file.

**Next:** S1 P3 — screenshot both variants in both themes (four captures), read them, critique
honestly against IDENTITY.md's rejection test, and fix what's found. In particular check: whether
the pinned-open context popover in the "live composition" panel visually crowds the operator bubble
above it (noticed but not fixed this iteration, since forcing states for a demo differs from what
the popover does on a real hover in the real app), whether the considered variant's motion reads as
too busy once several loops are visible together, and whether "restrained" is restrained enough
relative to "considered" to earn being called a lesser degree rather than an unfinished one.

## Iteration 11 — 2026-08-22T02:13:51+01:00 — S1 P3: iterate on the conversation/composer/navigation mocks

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 10's commit
(`6c0c36c`).

**Captured.** `scripts/uishot.py` assumes the live app's own "Switch to dark mode" button role,
which these static mocks don't have (they flip `document.documentElement.dataset.mode` via a
`.theme-toggle` click handler instead) — per iteration 10's note, used a direct-Playwright script
instead: both variants, both themes, 1440×1000 viewport, full-page PNGs, console errors captured.
No console errors beyond the pre-existing `net::ERR_FILE_NOT_FOUND` for a webfont the standalone
mocks don't carry (same as every prior pass, not a regression). Read all four PNGs.

**Found, by looking.** Two real defects in `considered.html`, invisible from source review alone:

1. **Confirmed the concern iteration 10 flagged and left open.** The context-usage popover
   (`.ctx-pop`, `right: 0; top: calc(100% + 6px); z-index: 20`) drops straight down from the header
   and, at the "live composition" panel's actual scroll position, lands squarely over the
   operator's own message bubble ("Add a `start_new_thread` flag to..." — cropped to unreadable in
   the screenshot). Traced this against how real popovers/dropdown menus behave (GitHub's
   notification panel, VS Code hover cards, any header dropdown) — transient content-covering on
   hover is the standard, accepted pattern for exactly this kind of control, and it disappears the
   instant the pointer leaves; the reason it looks alarming here is that the demo force-pins it
   open (`data-force="hover"`) for the static capture, which is a demo artefact, not a live-usage
   one. Concluded: **no structural fix**, recorded as a reasoned judgement call rather than left
   ambiguous. If this becomes a real component later, the same tradeoff applies to `ControlPill`'s
   existing popovers, which already overlay content the same way.
2. **A genuine, unambiguous bug**, not a judgement call: the operator's own message-timestamp
   tooltip (`.msg-time-pop`, centred via `left: 50%; transform: translateX(-50%)`) sits under a
   right-aligned row near the frame's right edge, so the centred tooltip ran past `.frame`'s
   `overflow: hidden` boundary and was clipped mid-text ("Fri 22 Aug, 00:4" — cut). Confirmed via a
   cropped screenshot of just `.frame`'s top 220px in both the diagnosis and the fix. **Fixed**:
   added a `.msg-row.mine .msg-time-pop` override (right-anchored, no centring transform) scoped to
   only the operator's own row — every other message row is left-aligned with room to spare, so
   the generic centred rule stays correct for them. Re-captured and re-cropped after the fix: full
   tooltip text ("Fri 22 Aug, 00:41:07") now renders entirely inside the frame, both themes.
   `restrained.html` was never at risk — it uses the native `title` attribute throughout, which the
   browser itself keeps on-screen.

**The other two questions iteration 10 asked to re-examine, resolved by inspection:**
- *Is "considered" too busy once several motion loops are visible together?* Checked every
  `@keyframes` in the file: `slideIn` (sidebar group entrance) plays once, not a loop;
  `dotPulse`/`spin`/`ringOut` only ever render inside the isolated "Interaction states" reference
  grid, whose entire purpose is showing every state side by side — not a claim about the live
  screen. In the live-composition panel itself, the only continuous loop visible is one subtle
  `livePulse` green dot on the armed spec-control pill (1.6s opacity pulse). Not busy — no change
  needed.
- *Is "restrained" restrained enough relative to "considered"?* Read both full-page screenshots
  side by side: restrained has no custom popover (native `title` only), no lift-on-hover, no
  live-dot, no header-title hover chevron, no empty-state motion — considered has all five. That is
  a clear, legible difference in degree, not two copies of the same file. No change needed.

**Verified.** Re-ran the capture script after the edit: 0 console errors, both variants, both
themes; the fixed tooltip and the untouched popover overlay both confirmed by reading the
resulting PNGs (not assumed from the diff). Screenshots deleted after reading (temp dir outside
the repo this time — `/tmp/s1shots`, nothing to `.gitignore` or clean up in-tree).

**Not done this iteration, deliberately:** this is P3's *first* iterate pass; `screen_pass_protocol`
allows a second one in P4 before `RATIONALE.md` and the review-index entry. Only `considered.html`
changed — `restrained.html` had no defect to fix.

**Next:** S1 P4 — a second iterate pass (re-screenshot both variants/themes once more after this
fix, confirm no regression, look once more for anything missed), then write
`design/mocks/S1/RATIONALE.md` (what was researched → what changed → what was rejected and under
which clause, including the popover-crowding judgement call above) and add S1 to
`design/mocks/index.html` with before/after shots — noting `dead_ends_inherited`'s point about the
blanket `*.png` `.gitignore` rule: inline the shots as data-URIs in the index HTML itself rather
than committing PNG files.

## Iteration 12 — 2026-08-22T02:23:21+01:00 — S1 P4: finish (second iterate, RATIONALE.md, review index)

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 11's commit
(`e7109b3`).

**Second iterate pass.** Re-screenshot both variants, both themes, via the same direct-Playwright
approach as P3 (`uishot.py` still doesn't fit a static mock's own `.theme-toggle` handler). Zero
console errors, same pre-existing webfont 404 as every prior pass.

**Found a second real bug, this one in both variants, by reading the renders rather than the
source.** Cropped the boundary between the last timeline message and the composer and saw the
reviewer's reply bubble cut off mid-second-line, with what looked like a hard clip line straight
through the text — in *both* `restrained.html` and `considered.html`, both themes. Traced the
cause by reading `.timeline`'s CSS (`flex: 1; overflow-y: auto`) and finding neither file's
`<script>` block ever scrolled it — the browser default is to render from the top of a scrollable
region, so with more message content than the fixed 660px `.frame` height, the *last* message sits
partially below the container's own overflow boundary and gets cut, not hidden. Checked whether
this is a demo-only artefact or something the real product actually guards against:
`AgentOutputPanel.tsx:254-286` does, deliberately — its own comment explains that a direct
`scrollTop` assignment (not `scrollIntoView`/`rAF`) is required so following a conversation doesn't
depend on the window currently painting, and the simple-case fallback is `el.scrollTop =
el.scrollHeight`. Neither mock had any equivalent. **Fixed** in both files' existing `<script>`
block: `document.querySelectorAll('.timeline').forEach((el) => { el.scrollTop = el.scrollHeight
})`, with a comment citing the real component's behaviour so a future reader knows this isn't
arbitrary. Re-screenshotted and cropped the same region before/after — the last message and the
"builder is working" indicator now render fully above the composer, both variants, both themes.

**The two questions carried from P3 needed no further work this pass** — both already resolved by
inspection in iteration 11 (popover overlap is standard transient behaviour, not fixed; the
restrained/considered degree difference reads clearly) — re-confirmed only incidentally by the
fresh screenshots, nothing new to add.

**Wrote `design/mocks/S1/RATIONALE.md`** — research → changes for all six RESEARCH.md findings,
what was rejected and under which IDENTITY.md clause (a third "expressive" variant, rejected under
clause 5/7 for having no new finding to justify it; T3's glass banner-stack surface, rejected under
clause 7's no-glass rule; any new hue, checked against clause 2 each pass), and both P3/P4
judgement calls including this iteration's scroll-clip fix with its before/after evidence.

**Built `design/mocks/index.html`** — did not exist yet; this is its first entry (the `Z` queue item
rebuilds it in full later, but `P4_finish`'s own instruction is to add the finishing screen here as
it lands, so an incremental index was started rather than left for `Z` alone). Assembled entirely
via a Python script in `testbed/scratch/` (gitignored, deleted after use) rather than through the
editing tool directly, specifically to avoid pushing ~1.3MB of base64 image text through the
conversation itself — the script read four full-page screenshots (both variants, both themes,
resized to 760px wide) and the scroll-fix before/after crop pair, base64-encoded them, and wrote
the final HTML with them inlined as `data:image/png;base64,...` sources, sidestepping the repo's
blanket `*.png` `.gitignore` rule exactly as `dead_ends_inherited` flagged for whoever reached this
point. Two placeholder sections added below S1's for `_system` (built, not yet indexed with shots)
and S2–S8 (not started), so the index reads honestly about what it does and doesn't yet cover.
Verified by opening the finished `index.html` itself with Playwright (1280×1000, full-page,
`file://`) and reading the screenshot: zero console errors, all six embedded images decode and
render, the before/after fix pair is legible at the chosen size, and the pending sections are
visually distinct (dimmed, "not yet indexed" / "not started" badges) from the done one.

**Verified, not assumed.**
- Direct-Playwright capture of both S1 variants after the scroll fix, both themes → 0 console
  errors; cropped before/after comparison confirmed the clip is gone in all four combinations.
- `npx openspec validate conversations-continue --strict` → valid (unrelated to this iteration's
  changes, re-checked as routine hygiene since this branch also carries that change).
- `git status --short` after cleanup → only the intended four paths changed
  (`.claude/autonomous/STATE.json`, `design/mocks/S1/{considered,restrained}.html` modified;
  `design/mocks/S1/RATIONALE.md`, `design/mocks/index.html` new). No scratch files, no stray `.png`.
- Playwright read of the finished `design/mocks/index.html` itself, both as a rendered screenshot
  and by checking `page.on('console'/'pageerror')` — confirms the data-URI approach actually works
  in a real browser, not just that the file was written.

**S1 is now complete — all four passes verified across three iterations (9, 10, 11, 12).**

**Next:** S2 — "Screen 2: task board + task cards," the operator's explicitly named worst offender.
Begin with P1 (explore only): read `TasksBoard.tsx`, `TaskCard.tsx`, `TaskDetailDrawer.tsx` in
full, `WebSearch` for kanban/task-card UI patterns, read the T3 Code sourcemaps for the closest
equivalent surfaces, and write `design/mocks/S2/RESEARCH.md`. No mock this iteration — same
one-pass-per-firing rhythm as every screen so far.

## Iteration 13 — 2026-08-22T02:32:30+01:00 — S2 P1: explore (task board + task cards)

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 12's commit
(`4ee2615`, the release-heartbeat commit).

**Read `TaskCard.tsx`, `TasksBoard.tsx`, `TaskDetailDrawer.tsx`, and `TaskIntegrationNote.tsx` in
full**, including comments — same discipline as every prior screen. Found several deliberate,
documented decisions that must survive the mock unchanged: purple-for-blocked vs. amber-for-stalled
as *opposite* signals (not degrees of the same problem); "Stalled" as a renamed label after a real
operator complaint about jargon (2026-08-10); the `task-live-pulse` ring (D12) that already respects
`prefers-reduced-motion` and is deliberately never the sole carrier of the "running" fact; sticky
column headers with a `-12px` offset hack fixed directly in response to the operator losing column
context while scrolling; the centred-modal drawer geometry, which reverses an *earlier* right-side
design on the operator's own explicit 2026-08-17 quote ("I don't want a ticket that takes the whole
screen... just that central popup"); `blocked` deliberately has no column of its own (R3).

**Found a real bug while reading, not a styling opinion.** `TaskCard.tsx:309` and
`TaskDetailDrawer.tsx:257` both render `<StatusBadge status={task.priority} />`. `Badge.tsx`'s
`STATUS_STYLES` map is keyed by task *status* values (`pending`, `in_progress`, …) and holds no
entries for priority values at all. Cross-checked the Hub's own source of truth,
`hub/hub/schemas/tasks.py:26` (`_PRIORITIES = ["low", "medium", "high", "critical"]`), confirming
every priority value misses the map and falls through to `STATUS_STYLES.pending ?? NEUTRAL`. So
today, a `critical` task and a `low` one render an *identical* grey pill — priority is never actually
colour-coded, which is exactly the gap the operator's own brief named. Recorded as finding 1 in
`RESEARCH.md`, flagged to fix for real in the mock (a proper `PRIORITY_STYLES` map) and to call out
in `RATIONALE.md` later as a genuine product bug, separate from the visual-refinement work.

**Four `WebSearch` queries**: general 2026 kanban card texture/hover/motion trends, Jira/Asana
information density, Linear's issue-row design (hairline borders + inset shadows instead of drop
shadows, priority-glyph + status-ring + coloured-pill mix — validation that AgentWeave's own
charcoal/hairline identity is already in the right family, not a reason to import a new one), and
drag-and-drop kanban interaction patterns (drop-zone sizing, destination-column highlight,
idle→hover→grab→move→drop microstates, ARIA equivalents).

**T3 Code sourcemaps**: no kanban/task-board surface exists in T3 Code at all (it's a chat-based
coding tool) — searched `index-DiDfaONg.js.map`'s `sources` list for `kanban|task|board|card|todo`
and confirmed this directly rather than assuming. Read the three closest analogues instead:
`ProposedPlanCard.tsx` (a `rounded-[24px]` card — the same 24px AgentWeave already reserves for
`--radius-content` — with a badge+title header, overflow-menu icon button, and a collapsed-body
fade-out-gradient-plus-expand-button idiom), `ComposerPreviewAnnotationCards.tsx` (a compact chip
card with an `icon + count` stat row and a hover-reveal corner remove button — the stat idiom maps
directly onto a task's own unshown counts, like requirement links or acceptance criteria), and
skimmed `ProviderInstanceCard.tsx` (less relevant, a settings table, confirmed by grep rather than a
full read). Extracted to `testbed/scratch/t3ref/` (gitignored), read, deleted immediately after per
`IDENTITY.md`'s reference-material rule — nothing quoted at length, nothing committed.

**Wrote `design/mocks/S2/RESEARCH.md`** — ten concrete, code-verified gaps (the priority-badge bug;
no hover elevation, only an inline border-colour swap with no CSS `:hover` rule; no press/active
state; bare per-column empty states despite `EmptyState` existing and being used only for the
whole-board case; no drag-and-drop at all, confirmed absent by reading both files — a missing
*feature*, not a style gap, mocked per `pre_authorised` rather than implemented; an all-same-shaped
badge row with no icons; requirement chips and informational badges sharing identical visual weight;
`TaskIntegrationNote` breaking the card's own pill/block pattern with bare coloured text; no
`tabular-nums` on the timestamp; the description clamp having no fade/expand affordance) plus a
"what's already good" section naming every decision above that must not be undone, with file:line
citations throughout.

**Verified, not assumed.**
- Re-read `Badge.tsx`'s `STATUS_STYLES` object directly and cross-referenced every key against
  `hub/hub/schemas/tasks.py`'s `_PRIORITIES` list before writing the bug up — didn't infer this from
  memory or pattern-matching.
- Grepped `TaskCard.tsx` and `TasksBoard.tsx` for `draggable`/dnd imports before claiming
  drag-and-drop is absent, rather than assuming from a first skim.
- Searched the T3 sourcemap's `sources` array programmatically for kanban/board/card filenames before
  claiming no direct equivalent exists, rather than asserting it.
- `git status --short` after cleanup → only `design/mocks/S2/RESEARCH.md` new, `.claude/autonomous/`
  state files modified. `testbed/scratch/t3ref/` removed, no stray files.

**Next:** S2 P2 — validate every `RESEARCH.md` finding against `IDENTITY.md`'s rejection test, then
build `design/mocks/S2/<variant>.html` (two or three variants, both themes, realistic task content
across all seven statuses plus blocked/stalled/merged cases), fixing the priority-badge bug for real
in the mock's own styles.

## Iteration 14 — 2026-08-22T02:47:16+01:00 — S2 P2: validate + mock (task board + task cards)

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 13's commit
(`ef06f6b`).

**Validate.** Re-read all ten `RESEARCH.md` findings against `IDENTITY.md`'s rejection test line by
line before building anything. All ten pass, nothing discarded: none touches the palette (clause 1);
the priority fix reuses the existing amber/red already on the same card (Stalled, Prerequisite
regressed) rather than a new hue, and `--blue` appears only on the status pill (already its role) and
the selected/focus ring (clause 2); the requirement-chip and empty-column treatments derive from
`--radius*` (clause 3/4); no new type (clause 4); every new glyph maps to an icon `Icon.tsx` already
declares mapped (see the bug below) rather than inventing a fifth icon source (clause 5); density is
unchanged — same seven columns, same card count per column as a realistic board, nothing narrowed to
make room (clause 6); every card state is demonstrated, not just resting (clause 7).

**Read before building**, in full: `TaskCard.tsx`, `Badge.tsx`, `TasksBoard.tsx`,
`TaskIntegrationNote.tsx`, `agentColorVars`/`colorTint.ts`'s `tint()` recipe (replicated exactly —
`color-mix(in srgb, TOKEN N%, transparent)` — rather than approximated), and `index.css` for the exact
elevation/radius/duration tokens `foundations.html` already named. Confirmed `EmptyState.tsx`'s
icon-circle shape before building the column-level empty state so the new one reads as a smaller
member of the same family, not a competing pattern.

**A second real bug, found while building, not by P1.** Cross-checked every `Icon name="..."` string
`TaskCard.tsx`/`TasksBoard.tsx` actually passes against `Icon.tsx`'s `ICONS` map (read in full — 84
entries). `help_circle`, `alert_triangle`, `filter_alt`, and `expand_less` are used at four call sites
(`TaskCard.tsx`'s blocked box and Stalled badge, `TasksBoard.tsx`'s requirement-filter banner and
rejected-section chevron) but none of the four exists in the map — only `help`, `warning`,
`filter_list`, and `expand_more` do. `Icon()`'s own fallback path (`Icon.tsx:313-322`) renders `null`
for an unmapped name, so all four render nothing in the shipped product today: the blocked box has no
icon, the Stalled badge has no icon (the Prerequisite-regressed badge does — it correctly uses
`warning`), the filter banner has no icon, and the rejected-section toggle has no chevron at all in
either state. Not in `RESEARCH.md` — recorded in `STATE.json`'s `next_action` for `RATIONALE.md` to
carry forward as finding 11, separate from finding 1's bug, with these exact file:line citations.

**Built two variants**, not three — same reasoning as S1: `restrained`/`considered` read as a clear
degree difference on this screen without inventing a decoration-only "expressive" reading, and a third
variant would mean a third full seven-column board with no new finding to justify it.

`design/mocks/S2/considered.html` — the fuller treatment. Real `PRIORITY_STYLES` (neutral → neutral →
amber → red) with a hand-drawn flag glyph disambiguating it by shape from the same-coloured
Stalled/Prerequisite-regressed badges; hover = lift + `surface-3` + shadow (`--dur-base`), press =
settle + `--press-lo` inset; a column-empty treatment with a small icon tile; requirement chips
bordered and clickable-looking vs. italic informational text; `TaskIntegrationNote` as a bordered,
icon-led block for all three outcomes (merged/failed-with-retry/skipped-no-branch); a description
fade-into-clamp on the one card whose text runs long (T3's `ProposedPlanCard` idiom); a forced
four-state strip (rest/hover/press/selected via `data-force`, matching `foundations.html`'s
convention); and a drag-and-drop *illustration* (a mid-drag card plus a highlighted drop-zone) —
finding 5 is a missing feature, mocked per `pre_authorised`, explicitly not built. `design/mocks/S2/restrained.html`
— the smallest fix per finding: the priority map as a plain colour dot instead of a glyph, hover/press
as real CSS rules with no lift or shadow, the empty column as centred text in a dashed box, requirement
chips differentiated by a border alone, the integration note as a coloured left-rule instead of a full
block, and a three-state strip (rest/hover/press only, no selected/dragging, no drag-and-drop section)
— deliberately less than `considered`, not an unfinished copy of it. Both files use all seven real
columns (`Pending/Assigned/In Progress/Under Review/Completed/Approved/Needs Revision`), keep `blocked`
out of its own column (R3), keep the sticky `-12px` header offset, and keep the centred-drawer geometry
implied by the "open" affordance — none of `RESEARCH.md`'s "must not be redesigned" list was touched.

**A real bug in the mock's own authoring, caught before it shipped.** First draft of the icon
substitution used a `${'{'}NAME{'}'}` placeholder text convention with a regex intended to match it —
the regex required a second `$` that the placeholder text itself never contained
(`${'{'}NAME{'}'}`, not `${'{'}NAME${'}'}`), so every icon slot would have rendered the literal
placeholder text instead of an SVG. Caught by the same discipline as every prior pass — rendering and
reading the result rather than trusting the source — before considering the file finished, not
after. Fixed the regex to match the placeholder actually written; re-verified with a scripted check for
literal `${` surviving into the rendered page's text (`page.inner_text('body')`), zero matches after
the fix, in both files.

**Verified, not assumed.** Direct-Playwright (`file://`, 1500×1100, both themes, both files) for: zero
unexpected console errors (only the pre-existing webfont 404 every prior mock also shows), zero leftover
`${` placeholder text in the rendered body, and a full-page screenshot read for each of the four
renders. Confirmed by reading the PNGs: the priority flag/dot renders legibly at 9-11px in both themes;
the live-pulse card's green ring is visible; the blocked purple box, Stalled amber badge, and
Prerequisite-regressed red badge all carry real icons now (not the broken names the product itself
still ships); the empty "Assigned" column reads as an empty state, not a rendering gap; the rejected
section's chevron rotates on click (`in-file <script>`, not a framework); and — cropped in for a close
read — the flag glyph is legible as a flag at its actual on-card size in both themes, not a stray mark.
No console errors, no clipped text, no stray hue in either file, either theme.

**Not done this iteration, deliberately.** No formal P3 critique-and-fix pass — what happened above was
build-time verification (catching the placeholder-regex bug, confirming legibility), not the honest
"screenshot, read, critique against the rejection test, fix" cycle `screen_pass_protocol.P3_iterate`
asks for as its own pass. Flagged explicitly in `next_action` so the next iteration doesn't skip it on
the strength of this one's screenshots.

**Verified.**
- `git status --short` after cleanup → only `design/mocks/S2/considered.html` and
  `design/mocks/S2/restrained.html` new (plus the usual `.claude/autonomous/` state files). No stray
  `.png`, no scratch files under `/tmp` or `C:\tmp` left behind (both cleaned explicitly — this
  machine's Bash `/tmp` and Python's `/tmp` resolve to different real paths, `C:\tmp` is the one Python
  actually writes to; noting this here since it cost a few minutes of confusion this iteration).

**Next:** S2 P3 — the honest iterate pass. Screenshot both variants, both themes (four captures) via
direct Playwright, read them fresh, critique against `IDENTITY.md`'s rejection test without the
build-time bias of already believing they're right, and fix anything found. Look specifically at the
states-strip and drag-and-drop sections, which were confirmed rendering but not critiqued this
iteration.

## Iteration 15 — 2026-08-22T02:53:51+01:00 — S2 P3: iterate on the task-board mocks

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 14's commit
(`9cb5ac6`, the release-heartbeat commit).

**Captured.** Direct-Playwright (`file://`, 1500×1100, both variants, both themes, full-page PNGs,
console errors captured) — same approach as every prior screen since `uishot.py` still doesn't fit a
static mock's own `.theme-toggle`. Zero console errors beyond the pre-existing webfont 404, zero
leftover `${` placeholder text in either file. Read all four full-page PNGs fresh, then cropped and
zoomed specific regions for a close read rather than trusting the full-page thumbnail's resolution.

**Found and fixed a real legibility bug**, only visible by looking, not from the source: the flag
glyph `considered.html` uses to disambiguate the `high`/`critical` priority pills by shape
(`FLAG`/`FLAG_SM`, a thin `stroke-width: 2.4` outline at 9×9px) renders as an illegible mark that
reads as the letter **"P"**, not a flag — confirmed in both themes, at every call site (the Finding-1
before/after comparison, every `high`/`critical` card badge, and the states-strip). Checked whether
this was a size problem or a shape problem by comparing against the other small glyphs on the same
cards: `WARN_SM` (11px, also thin-stroke) reads clearly as a warning triangle, `HELP` (15px)
reads clearly as a question-mark circle — so 9-11px isn't inherently too small for a stroke icon, but
the flag's specific geometry (a thin vertical line plus a thin hooked stroke) collapses into
noise at that size in a way a closed triangle or circle doesn't. Root cause, not just symptom: a
stroked outline needs more pixels to read than a filled shape at the same size, and the flag was the
only filled-in-real-use glyph built as a stroke.

Fixed by replacing `FLAG`'s definition with a filled shape (`fill="currentColor"`, a solid pole
`<rect>` plus a solid pennant `<path>`) instead of the stroked outline, and bumping both call sites
from 9px to 11px (the before/after comparison's inline `.ic` style, and `FLAG_SM`'s derived size) to
match `WARN_SM`'s already-confirmed-legible size — consistency across the card's small-glyph set, not
an arbitrary second change. Re-screenshotted and cropped the same regions: the flag now reads clearly
as a flag, both themes, at every call site (before/after table, board cards, states-strip).

**The two regions `next_action` flagged as unreviewed, now actually critiqued:**
- *States-strip* (`rest`/`hover`/`press`/`selected`, `data-force`-driven). Read correctly on the fixed
  flag glyph. Sampled background pixel colour directly at each cell to confirm the four states are
  genuinely distinct, not just visually similar in a screenshot: rest `rgb(29,29,33)` (`--surface-2`),
  hover `rgb(38,38,43)` (`--surface-3`, lighter), press `rgb(25,25,28)` (darker, the `--press-lo` mix),
  selected `rgb(29,29,33)` (same background as rest, distinguished by border/shadow alone — correct
  per its own CSS rule, which only changes `border-color`/`box-shadow`, not background). No bug —
  confirmed by measurement, not assumed from the render.
- *Drag-and-drop illustration*. Both the mid-drag card (rotated, reduced opacity, elevated shadow) and
  the highlighted drop-zone ("Drop to mark approved," dashed `--ring`-tinted border) render cleanly in
  both themes — text fully legible, no clipping, no stray artefacts. No bug.

**`restrained.html`** — full-page read in both themes, no cropping needed since it deliberately avoided
the icon-legibility risk in the first place (a plain colour dot instead of a glyph for priority, per
iteration 14's log). Confirmed clean: no bug, no fix needed. Notable for `RATIONALE.md` later —
`restrained`'s smaller, glyph-free choice turned out to be the safer one at this information density,
which is itself a finding about *degree*, not just a lesser version of `considered`.

**Verified, not assumed.**
- Direct-Playwright re-capture after the fix, both variants, both themes → 0 console errors, 0
  leftover placeholder text.
- Pixel-sampled crop-and-zoom (5×) read of the fixed flag glyph at its actual on-card size, both
  themes, both the Finding-1 comparison table and a live board card (`Wire start_new_thread…`,
  critical) — reads as a flag, not a letter, in every case checked.
- `PIL.Image.getpixel` sampling of the four states-strip cells' background colour, confirming they
  differ exactly as the CSS intends rather than trusting the screenshot's apparent similarity.
- `git status --short` after cleanup → only `design/mocks/S2/considered.html` modified (plus the usual
  `.claude/autonomous/` state files). Scratch dir `/tmp/s2shots` and the two throwaway Python scripts
  removed — nothing left in `/tmp` or tracked in the repo.

**Not done this iteration, deliberately:** no second iterate pass or `RATIONALE.md` yet —
`screen_pass_protocol.P3_iterate` is exactly what happened this iteration (screenshot, read, critique,
fix); `P4_finish` is the next firing: a second look for anything missed, `RATIONALE.md`, and adding S2
to `design/mocks/index.html`.

**Next:** S2 P4 — finish. Re-screenshot both variants/themes once more (four captures) to confirm the
flag-glyph fix has no regression and look once more for anything missed, then write
`design/mocks/S2/RATIONALE.md` (research → changes for all ten `RESEARCH.md` findings, including the
two extra bugs found beyond `RESEARCH.md` itself — the priority-badge bug from P1/P2 and this
iteration's flag-glyph legibility bug — what was rejected and under which `IDENTITY.md` clause, and
the `restrained`-is-safer-at-this-density observation above), then extend
`design/mocks/index.html` with S2's before/after shots (inline data-URIs, same approach as S1, per the
`.gitignore` blanket `*.png` rule already noted in `dead_ends_inherited`).
