# Tasks — Conversations continue

Phases are ordered so that each one leaves the tree working. Phase 1 is the schema the rest needs,
phase 2 fixes the pre-existing cutover break in the direction that already has a contract, phase 3
adds the reverse rule, phase 4 adds deliberate branching, phase 5 corrects the tool description,
phase 6 folds the outbound bubble, and phase 7 is what only a human can judge.

Phase 6 is independent of 1-5 — it touches rendering only. If the routing work is split out, it
travels with either half.

Every phase opens with its test task. A test written after the implementation tends to assert what
the code does rather than what the requirement says.

## 1. The line of work

- [x] 1.1 Add `test_migration_0085_adds_lineage_id` to `hub/tests/test_migrations.py`, asserting the
      column exists after upgrade, that every pre-existing row is backfilled to its own `id`, and
      that downgrade drops it
- [x] 1.2 Add `lineage_id` to `Conversation` in `hub/hub/db/models.py`, indexed
- [x] 1.3 Write `hub/hub/migrations/versions/0085_conversation_lineage.py` — add the column,
      backfill `lineage_id = id`, then index it; guard for a missing `conversations` table as
      `0033`/`0034` do, since an upgrade from an early revision reaches it with only that
      revision's tables
- [x] 1.4 Bump `HEAD_REVISION` to `"0085"` in `hub/tests/test_migrations.py:39` **and** the head
      assertion in `hub/tests/test_project_persistence.py`
- [x] 1.5 Set `lineage_id` to the conversation's own id in `new_conversation`
      (`hub/hub/conversations.py`). The sweep is already done — design.md open question 3 lists all
      eight call sites and `checkpoint_cutover.py:91` is the only one that inherits. Confirm the
      list still holds rather than repeating the sweep
- [x] 1.6 Run `cd hub && py -3.11 -m pytest tests/test_migrations.py tests/test_project_persistence.py -q`

## 2. A cutover keeps the line of work

Covers `agent-conversation-handoff` — *A cutover carries the line of work to the successor in both
directions*.

- [x] 2.1 Add tests to the checkpoint-cutover suite for all five scenarios: successor shares the
      predecessor's lineage; an agent sending **from** a successor reaches its already-bound
      recipient thread without creating one; a correspondent replying into a cut-over line reaches
      the newest open conversation; lineage resolves with no checkpoint rows present; a
      non-successor conversation is its own lineage. **2.2 is where the currently-failing one is
      expected** — the sender-side case is a live defect today, so that test should fail before 2.3
      and pass after
- [x] 2.2 In `hub/hub/checkpoint_cutover.py`, set `successor.lineage_id = predecessor.lineage_id`
      alongside the existing `bound_sender_*` copy at lines 108-110
- [x] 2.3 Widen the forward lookup in `peer_bound_conversation` (`hub/hub/conversations.py:172`)
      from `bound_sender_conversation_id == src.id` to "bound to any conversation sharing
      `src.lineage_id`", leaving the senderless `bound_sender_agent` branch untouched
- [x] 2.4 Confirm by test that a self-lineage row resolves exactly as the old equality test did —
      this is what makes the backfill safe for every existing conversation
- [x] 2.5 Run the conversations and cutover suites

## 3. A reply continues the conversation

Covers `agent-conversation-workspace` — *A reply continues the conversation it is replying to*.

- [x] 3.1 Add tests for all six scenarios: a reply reaches the thread it answers; an exchange
      settles into exactly two conversations; a message to a third agent does **not** continue an
      unrelated thread; a reply continues into an operator-origin conversation and records the
      replying agent as `origin_agent`; continuation survives the replying side's cutover; an
      archived line with no open successor falls through to creating a conversation
- [x] 3.2 Add the reverse resolution to `hub/hub/conversations.py`: given the sender's conversation,
      if its `bound_sender_conversation_id` names a conversation owned by the recipient, return the
      newest open conversation in that conversation's lineage
- [x] 3.3 Wire it into `hub/hub/api/v1/messages.py:184-201` **between** the forward lookup and the
      mint, so the mint branch is reached only when both miss. Do not reorder the existing forward
      lookup
- [x] 3.4 Add a regression test reproducing the measured defect directly: three messages alternating
      between two agents produce two conversations, not three
- [x] 3.5 Run `cd hub && py -3.11 -m pytest tests/ -q` and confirm no existing delivery test changed
      behaviour — any that did means the forward path was disturbed

## 4. Starting a thread deliberately

Covers `agent-conversation-workspace` — *An agent can start a new thread deliberately*.

- [x] 4.1 Add tests for all four scenarios: an explicit request creates a thread even when a binding
      exists; the new thread becomes the bound one for later messages; omitting the flag continues;
      naming a conversation **and** asking for a new thread is refused with nothing created and
      nothing delivered
