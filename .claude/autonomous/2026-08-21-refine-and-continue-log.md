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

## Iteration 16 — 2026-08-22T03:04:28+01:00 — S2 P4: finish (RATIONALE.md + review index)

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 15's commit
(`2c222c8`, the release-heartbeat commit).

**Re-screenshot pass.** Direct-Playwright (`file://`, 1500×1100, both variants, both themes, fresh
captures — not reusing any prior iteration's PNGs) → 0 console errors beyond the pre-existing webfont
404s, 0 leftover `${` placeholder text. Cropped and zoomed (3–5×) the finding-1 comparison table and a
live board card's `critical` badge in both themes: the flag glyph reads clearly as a flag everywhere,
no regression from iteration 15's fix. Also read `restrained.html` full-page in both themes again — no
bug, confirms iteration 15's finding that its plain-dot priority treatment carries no flag-legibility
risk in the first place. (Noted, not a mock bug: the capture script sets `data-mode` via
`page.evaluate` rather than clicking the mock's own toggle button, so the button's static label text
reads "dark" in the light-theme screenshots too — a screenshot-harness artefact from setting the
attribute directly instead of driving the click handler, not a defect in the mock itself.)

**Wrote `design/mocks/S2/RATIONALE.md`.** Research → changes for all ten `RESEARCH.md` findings
(priority-badge colour-coding, hover elevation, press state, column empty states, drag-and-drop
illustration, badge-row shape-scannability, requirement-chip weight, `TaskIntegrationNote`'s broken
pattern, `tabular-nums`, description fade), each tied to what `restrained` vs `considered` actually
did and cross-checked against the live file content (`grep`-confirmed `tabular-nums`, `.integration-
note`, and `.card-desc-fade` are present at the cited line numbers before writing the summary, not
assumed from the log). Explicitly wrote up finding 11 (the icon-mapping bug — `help_circle`,
`alert_triangle`, `filter_alt`, `expand_less` used in the real product but absent from `Icon.tsx`'s
map, so all four render nothing today) and the flag-glyph legibility bug as the two bugs found beyond
`RESEARCH.md` itself. Added a "what was rejected, and under which clause" section (third variant,
building drag-and-drop for real, a new priority hue, icon-heavy badge rows) and a judgement-call
section stating plainly that `restrained`'s glyph-free dot is structurally safer at this card density
than any glyph-based signal, independent of whether a specific glyph happens to render legibly — worth
carrying into a real implementation choice, not just a stylistic preference. Closed with a "what's
already good and was left alone" section matching `RESEARCH.md`'s own list verbatim.

**Extended `design/mocks/index.html`.** The file is 1.3MB before this change (base64-embedded PNGs
from S1), too large for the `Read` tool to load directly (1.3MB alone is ~850K tokens) — so all
inspection and editing of it was done by `awk 'length($0) < 300'` (to see structural lines while
skipping the giant base64 lines) and a Python script performing string-level splice-and-write on disk,
never round-tripping the file's content through the model's own context. Captured 4 fresh full-page
shots (`considered`/`restrained` × dark/light) plus a tight before/after crop pair for the flag-glyph
fix — reconstructed "before" by writing iteration-14's pre-fix `considered.html` (via `git show
3ce097d:...`) to a temporary file *inside* `design/mocks/S2/` (not a scratch dir) so its relative
`../../../hub/ui/src/index.css` import resolved correctly and the crop showed the real styled bug, not
an unstyled page — confirmed this mattered by first getting a broken-CSS render when the temp file was
placed under `/tmp` instead, diagnosed, and corrected. Deleted the temp file immediately after
capturing, confirmed via `git status --short` that only the intended two files remained modified/new.
Base64-encoded and spliced the S2 section into `index.html` (matching S1's existing markup shape
exactly — `screen-card`/`shot-row`/`fix-block`), and rewrote the trailing "S2 — S8, not started"
placeholder to "S3 — S8" now that S2 is done. Rendered the whole updated file with Playwright
afterward: 12 `<img>` elements total (S1's 6 + S2's 6), 0 broken, only the pre-existing webfont console
errors — confirmed by screenshotting three scroll positions and reading them, not just checking the
image count. Same blanket `*.png` `.gitignore` constraint as S1: screenshots inlined as data-URIs in
the tracked HTML, never committed as `.png` files on disk.

**Verified, not assumed.**
- Fresh 4-capture re-screenshot + crop-and-zoom read, both variants/themes, confirming no regression.
- `grep`-confirmed the three RATIONALE.md line-number citations (`tabular-nums`, `.integration-note`,
  `.card-desc-fade`) directly in `considered.html` before writing them.
- Playwright render of the updated `index.html`: 12/12 images load, 0 broken, 0 unexpected console
  errors, three scroll positions screenshotted and read.
- `git status --short` after cleanup → only `design/mocks/index.html` (modified) and
  `design/mocks/S2/RATIONALE.md` (new). No stray temp file, no `.png` on disk, nothing left under
  `C:\tmp`.

**S2 — task board + task cards is now done, all four passes.** The queue moves to S3, "the right side
panel" (`PanelShell` and its tabs — `FileTree`, `FilePreview`, `SpecIndexTab`, `LoopsIndexTab`,
`FilesIndexTab`), always on screen while working.

**Next:** S3 P1 — explore. Read `PanelShell.tsx` and each tab component in full (comments included,
same discipline as every prior P1), then `WebSearch` for side-panel/file-tree/tabbed-panel UI patterns
and read the T3 Code sourcemaps for the closest equivalents (`RightPanelTabs.tsx`,
`RightPanelSheet.tsx`, `FileBrowserPanel.tsx`, already named in `STATE.json`'s S3 queue entry as the
closest reference material). Write `design/mocks/S3/RESEARCH.md`. Do not build a mock this iteration —
P2 is the next firing, per the established one-pass-per-firing rhythm.

## Iteration 17 — 2026-08-22T03:13:31+01:00 — S3 P1: explore (the right side panel)

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 16's commit
(`0ce17cc`, the release-heartbeat commit).

**Read in full, including comments:** `PanelShell.tsx`, `FileTree.tsx`, `FilePreview.tsx`,
`SpecIndexTab.tsx`, `SpecDocumentBrowser.tsx` (the shared engine behind `SpecIndexTab` and the
Ctrl/Cmd+K picker), `LoopsIndexTab.tsx`, `FilesIndexTab.tsx`, `fileIcons.ts`, and `RowMenu.tsx` (the
tab strip's "+" affordance). Several deliberate decisions worth not undoing: `FilePreview`'s explicit
refusal to reuse `MarkdownMessage` (a load-bearing "no `rehypePlugins`, ever" trust boundary — a
workspace file is content the operator opened themselves, agent/peer output is not); `PanelShell`'s
launcher-grid empty state, replacing one line of grey text after the operator's 2026-08-19 "when we
open the right screen and there is nothing there weird"; `fileIcons.ts`'s whole-filename-before-
extension precedence and its explicit note that colour, not shape, carries recognition at 12px;
`LoopsIndexTab`'s `ending_state`-only bucketing (design D17) and its 2026-08-19 agent-attribution row.

**`grep`-confirmed, not assumed:** `--row-hover`/`--row-active`/`--row-selected` exist in
`hub/ui/src/index.css` and appear in none of the five panel-tab component files — every row in
`FileTree`, `FilesIndexTab`, `LoopsIndexTab`, and `SpecDocumentBrowser` sets a static `background` at
rest with no `:hover` rule at all. Also confirmed `Icon.tsx`'s icon map has `folder_open` but no
closed-folder entry, so `FileTree.tsx`'s unconditional `<Icon name="folder_open" ... />` shows the
same glyph whether a directory is collapsed or expanded — a real, checkable gap, not a styling
opinion, but one whose real fix needs a new `Icon.tsx` map entry (source change, out of scope for a
mock — flagged for `RATIONALE.md` only).

**T3 Code sourcemaps.** Recreated the extraction approach from scratch this iteration (no cached
script survives between firings): a small Python script (`json.load` each `*.js.map`, filter
`sources[]` for target substrings, print `sourcesContent`) located and read `RightPanelTabs.tsx`,
`RightPanelSheet.tsx` (via the same `index-*.js.map`), and `FileBrowserPanel.tsx` (via
`FilePreviewPanel-*.js.map`) — the exact three files this queue item's own `STATE.json` detail named
as closest reference material. Read via the repo's own `/tmp` → `C:\Users\huida\AppData\Local\Temp`
mapping (confirmed with `cygpath -w` after the `Read` tool first rejected the bash-relative path).
Patterns worth carrying, restated for this palette rather than copied (per `IDENTITY.md`'s "design
reference only" rule — nothing quoted here at length, nothing committed from T3's source): pill-
shaped scrollable tabs with a hover wash on inactive tabs; the close icon cross-fading in over the
identity icon on tab hover rather than sitting beside it always-visible (a real density cost in
AgentWeave's current two-icon-per-tab layout); every tab title wrapped in a tooltip so truncation
never loses the full name; a tab context menu (close / close others / close to the right / close
all) and middle-click-to-close, both entirely absent from `PanelShell`; empty-state launcher cards
with real hover/press/disabled-with-reason states and a live-count badge on the card whose tab
already has one to show (T3 badges its Agents card with a running-subagent count; AgentWeave's
`loops` launcher discards the `counts.running` number `LoopsIndexTab` already computes); file-tree
row backgrounds built from low-percentage `color-mix(in srgb, currentColor N%, transparent)` — which
is structurally identical to what AgentWeave's own `--row-hover` et al. already do, so this is "apply
the existing token" rather than "adopt a new technique."

**General web research** (side-panel/file-tree/tabbed-panel patterns, code-preview-pane conventions,
uxpatterns.dev's Tabs pattern): breadcrumb/path headers and copy-to-clipboard buttons are
conventional on a file/code preview pane, both absent from `FilePreview.tsx`; search fields
conventionally carry a leading icon and Escape-to-clear, both absent from `FilesIndexTab` and
`SpecDocumentBrowser`'s inputs; horizontal scrolling tab strips (already `PanelShell`'s structural
choice) are specifically the right pattern when tab count is dynamic and may exceed width — confirms
the structure is right and only the visual layer around it is under-designed.

**Checked against U0a/U0b** (`foundations.html`, `controls.html`) so P2 reuses rather than reinvents:
skeleton primitives (`.sk-line`/`.sk-row`/`.sk-chip`) for the three tabs' plain `Loading…` text, a
real toggle (`.ctl-switch`) for `LoopsIndexTab`'s bare `<input type="checkbox">` "Show archived", and
`.menu-panel`/`.menu-item` for the tab-strip context menu this pass found missing.

**Wrote `design/mocks/S3/RESEARCH.md`** — what was read, the T3 reference findings, the general web
findings, an explicit "what's already good, leave it alone" section, and a numbered "what's missing,
concretely" list of 9 items for P2 to work from.

**Verified, not assumed.**
- `grep -rn "row-hover\|row-active\|row-selected"` against the five component files → zero matches,
  confirming finding 1 before writing it.
- `grep -n "folder" hub/ui/src/components/common/Icon.tsx` → only `folder_open`, `folder_plus`,
  `folder_search`; no bare `folder` entry, confirming the collapsed/expanded glyph finding.
- Read each of the three T3 source files in full via the extraction script's output, not a summary.
- `git status --short` after writing → only `design/mocks/S3/RESEARCH.md` new plus the usual
  `.claude/autonomous/` state files. Nothing under `hub/ui/src` touched (this is a mock-only pass).

**Not done this iteration, deliberately:** no mock built — `screen_pass_protocol.P1_explore` is
explore-only, matching S1 and S2's own first passes.

**Next:** S3 P2 — validate the RESEARCH.md findings against `design/IDENTITY.md`'s rejection test
(state which clause anything gets discarded under, same discipline as S1/S2), then build
`design/mocks/S3/<variant>.html` (2–3 variants exploring degree of refinement, self-contained HTML
importing `../../../hub/ui/src/index.css`) with realistic content spanning all three index tabs plus
an open `file:` tab and an open `spec:` tab, reusing U0a/U0b's already-established vocabulary rather
than inventing new primitives.

## Iteration 18 — 2026-08-22T03:24:31+01:00 — S3 P2: validate + mock (right side panel)

Branch/log/STATE.json reconciled cleanly on entry — clean tree, HEAD matched iteration 17's commit
(`0993645`).

**Validated every `RESEARCH.md` finding against `IDENTITY.md`'s rejection test before building
anything**, same discipline as S1/S2. All 9 pass, nothing discarded: none touches the palette
(clause 1 — every colour is a token, confirmed by grep against both mocks before screenshotting,
only literal is `9999px` for full rounding, same precedent as S2's `.pill`/filter chips); both
themes stay legible (clause 2, verified by screenshot below, not assumed); every duration is
`--dur-fast/base/slow` and every easing is `--ease` (clause 3, grep-confirmed zero raw `ms` values);
radii derive from `--radius*` (clause 4); reads as the same panel refined, not a different product
— pill tabs are the existing `9999px` shape already used elsewhere in the app, not a new geometry
(clause 5); nothing removed — same three index tabs, same file preview, same loops list, several
findings (tab context menu, breadcrumb copy button, launcher live-count badge, closed-folder glyph)
demonstrated as pre-authorised missing-feature findings rather than removed scope (clause 6); every
state is shown, not just resting (clause 7 — hover/press/selected/focus-visible forced via
`data-force` throughout, same pattern as S1/S2).

**Built two variants**, matching S1/S2's precedent of restrained + considered (not a third
"expressive" — nothing in this pass's findings needed a third degree; see RATIONALE note to write
in P4 if that judgement should be revisited):

- `design/mocks/S3/restrained.html` — smallest fix: apply `--row-hover/-active/-selected` to every
  row exactly as named, a real CSS hover/press on the launcher cards and tab strip (still both icons
  per tab, no crossfade), a search icon, and the file's path once above the preview content. No
  context menu, no live-count badge, no shimmer animation — checkbox stays native.
- `design/mocks/S3/considered.html` — full application: pill-shaped tabs with a hover wash, the
  identity/close icon crossfade via a `grid` slot (saves horizontal density per clause 6, matching
  T3's pattern), tooltips on truncated tab labels, a right-click context menu built from
  `controls.html`'s `.menu-panel`/`.menu-item` (demonstrated, not wired to real close-others/-right
  logic — a mock, not a feature), a live-count badge on the loops launcher card sourced from the
  number `LoopsIndexTab` already computes, a breadcrumb + copy-path header on `FilePreview`, and
  `foundations.html`'s shimmer skeleton replacing "Loading…" text. `LoopsIndexTab`'s "Show archived"
  checkbox becomes `controls.html`'s `.ctl-switch`.

**Screenshotted, both variants, both themes — and found a real bug by looking.**
`scripts/uishot.py` assumes the live app's own "Switch to dark mode" button role (same quirk S1
iteration 10/11 and S2 iteration 14 already worked around) — these static mocks flip
`document.documentElement.dataset.mode` via their own `.theme-toggle` handler instead, so used a
direct-Playwright script at `%TEMP%\s3shots\capture.py` (1400×1000 viewport, full-page PNGs,
console errors captured) rather than `uishot.py` directly. Zero console errors beyond the
pre-existing `net::ERR_FILE_NOT_FOUND` for a webfont the standalone mocks don't carry (same as every
prior pass — not a regression).

Read all four PNGs. **`restrained.html` had a real layout bug, invisible from source review alone:**
the tab-strip close icon (`.tab-close`, used three times) had no explicit `width`/`height` — CSS
class only set `display: inline-flex` with no sizing — while its inlined SVG used `width="100%"
height="100%"`. With no intrinsic container size to resolve the percentage against, the `X` glyph
ballooned to fill the entire `.panel-frame`, covering the tree and the code pane in both the "Files
— tab hover, search icon, tree states" and "File preview" composite panels. This was present in
`considered.html`'s equivalent icon too on first write, but that file's version sits inside
`.tab-icon-slot` which the CSS *does* give an explicit `14px`×`14px` inline size (a `grid`
crossfade slot needs one to stack two icons), so it never manifested there — confirmed by grep that
every other icon usage across both files has an explicit pixel size, either via an inline style or a
sized parent. Fixed by giving `.tab-close` `width: 14px; height: 14px; flex: none` directly, matching
the sizing convention every other bare icon span in these two files already follows. Re-screenshotted
`restrained-dark.png`/`restrained-light.png` after the fix — both composite panels render correctly,
full tree and code pane visible, tab strip legible.

No other defects found on inspection: badges, agent-colour dots, the pill-tab crossfade-forced state,
the context-menu illustration, and the skeleton shimmer all render as intended in both themes; light
theme keeps contrast on every token-derived colour (green "running" badge, amber "1 open question",
blue syntax highlight in the code pane).

**Verified, not assumed.**
- `grep -nE "#[0-9a-fA-F]{3,8}\b"` against both files → zero matches (no literal hex).
- `grep -noE "[0-9]+ms"` against both files → zero matches (no raw duration).
- `grep -nE "border-radius:\s*[0-9]"` against both files → only `9999px` (full rounding, same
  precedent as S2), no other literal radius.
- Four screenshots read via the `Read` tool, not assumed correct from source — this is what caught
  the `.tab-close` sizing bug.
- `git status --short` after the fix → only the two new `design/mocks/S3/*.html` files plus the
  usual `.claude/autonomous/` state churn. Nothing under `hub/ui/src` touched (mock-only pass, S3
  carries no C6-style exception).

**Not done this iteration, deliberately:** no `RATIONALE.md`, no review-index entry — those are P4's
job, matching `screen_pass_protocol`'s four-pass split and S1/S2's own iteration boundaries. P3 (a
second look-and-critique pass) is also not yet run; the bug caught above was found during this same
build+screenshot pass rather than a separate iterate pass, which is earlier than S1/S2's own P3 found
theirs — worth noting in P4 whether S3 needs a full second P3 iteration or can move straight to P4's
finish since the obvious defect already surfaced and was fixed here.

**Next:** S3 P3 — a second, deliberate look at both variants beside their pre-mock screenshots (none
taken of the *current* `PanelShell` itself yet — worth capturing one for the before/after in P4)
critiquing honestly against the rejection test one more time, particularly: whether the considered
variant's context-menu illustration reads as clearly "demonstrated, not wired" or risks looking like
a broken real control; whether the tooltip's `::after` CSS-only approach errs from how a real
`title`-replacement tooltip component would behave; and whether the two-variant set (no third
"expressive") is the right call for this screen the way it was for S1/S2, or whether the panel's
"always on screen" status (unlike S1/S2's page-navigated surfaces) argues for a subtler third degree.

## Iteration 19 — 2026-08-22T03:32:19+01:00 — S3 P3: iterate (right side panel)

**Re-screenshotted both `design/mocks/S3/*.html` variants in both themes** via the existing
`%TEMP%\s3shots\capture.py` direct-Playwright script (uishot.py still can't be used — these static
mocks flip theme via their own `.theme-toggle` handler, not the live app's button role). Read all
four PNGs fresh rather than trusting the P2 captures.

**Found and fixed a real bug by looking, not by reading source.** In the light-theme captures the
toggle button's own label was stuck reading "dark" even though the page had visibly switched to the
light palette. Root cause, confirmed by direct Playwright evaluation (clicked `.theme-toggle`,
compared `dataset.mode` vs `#theme-label` textContent before/after): both `considered.html` and
`restrained.html` attach the label-updating `addEventListener('click', …)` *before* the trailing
icon-substitution step `document.body.innerHTML = document.body.innerHTML.replace(...)`. That
`innerHTML` reassignment reparses and rebuilds the entire `<body>` from a string to swap in the real
SVGs — which discards every DOM node the listener was attached to and creates fresh ones parsed from
the (unmodified) HTML string. The inline `onclick="…dataset.mode = …"` on the button survives because
it's plain markup reflected into the new nodes, so the theme itself still flips correctly; only the
runtime `addEventListener` was orphaned on a detached node. Fixed by moving the
`addEventListener` call to *after* the `innerHTML` replace in both files (so it binds to the live
node), verified directly via Playwright (`before ('dark','dark') after ('light','light')` for both
files, was `after ('light','dark')` before the fix), then re-screenshotted and re-read all four PNGs
to confirm the fix holds and introduced no new defect. Checked whether this is inherited: `S2`'s
`considered.html` has the identical ordering bug (confirmed by the same before/after check) — `S1`'s
doesn't, because `S1` has no `#theme-label` span at all. Not fixing S2 here — out of scope for this
iteration, noting it so P4/RATIONALE or a later pass can decide whether to backport.

No other defects found on this pass — badges, agent-colour dots, the pill-tab crossfade, the search
field, tree row states, the loops toolbar switch and skeleton all still read correctly in both
themes after the `.tab-close` sizing fix from P2 held up under a second look.

**Answered the three questions `next_action` posed:**
- *Context menu — demonstrated affordance or broken control?* Reads clearly as demonstrated: it sits
  in its own labeled `frame-col` beside the tab strip rather than overlaid as if a real right-click
  had triggered it, and the caption underneath states outright that it's "Absent from `PanelShell`
  today … not implemented here, only demonstrated." No change needed.
- *CSS-only `::after` tooltip — plausible vs a real tooltip component?* Checked whether the app has
  an existing `Tooltip` component to diverge from: grepped `hub/ui/src/components` for `Tooltip` —
  no dedicated component exists anywhere in the tree (54 files use native `title=` only). So this
  isn't inconsistent with an established pattern, it's proposing one where none exists — correctly
  scoped as a missing-feature note for `RATIONALE.md`, not a risk to fix.
- *Does S3 need a third "expressive" variant, given the panel is always-on-screen chrome rather than
  a navigated-to page like S1/S2?* Judged no. The panel is peripheral to where attention actually
  goes while working; an expressive treatment on chrome that's *supposed* to recede risks reading as
  the "complete jump in design" clause 5 forbids, more than S1/S2's navigated screens would. Two
  variants stands, same call as S1/S2, but for a different reason worth stating explicitly in
  `RATIONALE.md` rather than leaving it looking like an unexamined default.

**Verified.**
- `grep -c "addEventListener('click'" design/mocks/S3/*.html` → 1 per file, now positioned after the
  `innerHTML` replace in both.
- Playwright before/after check on both files, both directions (see above).
- Four screenshots re-captured and re-read after the fix.
- `git status --short` → only the two edited `design/mocks/S3/*.html` files plus the usual
  `.claude/autonomous/` state churn.

**Not done this iteration, deliberately:** no `RATIONALE.md`, no review-index entry, no before-shot
of the current live `PanelShell.tsx` — all three are P4's job. The before-shot in particular needs
the trial Hub started from `hub/` on port 8010, which is more setup than this pass's scope
justified; flagging it here so P4 does it fresh rather than assuming a stale capture.

**Next:** S3 P4 — second iteration pass (none of this iteration's findings required a further mock
change beyond the toggle-label fix, so P4 can likely go straight to write-up), a before/after capture
of the current live `PanelShell` (start the trial Hub from `hub/` on port 8010, screenshot, stop it
cleanly), `design/mocks/S3/RATIONALE.md` covering the research, what changed, what was rejected
(third variant, under clause 5, reasoning above), and adding S3 to `design/mocks/index.html` (item Z
rebuild) alongside S1/S2's existing entries.

## Iteration 20 — 2026-08-22T03:43:37+01:00 — S3 P4: finish (right side panel)

**S3 is done — 4/4 passes.** This iteration wrote `design/mocks/S3/RATIONALE.md` and rebuilt
`design/mocks/index.html` (queue item Z) to add S3 alongside S1/S2.

**`RATIONALE.md`** maps all nine `RESEARCH.md` findings to what each variant did (unused row-state
tokens now applied; tab strip hover/tooltip/crossfading close icon plus a demonstrated-only context
menu in `considered`; launcher cards get real states and `considered`'s live loops-running-count
badge; a `FilePreview` header with breadcrumb/copy/language chip; search-input icon + clear;
`LoopsIndexTab`'s checkbox swapped for U0b's real `.ctl-switch`; skeleton primitives replacing the
bare "Loading…" paragraph; a demonstrated open/closed folder glyph flagged as a real `Icon.tsx`
map gap out of mock scope; and a restrained-only 1px tree connecting guide). Documents the P3
toggle-label bug fully, a "what was rejected and under which clause" section (no third variant —
argued explicitly this time rather than left as an unexamined default, since S3's always-on-screen
status made the question genuinely different from S1/S2's; building the context menu or
middle-click-to-close for real; a dedicated `Tooltip` component; fixing the folder icon in source;
a second empty-state pattern), and a "what's already good" carry-forward list.

**The live-`PanelShell` before-shot from iteration 19's `next_action` was investigated and
deliberately not captured.** Checked first: the trial Hub on 8010 was already running (PID 9596,
started before this session, project `proj-5e960453` loaded — confirmed via a read-only Playwright
`goto` that hit `AgentWeave Hub` / the real project overview, no state touched). But that project
has zero agents, and `grep`-confirmed `PanelShell` only mounts inside `ConversationView`, which
needs an active agent conversation to reach — there is no route to it with an empty roster.
Creating a runner and an agent purely to open a panel for one screenshot was judged more mutation
of a shared trial instance than this pass's scope justified, especially since neither S1 nor S2
ever took a live-app-vs-mock shot either — both screens' actual `index.html` entries and
`RATIONALE.md`s only ever compare mock-to-mock (e.g. S1's timeline-scroll fix, S2's flag-glyph
fix). Matched that established precedent instead of the prior iteration's aspirational note; left
the already-running Hub process exactly as found (did not start or stop it — it wasn't mine to
stop).

**`design/mocks/index.html` rebuild — verified, not assumed.**
- Learned the exact embedding format first (`<img src="data:image/png;base64,...">` inside
  `.shot`/`.shot-label` pairs, `.fix-pair` for before/after) by reading a de-data-URI'd copy of the
  existing file (`awk 'length($0) < 2000'` to strip the giant base64 lines, since the file is 2.7MB
  and exceeds the Read tool's token cap even with offset/limit) rather than guessing the shape.
- Used the four P3 screenshots already on disk (`%TEMP%\s3shots\{restrained,considered}-{dark,light}.png`,
  captured post-fix) for the main shot-row — did not need to re-render, since P3 already left fresh
  correct captures.
- Regenerated a genuine "before" (buggy) shot rather than fabricating one: checked out
  `design/mocks/S3/{considered,restrained}.html` as they stood at commit `86ac33c` (pre-fix, the P2
  commit) into a throwaway `design/mocks/_tmp_before_bug/` — placed at the same directory depth as
  `S3/` so the `../../../hub/ui/src/index.css` relative import still resolved — screenshotted the
  reproduced bug directly with Playwright (`mode=light label=dark` printed and confirmed for both
  files), then deleted the temp directory. `git status --short` confirmed nothing from it survived.
- Replaced the `S3 — S8` pending placeholder card with a real `done` S3 card (Python string
  replace on the exact placeholder text, `assert old in content` before writing so a silent
  no-op would have failed loudly) and renamed the remaining placeholder to `S4 — S8`.
- Reloaded the rebuilt `index.html` fresh in Playwright: 5 `.screen-card`s, 18 `<img>` tags total
  (S1: 6, S2: 6, S3: 6 — matches exactly), zero with `naturalWidth === 0` (none broken), theme
  toggle still flips `html[data-mode]` correctly end to end. The only console errors are three
  pre-existing `@fontsource/*` `file://` resolution failures inherited from `index.css`'s npm-style
  imports — present for every mock under `design/mocks/`, not introduced by this change.
- `git status --short` → only `design/mocks/index.html` (modified) and `design/mocks/S3/RATIONALE.md`
  (new). No stray files from the before-shot regeneration.

**Not done, deliberately:** no fifth S1/S2-style change to `hub/ui/src` — S3 stayed mock-only per
`limits` (C6 is the sole exception and this isn't it). The identical theme-toggle-label bug in
`S2/considered.html`, spotted again while confirming the fix pattern, is still not backported —
still out of scope for a different screen's pass, now noted in two consecutive iterations' logs
plus `RATIONALE.md` itself, worth someone deciding to just fix it directly rather than re-noting a
third time.

**Next:** S4 P1 — explore the task DAG / dependency board (`DependencyBoard`, `DependencyBoardView`).
Read `openspec/explorations/2026-08-21-the-execution-graph-in-the-panel.md` before starting — P2
must mock both the standalone and panel-embedded placements per `decisions_for_user` D-dag-placement,
and this screen also carries the waived task-dependencies check 11.1 (edges go stale when a
collapsed layer is expanded), worth reading precisely before research starts rather than discovering
it mid-mock.

## Iteration 21 — 2026-08-22T03:51:50+01:00 — S4 P1: explore (task DAG / dependency board)

**S4 queue item started.** Read `openspec/explorations/2026-08-21-the-execution-graph-in-the-panel.md`
first, as `next_action` required, before opening any code.

**What was read, in full:** `DependencyBoard.tsx`, `dependencyBoardLayout.ts`,
`DependencyBoardView.tsx`, `hub/ui/src/store/panelTabsStore.ts`. Not re-read from scratch:
`TaskCard.tsx` — S2's `RESEARCH.md` already covers it in depth and it renders unchanged inside this
screen, so S4's card treatment should match S2's chosen direction rather than diverge into a third
style.

**A second staleness cause, beyond the one the exploration doc names.** The doc diagnoses cause 1
precisely (the `layoutKey` not encoding which layers are collapsed, so `useEdgeLines`'s layout
effect never re-runs on expand). Reading `useEdgeLines` further turned up an earlier problem in the
same mechanism: while a layer is *collapsed*, its `TaskCard`s are unmounted entirely
(`{expanded && (...)}`), so any edge touching a task inside it hits the exact same
`if (!fromEl || !toEl) continue` guard written for genuine off-board references — the edge doesn't
just go wrong on expand, it **silently doesn't exist at all while collapsed**, with nothing on the
"2 done" toggle indicating a hidden connection runs through it. Read as very likely a large share of
"the links should not be static." Recorded as a *demonstrated variant*, not a source fix — this
screen stays mock-only per `limits`.

**Panel-embedding is a proposal, not existing machinery — confirmed, not assumed.**
`panelTabsStore.ts`'s `IndexTabId` is a closed `'specs' | 'files' | 'loops'` literal type; there is
no `tasks`/`dag` member today. `design/mocks/S4/RESEARCH.md` says this plainly rather than mocking a
panel tab as if it already shipped, per `decisions_for_user` D-dag-placement (mock both placements,
let the operator choose).

**External research** (four sources, each mapped to a concrete finding, not general reading):
GitHub Actions' run graph (icon-left status + colour, dependency lines) validates extending S2's
already-chosen icon+colour idiom to DAG nodes rather than inventing a fourth vocabulary; Airflow's
graph view validates that a stall-reason sentence (already computed by `layerStallSummary`, just
unstyled) is the highest-value thing on this screen; React Flow's edge-type docs recommend
step/smoothstep (orthogonal) routing over raw diagonal lines for exactly this kind of technical
diagram, and document an `animated` edge property that maps directly onto `assignee_status ===
'running'` (`TaskCard.tsx:94`'s own `isLive` condition, no new data) — real motion tied to real
state, inside the existing motion scale and `prefers-reduced-motion` discipline, rather than the
fully static rendering the operator called out; general DAG-at-scale practice (minimaps, pan/zoom)
was considered and **rejected** for boards this small (confirmed by reading `groupByDepth`'s output
shape — a handful of layers, few tasks each) — noted explicitly so a later pass doesn't reintroduce
it as an assumed best practice it isn't for this data size.

**Ten concrete findings recorded** in `design/mocks/S4/RESEARCH.md` (edges visually inert with no
arrowhead/direction/weight-by-state; collapsed layers drop edges silently; no lineage-on-hover
despite that being the operator's own stated want — *"to access the lineage fast"*; off-board
references float with zero connecting line to what names them; the collapse toggle carries only a
count; the document picker bar is undifferentiated pills with no icon and no visual proportion for
outstanding/total; the structure hint sentence has no visual anchor; no panel-embedded form exists;
the layer stall-summary sentence — the one piece of real synthesis on this screen — gets the least
visual weight of anything on it; loading states are bare text while the zero-tasks case already uses
`EmptyState`). A "what's already good" list keeps the three-way stall classification, longest-path
layering, the partly-finished-layer-never-collapses rule, off-board refs being named not hidden,
`EmptyState` on zero-tasks, and the picker's document-first/no-document-last sort off the table for
redesign.

**Verified.** `python -c "import json; json.load(...)"` on `STATE.json` after editing. Grepped
`TaskCard.tsx` directly to correct an early draft claim that `isLive` was a field on `Task` — it
is a computed local (`task.assignee_status === 'running'`) — fixed before finishing, not left as a
plausible-sounding inaccuracy. `git status --short` → only `design/mocks/S4/RESEARCH.md` (new) plus
the usual `.claude/autonomous/` state churn.

**Not done this iteration, deliberately:** no mock HTML yet — that's P2. No source change anywhere
(mock-only screen, same as S1–S3).

**Next:** S4 P2 — validate every finding against `IDENTITY.md`'s rejection test, then build
`design/mocks/S4/<variant>.html`, mocking BOTH a standalone page and a panel-embedded layout per
variant (narrower column, layers likely need to stack), two or three variants, realistic multi-layer
content (a collapsed terminal layer, an off-board reference, a `gated_on_rejected` card, a
live/running card), both themes. Reuse S2's `TaskCard` treatment rather than a third card style.

## Iteration 22 — 2026-08-22T04:02:42+01:00 — S4 P2: validate + mock (task DAG / dependency board)

**S4 P2 done.** Validated `design/mocks/S4/RESEARCH.md`'s findings against `design/IDENTITY.md`'s
rejection test (none discarded — every finding was a colour/motion/state/hierarchy gap, nothing
proposed a new hue, radius, or icon source) and built two variants, each containing **both** a
standalone form and a panel-embedded form, per `pre_authorised` and `decisions_for_user`
D-dag-placement.

**Card treatment reused verbatim.** Both files copy S2's `TaskCard` CSS classes (`task-card`,
`card-body`, `badge`, `b-success/info/danger/agent`, `chip-req`) rather than inventing a third card
style, per `next_action`.

**The edges are genuinely live, not illustrated.** Rather than hand-placing SVG coordinates, both
files run the same technique `DependencyBoard.tsx`'s `useEdgeLines` already uses:
`getBoundingClientRect` on each card after layout, redrawn on window resize and on every
collapse-toggle click. Verified this actually works with a throwaway Playwright script (not
committed — `.claude/autonomous/scratch/` is gitignored and the script plus its screenshots were
deleted after use): `restrained.html` shows 8 visible cross-board edges with layer 0 collapsed,
rising to 11 after clicking the toggle to expand it — exactly the 3 edges that were hidden behind
the collapsed layer, not a stale count. `considered.html` shows 8 real + 6 ghost-stub edges
throughout (3 hidden edges × 2 boards, each rendering a faint dashed stub instead of nothing), with
the ghosts swapping for real edges on expand and the total staying at 14 — confirming the ghost
mechanism and the real mechanism are counting the same edges, not double-drawing or dropping any.

**Content is realistic and answers every queue-required element in one graph:** a fully-terminal
collapsed layer 0 (3 approved tasks), a rejected task (`t1b`, "Widen forward lookup") whose rejection
propagates as a red edge into a `gated_on_rejected` card (`t2a`, "Reverse resolution wiring", which
also carries the off-board `REQ-118` reference connected by a real dashed line down to it — finding 4
fixed, not just described), a live/running card (`t1a`, green ring, green animated edge into its
gated successor), and the layer stall-summary sentences rendered with real visual weight (finding
9) instead of bare text.

**`restrained.html`** (smallest fix): straight lines (unchanged routing), an arrowhead
(`marker-end`), and colour that means something — grey default, amber when the edge's target is
gated, red when the source was rejected, green + animated dash when the source is live — plus a
hidden-link count appended to the "3 done" toggle text ("· 3 links hidden"). No hover interaction,
no ghost lines, no rerouting.

**`considered.html`** (fuller application): orthogonal step-routed edges per React Flow's
recommendation for technical diagrams (recorded in `RESEARCH.md`'s external research), the ghost
stub described above, and real hover-to-highlight lineage — mouseenter on any card computes its full
ancestor/descendant chain via a plain adjacency map, applies `--ring` (the same token every existing
selection state already uses, so clause 2 stays true) to the chain and dims everything else to 32%
opacity, including highlighting the collapsed layer-0 toggle when an ancestor is hidden inside it.
This directly answers the exploration doc's own stated want, quoted in `RESEARCH.md`: *"to access the
lineage fast."*

**A real bug found and fixed before finishing, not just described.** Screenshotting both variants in
both themes (Playwright directly, not `scripts/uishot.py` — that script looks for the Hub app's
"Switch to dark mode" button, which these standalone mocks don't have; per `dead_ends_inherited`
this is the expected fallback) turned up the collapse chevron rendering enormous — its SVG has
`width="100%" height="100%"` (matching every other icon substitution in this file's `ICONS` map) but
the wrapping `.layer-chevron` span had no explicit size, so it expanded to fill whatever space was
available instead of sitting at icon size next to the "3 done" label. Fixed in both files: `.layer-chevron`
now has an explicit `width: 14px; height: 14px` and `flex: none`, matching the convention every other
`.ic`-class icon usage in these mocks already follows. Re-screenshotted after the fix and confirmed
correct in both themes.

**Verified.** `python -c "import json; json.load(...)"` on `STATE.json` after editing. Playwright
script confirmed, per variant per theme: edge counts before/after toggle (see above), zero console
errors beyond the three pre-existing `@fontsource` `file://` resolution failures inherited from
`index.css` (present on every mock under `design/mocks/`, not introduced here). Read all four
resulting screenshots (restrained/considered × dark/light) directly — both variants legible in both
themes, edge colours (grey/amber/red/green) distinguishable against both the near-black and the light
surface, chevron fix confirmed correct at normal icon size, panel-embedded single-column stacking
renders cards full-width with edges correctly degenerating to straight vertical lines (expected, since
x1 equals x2 in a single-column layout — not a bug). `git status --short` → only the two new
`design/mocks/S4/*.html` files plus the usual `.claude/autonomous/` state churn; the verification
script and its PNGs were deleted after use and were gitignored regardless.

**Not done this iteration, deliberately:** lineage-hover highlighting was only spot-checked by
reading the JS logic and confirming the DOM structure it depends on (`data-node` attributes, the
`PARENTS` adjacency map) is correctly wired — not clicked/hovered live via Playwright in this pass.
P3 should do that explicitly (`page.hover(...)` then screenshot) rather than trust the static read.
No source change anywhere (mock-only screen, same as S1–S3). No `RATIONALE.md` yet — that's P4.

**Next:** S4 P3 — screenshot every variant (both standalone and panel-embedded regions) in both
themes, this time including a live hover test on `considered.html` to confirm the lineage highlight
actually differentiates dim vs. active rather than just existing in the code, critique honestly
against the rejection test, and fix what's found.

## Iteration 23 — 2026-08-22T04:10:15+01:00 — S4 P3: iterate (task DAG / dependency board)

**Verified branch/state on entry.** `git branch --show-current` = `autonomous/2026-08-21-refine-and-continue`,
`git log --oneline -15` matched STATE.json's account of iteration 22 exactly (S4 P2 commit
`e11a0eb` topmost real commit, heartbeat release `376e58d` after it). No reconciliation needed.

**What P3 requires per `screen_pass_protocol`:** screenshot every variant in both themes, read the
PNGs, critique honestly against the rejection test, fix what's found. Did exactly that, not more.

**Method.** `scripts/uishot.py` looks for the Hub app's "Switch to dark mode" button per
`dead_ends_inherited`, which these standalone mocks don't have, so used Playwright directly against
`file://` URLs — the same fallback S3's P3 iteration used. Wrote a throwaway script at
`testbed/scratch/s4p3/verify.py` (deleted after use; `testbed/scratch/` is gitignored regardless)
that for each of {restrained, considered} × {dark, light}: loads the mock, records the baseline edge
count and hidden-link label with layer0 collapsed, clicks the layer0 toggle, re-records both, and
screenshots. For `considered.html` specifically it additionally hovers the live card (`sa-t1a`,
"Successor inherits predecessor's lineage_id"), counts elements carrying `.lineage-active` /
`.lineage-dim` / `.edge-lineage-active` / `.edge-dim`, screenshots the hover state, clears the hover,
re-collapses layer0, and checks whether the ghost-stub markers actually resolve
(`svg.querySelector('marker#sa-arrow-ghost')`).

**Findings, checked against the rejection test:**

1. **`restrained.html` — correct, no changes.** Edge count 4 → 7 on expanding layer0 (exactly the 3
   previously-hidden edges), hidden-count label clears to empty on expand. Arrowheads and the
   grey/amber/red/green colour-by-meaning read clearly in both themes — read all four screenshots
   directly, not just the counts. The diagonal-line crossing between layer0→layer1 (visible in the
   dark-expanded screenshot, "Add lineage_id"→"Widen forward lookup" crossing "Write test"→"Successor
   inherits") is inherent to straight-line routing on a real DAG, not a bug — it's exactly what
   `considered.html`'s orthogonal routing exists to fix, and `restrained.html`'s own subtitle says so
   ("No new routing... see considered.html for those").

2. **`considered.html` — hover-to-highlight lineage genuinely works, not just present in the DOM.**
   Hovering `t1a` produced exactly the expected chain: ancestors `t0a`, `t0b` (both parents of `t1a`),
   descendants `t2b` (child via `t1a→t2b`) and `t3a` (child of `t2b`) — 5 cards plus the layer0 toggle
   (highlighted because two of its hidden children, `t0a`/`t0b`, are in the chain) = 6 elements with
   `.lineage-active`; the remaining `t0c`, `t1b`, `t2a` = 3 with `.lineage-dim`. Edge counts matched:
   4 `.edge-lineage-active`, 3 `.edge-dim`. Read the hover screenshots in both themes directly — the
   `--ring` outline on active cards and the 32%-opacity dim on the rest are clearly distinguishable
   against both the near-black and the light surface, confirming clause 2 (reuses an existing
   selection token) and clause 1 (legible in both themes) actually hold, not just in theory.

3. **Real bug found and fixed: ghost-stub arrowheads were invisible.** `considered.html`'s
   `drawBoard()` emits ghost paths with `marker-end="url(#${prefix}-arrow-ghost)"` (for both the
   standalone `sa-` and panel-embedded `pe-` boards) but neither `<svg><defs>` block ever defined a
   `<marker id="sa-arrow-ghost">` / `id="pe-arrow-ghost"` — only `normal`, `gated`, `rejected`, `live`,
   and `lineage` markers exist. A missing marker reference fails silently in the browser (no console
   error, no visible warning), so the dashed ghost stubs beneath the collapsed layer0 toggle rendered
   with no arrowhead — a real, user-visible regression from what `RESEARCH.md`'s finding 2 promised
   ("a faint ghost stub... instead of nothing"). Confirmed programmatically
   (`svg.querySelector('marker#sa-arrow-ghost')` → `false`) before fixing. Fixed by adding the two
   missing `<marker>` elements (one per board prefix, matching the existing five markers' exact
   shape/size/`orient="auto"` and using the `.arrowhead-ghost` class the CSS already defined but never
   referenced from a marker). Re-ran the verification script: `ghost_marker_defined` now `True`,
   `ghost_paths` still 3, all other edge/hover counts unchanged (proving the fix touched nothing else),
   and re-read the collapsed-ghost screenshot directly — the small triangular arrowhead is now visible
   at the end of each dashed ghost stub in both themes.

**Not a bug, checked and dismissed:** the mock's own inherited console errors are the three
pre-existing `@fontsource` `file://` 404s already documented in `dead_ends_inherited`, present on
every mock under `design/mocks/` — not introduced by S4 and not actionable here.

**Verified.** `py -3.11 -c "import json; json.load(...)"` on `STATE.json` after editing. Playwright
script re-run after the fix confirmed all counts identical to before except `ghost_marker_defined`.
Read all screenshots produced (restrained × 2 themes expanded; considered × 2 themes expanded, hover,
and collapsed-ghost) directly rather than trusting the programmatic counts alone. `git status --short`
→ only `design/mocks/S4/considered.html` modified (the two `<marker>` insertions); verification script
and its PNGs deleted after use. No source under `hub/ui/src` touched (mock-only screen, unaffected by
the C6 exception).

**Next:** S4 P4 — a second iteration pass (re-look for anything else), then `RATIONALE.md` and add S4
to `design/mocks/index.html`. Remember the `*.png` gitignore blanket rule when building the index —
inline screenshots as data-URIs in the HTML itself rather than trying to commit loose PNGs, as
`dead_ends_inherited` already flags for whichever iteration reaches queue item `Z`.

## Iteration 24 — 2026-08-22T04:20:39+01:00 — S4 P4: finish (task DAG / dependency board)

**Verified branch/state on entry.** `git branch --show-current` = `autonomous/2026-08-21-refine-and-continue`,
`git log --oneline -5` matched STATE.json exactly (heartbeat-release `23183a9` topmost, S4 P3
`4f48ebf` beneath it). Working tree clean. No reconciliation needed.

**What P4 requires per `screen_pass_protocol`:** a second iteration pass (re-look, fix anything
else found), then `RATIONALE.md`, then add S4 to `design/mocks/index.html` with before/after shots.

**Second look.** Re-ran a Playwright verification script (`testbed/scratch/s4p4/verify.py`,
deleted after use) against both variants in both themes, same method as P3: baseline screenshot,
count edges, click `layer0`'s toggle, count again, and for `considered` additionally hover the live
card and count `.lineage-active`/`.lineage-dim`/`.edge-lineage-active`/`.edge-dim`. All counts
matched P3 exactly (4→7 on expand for `restrained`, 7 constant for `considered`, 6 active/3 dim/4
edge-active/3 edge-dim on hover) — confirming P3's fix was stable and nothing regressed.

**Real bug found and fixed, by looking at the baseline screenshot, not by re-reading the JS.** The
"collapsed" baseline screenshot (taken *before* any click, i.e. the page's actual default state)
showed layer0's three "done" cards fully visible underneath a toggle whose chevron pointed right
(collapsed) and whose label read "3 links hidden" — a direct contradiction on first paint, in both
`restrained.html` and `considered.html`. Root cause, confirmed with
`getComputedStyle(el).display`: `#sa-layer0-cards` carried the `hidden` HTML attribute (UA rule
`[hidden] { display: none }`, specificity `(0,1,0)`) *and* the `.layer-cards { display: grid }`
class rule (also `(0,1,0)`). Equal specificity ties resolve to cascade order, and an author
stylesheet always applies after the UA stylesheet — so `display: grid` silently won and `hidden`
did nothing, on every page load, for both the `sa-` (standalone) and `pe-` (panel-embedded) boards
in both files. The JS collapse *model* (`boardState[prefix].collapsed = new Set([0])`) was correct
throughout — edge counts and the hidden-link label were always right — only the cards' own paint
ignored it. Fixed with the standard specificity-tiebreak idiom, `.layer-cards[hidden] { display:
none; }` (an attribute selector on the same class, specificity `(0,2,0)`, unambiguous), added once
in each file. Verified the fix directly (`display: none` at load, `hasAttribute('hidden'): true` in
both files) and re-ran the full edge/hover script afterward: every count unchanged, confirming the
fix touched only initial-paint visibility and nothing about the redraw logic. Re-screenshotted all
four collapsed baselines and read them directly — layer0 now renders collapsed on load in both
variants and both themes, matching its own chevron and hidden-count label.

**RATIONALE.md written** (`design/mocks/S4/RATIONALE.md`) — the ten `RESEARCH.md` findings mapped
to what each variant actually does, the CSS-specificity bug above written up in full, what was
rejected (crossing-minimisation/orthogonal routing for `restrained` — its own subtitle says no new
routing, that's `considered`'s job; a minimap/pan-zoom control — boards are small, considered and
rejected in `RESEARCH.md`'s external-research section already; building the panel `tasks`/`dag` tab
for real; a third "expressive" variant, same reasoning S3 gave for chrome that should recede/not
add noise to a technical diagram; redesigning the off-board reference chip itself rather than only
its missing connection) and what was left alone (three-way stall classification design D8,
longest-path layering, the partly-finished-layer-never-collapses rule D9, the off-board chip's
content, `EmptyState` on the zero-tasks case, and `TaskCard.tsx` itself — not re-researched, since
S2 already did that work and both variants deliberately reuse its refined card rather than invent
a third).

**`design/mocks/index.html` rebuilt for S4.** Generated four representative screenshots (restrained
dark/light showing layer0 correctly collapsed, considered dark/light showing the lineage-hover
highlight) plus a before/after pair for the CSS-specificity bug — the "before" pair was captured by
writing a throwaway sibling copy of `restrained.html` with the `.layer-cards[hidden]` fix line
stripped back out (`design/mocks/S4/_tmp_buggy.html`, same directory so the relative `index.css`
import still resolved, deleted immediately after the screenshot), never touching the real file's
git history. All six inlined as base64 `data:image/png` URIs directly in `index.html`, per
`dead_ends_inherited`'s standing guidance on the repo's blanket `*.png` gitignore rule — same
pattern S1/S2/S3 already established, so this iteration didn't need to invent one. Replaced the old
"S4 — S8 and the final review-index rebuild, not started" pending card with S4's real done section,
and renamed the remaining placeholder to "S5 — S8 and the final review-index rebuild" so it still
covers exactly what's left in the queue. Verified by loading `index.html` in Playwright: 6
`screen-card` sections (was 5), S4's status now reads "4/4 passes done", all 24 `<img>` elements
report `complete` with nonzero `naturalWidth` (0 broken), and the only console errors are the three
pre-existing `@fontsource` `file://` 404s already documented in `dead_ends_inherited` (present on
every mock under `design/mocks/`, not introduced here). Screenshotted the rendered S4 section and
its fix-block directly and read both — legible, correctly laid out, matches the S1–S3 precedent.

**Verified.** `py -3.11 -c "import json; json.load(...)"` on `STATE.json` after editing.
`git status --short` → `design/mocks/S4/{restrained,considered}.html` modified (the one-line CSS
fix each, carried over from P3's session plus this iteration's own second look — actually this
iteration's own fix, P3's fix was the marker-id bug), `design/mocks/S4/RATIONALE.md` new,
`design/mocks/index.html` modified. `testbed/scratch/s4p4/` (verification script, its screenshots,
and the throwaway buggy-copy directory) all deleted after use — gitignored regardless, per
`testbed/README.md`.

**S4 is now fully done — all four passes (P1–P4) complete and verified.**

**Next:** S5 — the rendered spec documents (`hub/hub/spec_render.py`, not React). P1 explore: read
`spec_render.py` end to end, the templates it renders, WebSearch for documentation/spec-rendering
UI patterns, and the T3 Code sourcemaps for anything comparable. Per `decisions_for_user`
D-spec-render, note plainly in `RATIONALE.md` (written at P4) that implementing this one later
touches Python templates, not React components — a different kind of change from every other
screen in the queue. Write `design/mocks/S5/RESEARCH.md`.

## Iteration 25 — 2026-08-22T04:27:58+01:00 — S5 P1: explore (rendered spec documents)

**Verified branch/state on entry.** `git branch --show-current` = `autonomous/2026-08-21-refine-and-continue`,
`git log --oneline -3` matched STATE.json exactly (heartbeat-release `5f02844` topmost, S4 P4
`25c0b81` beneath it). Working tree clean. No reconciliation needed.

**What P1 requires per `screen_pass_protocol`:** WebSearch for patterns for this KIND of surface,
read the T3 Code sourcemaps for the equivalent, read the current component (with its comments) end
to end, write `design/mocks/S5/RESEARCH.md` naming what's missing and its sources.

**Read in full:** `hub/hub/spec_render.py` (533 lines including every comment — the module's own
notes on anchor-stability and "no navigation script here, the shell owns it" were treated as
binding design constraints, not decoration); `SpecFrame.tsx` and `hubTheme.ts` (the sandboxed-iframe
host and its neutral-only theme override, including the prior incident recorded in `hubTheme.ts`'s
own comments — a re-grounded surface once inverted every lifted block because only the background
moved and not the rest of the ramp); `SpecDocumentPanel.tsx` (the chrome around the iframe —
breadcrumb, phase bar, coverage bar, proposals panel, a 200px outline sidebar built from
`toc-ready` postMessage anchors — confirmed this is a separate, already-styled React surface and
out of S5's scope per the queue item's own framing, but its shell decisions constrain the mock:
no sticky TOC or anchor-click interceptor inside the document itself, since the shell already owns
both).

**Read a real generated document, not a toy example.** `spec/capabilities/task-lifecycle-governance
/spec.html` (1204 lines, 32 requirements, a 110-row acceptance-criteria table) — chosen deliberately
for density. Two findings only a real document could surface: 108 of 110 acceptance rows have an
empty "Given" cell (confirmed against the document's own `Limits` section, which names this as a
known translation gap), yet the rendered table gives that column full, unconditional width on every
row; and rationale prose regularly outweighs the requirement statement it explains (FR-21's
rationale is roughly triple the length of FR-21 itself) while both render as a plain `<p>`,
differing only by a muted colour.

**Read the legacy convention as reference only, not as a contract.** `.agents/skills/aw-spec-apply
/html-spec-conventions.md` describes a different, agent-authored `spec.html` predating the Hub-owned
flow — per `CLAUDE.md` the `aw-*` skills are product source to implement, not a workflow to run, so
this was read the same way `IDENTITY.md` treats T3 Code: design reference, not something to run or
treat as current. Two things in it still transfer: its MUST/SHOULD/MAY badges are filled pills
(background + colour) rather than coloured text — a legitimate steal *within* `spec_render.py`'s own
existing tokens — while its sticky TOC and live task-progress bar are superseded (the shell owns TOC;
`SpecPayload.tasks` carries no status field today, so a progress bar would have to invent data the
payload doesn't have — flagged as a missing-feature note per the pre-authorised instruction, not
mocked as a fake state).

**T3 Code has no comparable surface.** Grepped all 384 sourcemaps under
`app.asar.unpacked/apps/server/dist/client/assets` for anything resembling a document/spec/plan
viewer (`TableOfContents`, `DocViewer`, `PlanView`, `SpecView`, `Requirement`, `Markdown`,
`ReactMarkdown`, `prose-`) — the only hit across all 384 was a Shiki syntax-highlighting grammar
file, not a component. T3 Code is chat-first and has no document-authority screen at all, unlike
every other screen in this queue — recorded plainly in `RESEARCH.md` rather than papering over the
gap with an invented comparison, and external WebSearch research carries correspondingly more
weight this pass.

**External research, three searches, all cited with URLs in `RESEARCH.md`:** API-reference-docs
scannability/hierarchy practice (Speakeasy, Stoplight — "walls of text with buried important
information" is this document's literal failure mode once the one 3px border is the only
differentiation between 32 requirement blocks); long-document reading UX (NN/g — a scroll-progress
indicator answers "how much is left" where the shell's own outline sidebar only answers "where am
I," and only at section granularity, not inside a 32-item Requirements section); badge/status-pill
design (Eleken — filled pill beats colour-on-text for at-a-glance scanning, the same "icon/fill +
colour" idiom S2 and S4 already invoked for cards and DAG nodes).

**Resolved a genuine tension with `IDENTITY.md` clause 1 before P2 needs it.** Clause 1 requires
"every colour resolves to an existing token in `hub/ui/src/index.css`" — read literally that cannot
apply here: `spec_render.py`'s `_STYLE` is a deliberately separate, self-contained token namespace
(the document renders standalone outside any Hub), and `hubTheme.ts`'s own comment states its four
semantic hues are "not the Hub's to recolour." Wrote the resolution directly into `RESEARCH.md`:
clause 1 is scoped for this screen to mean every colour resolves to a token **already declared in
`spec_render.py`'s own `_STYLE` block**, not the Hub's — same rule (no invented hue, no arbitrary
hex), applied to this screen's actual, different vocabulary — so P2 applies it consistently rather
than improvising a call mid-mock.

**`design/mocks/S5/RESEARCH.md` written** (187 lines) — what was read, the clause-1 resolution, three
cited external sources, ten specific missing-detail findings (modal-tone weight, inverted
rationale/statement hierarchy, the wasted Given column, no local sense of progress inside a long
section, no copy-anchor affordance despite anchor-stability being a real guarantee, bare task list,
undifferentiated corpus-map children, a duplicate/inconsistent in-frame vs. shell breadcrumb, bare
loading text, and the observation that the meta-chips/summary row is already the best-styled part
of the document while everything below regresses), and what must not be redesigned (the three-layer
theme cascade and `hubTheme.ts`'s neutral-only override — a tested, previously-bug-fixed contract;
the phase/rigor/modal colour *assignments* themselves, only their weight is the gap; anchor
stability; the deliberate absence of in-document navigation script).

**One self-caught error.** First write of `RESEARCH.md` left a stray `2.` numbered-list marker
inside what should have been an unordered "already good" list (a copy-paste artefact from drafting).
Caught rereading the file immediately after writing it, fixed with a targeted `Edit`, confirmed by
rereading the corrected section.

**Verified.** `py -3.11 -c "import json; json.load(...)"` on `STATE.json` after editing.
`git status --short` → only the new `design/mocks/S5/` directory (containing `RESEARCH.md`).

**Next:** S5 P2 — validate every `RESEARCH.md` finding against `IDENTITY.md`'s rejection test
(clause 1 applied as scoped above: the document's own `_STYLE` tokens, not the Hub's), then build
`design/mocks/S5/<variant>.html` (two or three degrees of refinement) using the real
`task-lifecycle-governance` document's density as realistic content, in both themes. Decide
explicitly at P2 whether to also demonstrate the standalone (non-Hub-embedded, OS-preference-driven)
theme path alongside the Hub-embedded one that `hubTheme.ts` produces, per `RESEARCH.md`'s closing
note — this screen is a real standalone artefact in a way no other screen in the queue is.

## Iteration 26 — 2026-08-22T04:40:37+01:00 — S5 P2: validate + mock the rendered spec document

Branch and log matched STATE.json on entry: HEAD was `fc3951b` ("release heartbeat for next
firing"), one commit past `0086438` (S5 P1). Read `RESEARCH.md` (187 lines) and `IDENTITY.md` in
full before touching anything.

**Validated all 10 `RESEARCH.md` findings against the rejection test**, applying clause 1 as
`RESEARCH.md` already scoped it for this screen (a colour must resolve to a token already declared
in `spec_render.py`'s own `_STYLE`, not `hub/ui/src/index.css` — that document is standalone and
the Hub's stylesheet is not in its cascade). None failed; all 10 were incorporated into the mock
rather than any being discarded.

**Built `design/mocks/S5/restrained.html` and `considered.html`.** Both reproduce `_STYLE`
byte-for-byte and are strictly additive below it — nothing inside the reproduced block was edited,
so a diff against the real renderer's own stylesheet shows only additions. Content is composited
from three real corpus documents rather than invented: FR-1–FR-8 verbatim from
`spec/capabilities/task-lifecycle-governance/spec.html` (the dense, 100%-MUST document
`RESEARCH.md`'s findings were measured against), FR-9/FR-10 (SHOULD/MAY) verbatim text borrowed
from `spec/capabilities/quiet-hours/spec.html` and re-anchored — the sampled document has no
SHOULD/MAY of its own, so without this the modal-tone system's other two tones would go
undemonstrated — and open questions plus map children verbatim from `spec/agentweave.html`, since
neither the sampled document nor any document in the current corpus populates Open Questions or
Tasks. The Tasks section content is therefore composed in `_tasks()`'s own voice
(`<strong>title</strong> — description — satisfies FR-N`) rather than lifted from a real document,
and this is stated plainly rather than passed off as sampled.

**Each of the 10 findings got a fix:**
1. Modal MUST/SHOULD/MAY as filled pills (`color-mix` of the existing tone token over `--bg`, no
   new hue) instead of colour-on-text.
2. Rationale gets a small-caps "Why" label and a left rule, subordinating it to the requirement
   statement instead of relying on colour alone.
3. The acceptance table's Given column is narrowed via `<colgroup>` and empty cells render a muted
   em dash instead of blank space claiming width.
4. A CSS-counter-only "Requirement N of 10" label (no script) — `data-total` is trivial for
   `spec_render.py` to emit since it already knows `len(payload.requirements)`.
5. A copy-anchor button beside each requirement's id, using a small inert clipboard script —
   confirmed this does **not** cross `spec_render.py`'s stated no-navigation-script boundary, since
   it copies to the clipboard and never intercepts an anchor click or adds same-document navigation.
6. Tasks render as bordered rows with `satisfies` chips instead of trailing muted text.
7. Map children get a divider between siblings instead of one unbroken list.
8. The in-frame breadcrumb gets a chevron separator instead of bare adjacent links (full
   deduplication against the shell's own breadcrumb is out of scope — that's `SpecDocumentPanel.tsx`,
   confirmed in P1).
9. Left alone — the bare "Loading…" text lives in `SpecDocumentPanel.tsx`, not this document.
10. The already-good summary line is kept and, in `considered.html`, gets a light card treatment so
    it doesn't look identical in weight to the plain paragraphs below it.

**A second scoped-clause resolution, parallel to clause 1's.** `considered.html` needed motion, and
IDENTITY.md clause 3 names `--dur-fast/base/slow` — tokens that live in `hub/ui/src/index.css`,
unreachable from this standalone document for the same reason clause 1 needed scoping in
`RESEARCH.md`. Resolved the same way: added `--aw-dur-fast`/`--aw-dur-base`/`--aw-ease` to this
document's own `_STYLE`, value-identical to the Hub's (150ms/250ms, the same
`cubic-bezier(0.16,1,0.3,1)`) — a mirror of the existing scale, not an invented one. Stated in both
files' header comments; will be repeated in `RATIONALE.md` at P4 so it isn't read as a stray
duration later.

**Decided the standalone-vs-embedded question `RESEARCH.md` raised at P1**, rather than leaving it
open: did not build a fourth separate file. Both mocks already exercise both cascade layers a real
opening of this document would hit — `@media (prefers-color-scheme)` (the OS-preference path, live
whenever the review toolbar hasn't forced a theme) and `:root[data-theme]` (the Hub-embedded path,
forced by the toolbar exactly the way `hubTheme.ts` forces it). A fourth file would duplicate all
this content for no new token combination. Recorded as the explicit decision the closing note asked
for.

**Verified by screenshot, not just by reading the CSS.** `uishot.py` targets the Hub app's own
localStorage-driven theme button and would not have found this file's custom review toolbar, so
wrote a throwaway `testbed/scratch/shot_s5.py` (Playwright, loads the two files directly via
`file://`, clicks the toolbar's Dark button, captures both themes) per the pre-authorised fallback
for exactly this case. Read all 4 PNGs (restrained × considered × light × dark): legible in both
themes (clause 2), same radius/token vocabulary as the untouched `_STYLE` (clauses 1/3/4), reads as
the same document improved — pills and a counter label, not a new layout — rather than a redesign
(clause 5), at least as much information on screen as before since nothing was removed, only added
(clause 6). **Interactive states (clause 7) are real in the CSS but not confirmed by triggering
them this pass** — the screenshots are resting-state only; `:hover`/`:focus-visible` were spot-read
in the stylesheet, not exercised in Playwright. Recorded honestly rather than claimed as verified,
and queued as the first thing P3 should do. Deleted all 4 PNGs after reading (gitignored, matches
the no-committed-screenshots precedent already set by S2/S4).

**Verified.** `py -3.11 -c "import json; json.load(...)"` on `STATE.json` after editing.
`git status --short` → only the two new `design/mocks/S5/*.html` files — staged and committed.

**Next:** S5 P3 — screenshot every variant in both themes again, this time actually triggering
`:hover` on a requirement, a table row and a task card, and `:focus-visible` on a copy button and a
nav link, before capturing. Read the results and critique honestly: in particular whether the
"REQUIREMENT N OF 10" counter reads as noise at this mock's 10-of-10 density versus how it would
read at the real document's 32, and whether the empty-Given em dash is legible enough at real
reading size (the P2 review screenshot was too compressed to confirm either way).

## Iteration 27 — 2026-08-22T04:47:25+01:00 — S5 P3: Playwright iterate on the rendered spec document

Branch and log matched `STATE.json` on entry: HEAD was `48c3c2a` ("release heartbeat for next
firing"), one commit past `105e225` (S5 P2). Read `restrained.html` and `considered.html` in full
before touching anything.

**Wrote `testbed/scratch/shot_s5_p3.py`** (Playwright, throwaway per the pre-authorised fallback —
`uishot.py` targets the Hub's own theme button, not a standalone file's toolbar). For each of the
two variants × two themes it captures: a resting full-page shot, a clipped shot of `#FR-3` after a
real `.hover()`, a clipped shot of an acceptance-table row after `.hover()`, a clipped shot of the
first task card after `.hover()`, and two focus-visible shots reached by real `page.keyboard.press
("Tab")` from the first nav link (not `.focus()` — Chromium's focus-visible heuristic does not
reliably arm on programmatic focus, keyboard traversal does) — landing on the second nav link and
then the first requirement's copy button.

**Found a real, confirmed bug carried over from P2, not a new defect introduced this pass.** The
first run's `hover-row` and `full` screenshots showed the acceptance table completely unaffected by
any of its dedicated CSS: no narrowed Given column, no alternating row bands, no em-dash placeholder
in empty Given cells, no hover tint. Sampled pixels down the column at (700, y) for every 8px from
y=0–392 — pure `(255,255,255)` throughout, confirming zero effect, not just a subtle one. Root
cause: in both files, `<section><h2 id="acceptance">Acceptance criteria</h2><table>...` puts the
`id` on the `<h2>`, not on an ancestor of the `<table>` — so every rule scoped `#acceptance table`,
`#acceptance col.*`, `#acceptance td.aw-cell-empty`, `#acceptance tr[data-group]`, and (in
`considered.html`) `#acceptance tbody tr:hover` silently matched nothing, because the h2 has no
table descendant. The same misplacement existed on `#requirements` (used only for
`counter-reset: aw-req`), but that one accidentally still counted 1–10 correctly, because CSS falls
back to an implicit root-level counter when no ancestor establishes one in scope — lucky, not
correct, and fragile if this document is ever embedded alongside another counter-using instance
(e.g. on the `index.html` queue item Z will build).

**Fixed by moving the `id` from the `<h2>` onto the enclosing `<section>`** for both `#requirements`
and `#acceptance`, in both `restrained.html` and `considered.html` — matching the pattern `#tasks`
already used correctly (`<section id="tasks"><h2>Tasks</h2>`, which is why the task-card styling
*did* render correctly the first time). Checked first that nothing inside either mock links to
`#requirements` or `#acceptance` by href (grepped both files) — the browser's own outline sidebar
that would consume such an anchor lives in the Hub shell, not reproduced here, so retargeting the id
from an inline heading to its section is anchor-neutral. No other section (`#summary`, `#evidence`,
`#open-questions`, `#map`) has any CSS rule keyed off its id being an ancestor of anything, so left
those as-is — fixed only what was actually broken.

**Re-ran the screenshot script and read every image.** Confirmed by both full-page and pixel-level
inspection: the Given column is now visibly narrow with a legible muted em dash in every empty cell,
requirement rows alternate a faint band, and hovering a row now tints it with a clearly visible pale
accent wash in `considered.html` (`restrained.html` correctly has no row-hover rule at all — its own
header comment states table-row hover is deliberately deferred to `considered.html`, so its absence
there is intended, not a miss). Requirement hover (`considered.html`) shows the left border swapping
to accent and a soft `--surface` background; task-card hover shows border tint + a translateY lift +
soft shadow; both read clearly in light and dark. Focus-visible via real Tab traversal shows a crisp
2px accent outline on the copy button and (in `considered.html`) on nav links; `restrained.html`'s
copy button has its own `:focus-visible` rule and its nav link correctly falls back to the browser's
native focus ring, consistent with the file's stated minimalism (no custom nav-hover/focus was ever
claimed for restrained). **Clause 7 of the rejection test (interactive states are real) is now
verified by actually triggering the states, not spot-read in the stylesheet** — closing the honesty
gap P2's log entry flagged explicitly.

**Answered the two questions P3 was queued to answer.** The "REQUIREMENT N OF 10" counter reads as a
small, unobtrusive uppercase label at this mock's 10-of-10 density in the full-page screenshot — it
does not compete with the requirement text or crowd the layout; nothing about its size or weight
would change at the real document's 32 (it is a fixed-size label, not something that grows with the
count), so no adjustment was made. The empty-Given em dash is clearly legible at normal reading
size, once the underlying `#acceptance` scoping bug was fixed to make it appear at all — the P2
screenshot could not have confirmed this because the rule producing the dash was silently inert.

**Verified.** `py -3.11 -c "import json; json.load(...)"` on `STATE.json` after editing. Deleted all
regenerated PNGs (gitignored, matches the S2/S4/S5-P2 precedent of no committed screenshots).
`git status --short` → only the two modified `design/mocks/S5/*.html` files — staged and committed.

**Next:** S5 P4 — a second iteration pass on the same basis (look again, fix anything remaining),
then write `design/mocks/S5/RATIONALE.md` (what was researched, what changed and why, what was
rejected and under which clause, including the two scoped-clause resolutions from P2 and the
`#acceptance`/`#requirements` id-scoping bug found and fixed this pass) and add S5 to
`design/mocks/index.html` with its before/after shots — noting `index.html` does not exist yet
(queue item Z), so P4 is where S5's own entry is written but the review index itself is still
pending until Z runs.