- [x] 4.2 Add `start_new_thread: bool = False` to the message-create schema in `hub/hub/schemas/`
- [x] 4.3 Honour it in `hub/hub/api/v1/messages.py` — when true, skip both lookups and mint, binding
      the new conversation to the sending conversation; when true alongside an explicit
      `conversation_id`, refuse
- [x] 4.4 Confirm by test that the newest binding wins the forward lookup, so no extra state is
      needed to make the new thread the active one

## 5. The tool surface tells the truth

Covers `agent-tool-surface` — *The outbound message tool describes how delivery is actually
resolved*.

- [ ] 5.1 Add a test asserting the published `send_message` description does not claim recency
      delivery, and that `start_new_thread` is declared with its default
- [ ] 5.2 Add `start_new_thread` to `send_message` in `hub/hub/mcp_server.py:174-208` and pass it
      through to `POST /messages`. This file is spawned standalone and may import **only** stdlib +
      fastmcp — the flag is a pass-through, so nothing new is imported
- [ ] 5.3 Rewrite the `conversation_id` docstring, which currently says "Leave unset to use their
      most recent one" (`hub/hub/mcp_server.py:191-194`) — recency was removed when the binding
      contract shipped
- [ ] 5.4 Update the test that asserts `mcp_server.py`'s restatements agree with the Hub
- [ ] 5.5 Run `py -3.11 -m ruff check hub/`, `black --check hub/`, and the full
      `cd hub && py -3.11 -m pytest tests/ -q`

## 6. The outbound message folds

Covers `agent-conversation-workspace` — *An outbound peer message renders folded, showing its
subject*. Independent of phases 1-5: it touches rendering only, and could ship on its own.

- [ ] 6.1 Add tests for all five scenarios: an outbound entry renders folded; two messages to the
      same recipient with different subjects fold to different lines; expanding shows the content;
      an expanded message stays expanded as entries are appended; an inbound message is unaffected
- [ ] 6.2 Add `subject` to `TimelineEntry` in `hub/hub/api/v1/agent_chat.py:59-78` and stop
      discarding it in `_message_to_timeline` (line 203-208), which today passes only `id`, `kind`,
      `content`, `timestamp` and `participant`
- [ ] 6.3 Add `subject` to the `TimelineEntry` type in `hub/ui/src/api/agentChat.ts`
- [ ] 6.4 Fold the outbound branch of `MessageEntry`
      (`hub/ui/src/components/agents/AgentTimeline.tsx:849-895`). `WorkRow` in the same file is the
      pattern — a header row, an inline truncated detail, `useState` for expansion. Reuse its shape
      rather than inventing a second one; do **not** fold the inbound branch
- [ ] 6.5 Confirm a message with no subject still folds to something readable — subject is required
      by `send_message`, but the column is nullable and older rows predate it
- [ ] 6.6 Run `cd hub/ui && npx vitest run`, `npm run lint`, `npx tsc --noEmit`
- [ ] 6.7 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py` from the repo
      root, and commit `hub/ui/src` and `hub/hub/static/ui` together

## 7. Human verification

Not agent-verifiable. Each needs the trial Hub on 8010 with at least two agents bound to a runner,
and a real exchange — the defect this change fixes was found by watching one, not by reading code.

- [ ] 7.1 Have two agents exchange four or more messages. Confirm in the UI that the exchange
      occupies **two** conversations total, and that each agent's side reads as one continuous
      thread
- [ ] 7.2 Ask one agent something in your own conversation and have it delegate to a second agent.
      Confirm the second agent's reply appears **in your thread**, left-aligned and labelled with
      that agent's name. Attribution is already implemented (D5) — this confirms it holds on the new
      path, it is not an open design question
- [ ] 7.3 Judge whether the thread still reads as *your* conversation once it carries a complete
      third-party exchange rather than only the outbound half it shows today. This is the risk D5
      accepts, and the only part of it that is genuinely open. If it reads as a log, say so — that
      is a finding about density, not a reason to drop continuity
- [ ] 7.4 Trigger a checkpoint cutover mid-exchange, then have the correspondent reply. Confirm the
      reply lands in the successor and that nothing new is opened
- [ ] 7.5 Have an agent start a new thread deliberately and confirm the separation is legible in the
      UI — that it reads as a deliberate branch rather than as the scattering this change removes
- [ ] 7.6 Judge whether a continuing thread grows uncomfortably long before a checkpoint is
      suggested. Continuity means threads no longer reset on every reply; if the checkpoint prompt
      now arrives too late, that is a finding for a separate change, not a reason to reopen this one
- [ ] 7.7 Read a conversation where an agent delegated three or more times. Judge whether the folded
      outbound rows make the agent's own replies findable again, and whether the subject line is
      actually informative — a subject the agent wrote carelessly folds to a useless row, and that
      would be a finding about the prompt, not the fold
- [ ] 7.8 Confirm the fold does not reintroduce the scroll bounce fixed in handoff 0072. Expanding
      an entry changes height mid-conversation, which is exactly the shape of that defect
