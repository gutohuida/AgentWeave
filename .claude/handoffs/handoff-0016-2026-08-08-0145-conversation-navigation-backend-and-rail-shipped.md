# Handoff: conversation navigation — backend, tree and recency view shipped; menus and selection remain

**Date:** 2026-08-08T01:45 · **Branch:** hub-native-experience · **HEAD:** 179cf8b
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0015-2026-08-07-2147-conversation-navigation-explored-and-proposed.md
**Status:** chunk complete. Six commits, working tree clean. `2026-08-07-conversation-navigation`
is **47/78 tasks** — sections 1–6 and four of section 10 done; sections 7, 8, 9, the rest of 10,
and all of 11 remain.

## Goal

Implement `openspec/changes/2026-08-07-conversation-navigation/` — give a conversation a name, a
provenance, a home in the rail, and a way to be put away.

The *why*, from handoff-0015: a conversation is the unit of work in AgentWeave and was the one
object with no place in the shell. Sixteen entries labelled `conv-a3f81b2c…` in an overflow menu
that also held durable agent settings. Second and more expensive: `Question`, `PermissionRequest`
and `UnaskedQuestion` all block a run pending an answer, and none of them were visible anywhere
except inside the conversation that raised them — so a run that stopped to ask something was
discovered by clicking through agents one at a time while `Agent.question_timeout_seconds` counted
down.

## Current state

### Shipped and live on http://localhost:8010

**The Hub was restarted three times this session and is running the current code.** The UI was
built and copied to `hub/hub/static/ui` (committed artefact, per CLAUDE.md); the served bundle is
`assets/index-BTpElNWl.js`. The real database `hub/data/agentweave.db` was migrated **0034 → 0037**.

Six commits, oldest first:

1. `5b8d21a` — schema. `Conversation.title`, `.title_set_by_operator`, `.origin`;
   `conversation_id` on `questions`/`permission_requests` (+ an index on the one
   `unasked_questions` already had); `projects.conversation_title_mode` and
   `.conversation_title_runner_id`. Migrations 0035–0037.
2. `37983d3` — rename, archive/unarchive with refusals, archived-send refusal with conversation
   targeting, per-conversation attention state. 47 tests.
3. `b259ae7` — title generation (opt-in, one-shot spawn). 19 tests.
4. `15880a0` — the rail's third level: `AgentTree.tsx`, `ConversationRow.tsx`, the project-wide
   listing endpoint. 11 tests.
5. `9f77e45` — lazy title backfill for conversations predating titling; rebuilt `static/ui`.
6. `179cf8b` — the recency view, the "Show archived (N)" control, and the "Show fewer" fix.

### What actually works, verified live against the real database

- 35 pre-existing conversations migrated intact and are all titled (max title 119 chars, cut at a
  word boundary under the 120 cap). Both check constraints and all three indexes survived 0035's
  SQLite table rebuild; 77 `runs` rows still reference conversations.
- `GET /api/v1/projects/proj-84d218db/conversations` returns 35 open, 0 archived, each with
  `agent`, `origin`, `title`, `attention`.
- The live project is **`proj-84d218db` ("Testbed")** with agents `codex-1`, `codex-2`,
  `file_edit`, `haiku-1`, `haiku-2`, `haiku-3`. The bootstrap `.env` names
  `AW_BOOTSTRAP_PROJECT_ID=Agentweave`, which **does not exist** — do not use it in curl.
  API key: `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (in `hub/.env`).

### Known-broken / not done

1. **Sections 7, 8, 9 are untouched.** No row menus, no `⋯` control, no rename-from-the-rail, no
   archive-from-the-rail, no new-conversation surface. The rename/archive/unarchive **endpoints
   exist and are tested**, but nothing in the UI calls them — the only way to archive today is
   curl.
2. **`ConversationControls.tsx` still holds the old overflow menu**, and it is now a *second*
   conversation switcher disagreeing with the rail. Section 9 deletes it. Until then the app has
   two ways to switch conversations and they do not share selection state.
3. **`AgentOutputPanel` still owns `selectedConversationId`.** Clicking a conversation in the rail
   navigates (the destination carries `conversationId`) but the panel's own auto-select-first
   effect may clobber it. **This is section 8 and it is the most likely source of a "clicking the
   rail does nothing" bug report.** Not observed, not tested — see Verification.
4. **`AgentsPage.tsx` / `AgentDetailPanel.tsx` still exist and are still unreachable.** Section 9.4
   deletes them.
5. **Nothing has been checked in light mode.** Task 11.10, carried unmet from the previous change.
6. **Title generation has never spawned a real CLI.** Every test fakes `_run_titler`. Task 11.9.
7. Everything from handoff-0015's known-broken list that is not listed above is still true —
   Codex per-file paths (follow-up #4) unstarted, three older openspec changes in flight.

## Files touched

`git status --short` is **empty** — working tree clean, everything committed.
`git log --oneline -6` = the six commits above. 253 commits ahead of `master`, **no upstream**.

### Backend — new files

- `hub/hub/migrations/versions/0035_add_conversation_title_and_origin.py` — recreates
  `conversations` via `batch_alter_table(recreate="always")`, guarded on **both** `conversations`
  and `projects` existing. Complete.
- `hub/hub/migrations/versions/0036_add_conversation_id_to_blocking_tables.py` — adds the column
  where missing, the index everywhere. Complete.
- `hub/hub/migrations/versions/0037_add_project_title_generation_setting.py` — plain `add_column`,
  no CHECK. Complete.
- `hub/hub/conversation_titles.py` (222 lines) — `build_title_command`, `title_from_output`,
  `_run_titler`, `generate_conversation_title`, `maybe_generate_title`. Complete but **never run
  against a real CLI**.

### Backend — modified

- `hub/hub/db/models.py` — `CONVERSATION_ORIGINS`, `CONVERSATION_TITLE_MAX_LENGTH = 120`,
  `CONVERSATION_TITLE_MODES`; three new `Conversation` columns + `ck_conversations_origin`;
  `conversation_id` on `Question` and `PermissionRequest`, index added to `UnaskedQuestion`'s;
  two new `Project` columns. Complete.
- `hub/hub/conversations.py` — `title_from_message`, `name_conversation`, `backfill_titles`,
  `conversation_id_for_run`, `archivable`, `conversation_attention`, `archive`, `unarchive`;
  `new_conversation` now **requires** `origin`. Complete.
- `hub/hub/api/v1/agent_chat.py` — `ConversationResponse` gained title/origin/attention/archived_at;
  `list_conversations` gained `?lifecycle=`; new PATCH rename, POST archive, POST unarchive; new
  `conversations_router` with `GET /projects/{id}/conversations` returning
  `{conversations, archived_count}`. Complete.
- `hub/hub/api/v1/__init__.py` — mounts `project_conversations_router`. Complete.
- `hub/hub/api/v1/messages.py` — honours `body.conversation_id`, refuses an archived one with
  cause + instruction + verbatim content. Complete.
- `hub/hub/api/v1/projects.py` — `ProjectSettings` gained the two title fields; PUT validates the
  runner belongs to the project. Complete.
- `hub/hub/api/v1/agent_trigger.py` — `name_conversation` on the queued entry;
  `conversation_id_for_run` on the Codex `PermissionRequest`; `maybe_generate_title` at **both**
  run-completion sites (~line 1214 exec, ~line 1580 app-server). Complete.
- `hub/hub/api/v1/agent_actions.py` — `conversation_id` on the Claude `PermissionRequest`. Complete.
- `hub/hub/api/v1/questions.py` — `conversation_id` on `Question`; names the conversation from
  `q_text`. Complete.
- `hub/hub/api/v1/agents.py`, `hub/hub/output_recording.py`, `hub/hub/scheduler.py` — pass `origin`
  (`peer`, `operator`, `job` respectively). Complete.
- `hub/hub/mcp_server.py` — `send_message` gained `conversation_id`. Complete.
- `hub/hub/schemas/messages.py` — `MessageCreate.conversation_id`. Complete.

### Backend — tests

New: `hub/tests/test_conversation_titles.py` (16), `test_conversation_origin.py` (9),
`test_conversation_archive.py` (9), `test_conversation_archive_refusal.py` (5),
`test_archived_send_refusal.py` (7), `test_conversation_attention.py` (8),
`test_title_generation.py` (19).
Modified: `conftest.py` (new `drain_conversation` fixture), `test_migrations.py` (+3 tests, head
0037), `test_project_persistence.py` (head 0037), `test_bola.py` (+1), `test_mcp_server.py`,
`test_operator_projects_api.py`, `test_conversation_contract.py`, `test_accounting_budget.py`,
`test_agent_trigger.py`. All complete.

### Frontend — new files

- `hub/ui/src/components/layout/AgentTree.tsx` — agent rows with expander + name split,
  conversations as children, `CONVERSATION_DISPLAY_CAP = 7`, Show more/Show fewer, collapsed-agent
  waiting marker. Complete.
- `hub/ui/src/components/layout/ConversationRow.tsx` — one row; optional 2px agent-colour leading
  edge, `peer` origin chip, attention dot. Complete.
- `hub/ui/src/components/layout/RecencyView.tsx` — flat cross-agent list, "Show archived (N)".
  Complete.
- `hub/ui/src/__tests__/conversationTree.test.tsx` (12), `recencyView.test.tsx` (9). Complete.

### Frontend — modified

- `hub/ui/src/api/agentChat.ts` — `AgentConversation` gained title/origin/attention/etc,
  `ProjectConversations`, `conversationLabel()`, `useProjectConversations()`. Complete.
- `hub/ui/src/components/layout/Sidebar.tsx` — `railView` state + toggle, `AGENTS_EXPANDED_KEY`,
  delegates to `AgentTree`/`RecencyView`. Complete.
- `hub/ui/src/App.tsx` — passes `activeConversation` and `onOpenConversation`. Complete.
- Five test fixtures gained the four now-required fields: `agentHandoff.test.tsx`,
  `agentRunningComposer.test.tsx`, `batchedQuestionComposer.test.tsx`,
  `composerModelControls.test.tsx`, `conversationControls.test.tsx`. `projectRail.test.tsx` gained
  a `QueryClientProvider`. Complete.
- `hub/hub/static/ui/**` — rebuilt twice. Current bundle `assets/index-BTpElNWl.js`.

### openspec

- `tasks.md` — 47 boxes ticked, plus three prose notes recording where the plan did not survive
  contact (under §2 and §4).
- `specs/agent-conversation-workspace/spec.md` — one ADDED requirement paragraph and one scenario
  for the recency view's archived control (the operator's decision, recorded 2026-08-08).

## Key decisions

1. **Task 2.9 specified a failure that could not happen; the operator chose to make it real.**
   `send_message` addresses an *agent*, never a conversation, and `latest_open_conversation`
   already skips archived rows — "a send whose recipient conversation is archived" had no code
   path. `MessageCreate` and the MCP tool gained an optional `conversation_id`. Unset is exactly
   today's behaviour. Rejected: leaving 2.9/2.10/3.5 unimplemented (the requirement would ship as
   dead prose); refusing when the *latest* conversation is archived (blocks all peer messages to
   an agent whose last thread was archived, contradicting design.md's own reasoning).
2. **No `Run` row for a titling spawn, against design.md's wording.** design.md said "a one-shot
   run bound to no conversation", citing `Run.conversation_id` being nullable. But
   `turn_scheduler.schedule_agent` and `trigger_agent_directly` both gate on
   `Run.agent == a, Run.status == "running"` — a titling run under the agent's name makes it look
   busy and stalls its queue. A `conversation_titled` event carries the observability instead.
3. **No CHECK constraint on `projects.conversation_title_mode`.** Adding one means recreating a
   table 22 foreign keys point at, to guard two values validated where they are set.
   `permission_requests.status` made the same trade.
4. **`Project.conversation_title_runner_id` is not a ForeignKey.** `runners.project_id` already
   points at `projects`; closing the loop makes the two tables unsortable for DDL (SQLAlchemy
   raises at `create_all`). Validated in the PUT handler instead.
5. **Task 5.1 resolved as a project-wide listing**, not per-agent fetches. `GET
   /projects/{id}/conversations`. One request rather than one per expanded agent: no waterfall on
   expand, the recency view reads the same cache, and it is where 2.8's `archived_count` belongs —
   a "Show archived (N)" control cannot state N from a response that omitted them.
6. **The cap is 7** (operator's call, 2026-08-08). Three agents expanded at 7 each is 25 rows with
   their parents, which fits a rail without scrolling.
7. **An agent row shows a waiting marker while collapsed.** Not in the task list. Attention state
   that only appears under an expanded agent solves nothing — the operator would still expand every
   agent to find the one that stopped for them.
8. **Titles backfill lazily on first read**, not in a data migration. The migration would have to
   reproduce word-boundary truncation in SQL, and a conversation whose queue entries were pruned
   has no title to derive either way. Those stay `null` and render as "New conversation".
9. **The recency view hides archived conversations and states the count** (operator: *"The recency
   doesn't show archived conversations. But you can expand the archived ones. There should be a
   button show archived or something like that"*). The archived list is only fetched once asked for.
10. **Origin assignment per call site**: `agents.py:1067` → `peer` (a peer asked for the agent to
    exist), `agent_trigger.py` → `operator` (that route queues `origin_type="operator"`),
    `messages.py` → `peer`, `questions.py` → `operator`, `scheduler.py` → `job`,
    `output_recording.py` → `operator` (fallback for self-reported output the Hub did not open).

## Constraints and user directives (verbatim)

**From this session:**
- *"no need for backups everything is test env"* — said when warned that migrating the real
  database rebuilds the `conversations` table.
- *"The recency doesn't show archived conversations. But you can expand the archived ones. There
  should be a button show archived or something like that"*
- *"Once we expand with show more there is no button with show less."* (Fixed in `179cf8b`.)
- *"What is taking so long?"* and *"The test is taking very long why?"* — **the operator is
  sensitive to wall-clock time.** `pytest hub/tests/` is ~3:40 for 1060 tests. Run targeted files
  during development and one full sweep before committing. Do **not** re-run the whole suite after
  every small fix.
- On the cap: the operator asked what it was, and accepted 7 without objection after the
  explanation.

**Carried from handoff-0013/0014/0015 and still binding:**
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter with
  highlight on the cards just like T3. It should feel as a extension of the chat box"*
- *"using right click is nice but no everyone will think about it. So your instinct to show three
  dots is good. I think we should go with that."* — **section 7 must use a visible `⋯` control,
  not right-click-only.**
- *"handoff need a explicit place to sit. Where we know it's there. Users might not know of forget
  about the handoff."* — **section 9.1: a persistent labelled control on the conversation header,
  never a menu item.**
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly, never `git add -A`; openspec, never aw-spec skills; `Icon` is the only
  icon system (**icon names are the Material-style keys in `Icon.tsx`'s map — `schedule`,
  `smart_toy`, etc., not lucide component names**); `approve_tool_call` keeps **no return
  annotation**; `hub/hub/static/ui` is a committed build artefact that must be refreshed after
  `npm run build` and confirmed with `diff -rq`; never mark a task complete on the strength of a
  plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All six commits this session were unprompted.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. **Done at
  session start** — see Verification. **Repeat next session.**

## Dead ends

- **`op.batch_alter_table("conversations", recreate="always")` fails with
  `NoSuchTableError: projects`** on an alembic-only upgrade. Recreating reflects the table, and
  reflecting it resolves its foreign key to `projects`, which does not exist when alembic runs
  without `create_all`. Fix: guard on **both** tables, exactly as `0019` does. This cost one full
  test-suite run to diagnose.
- **A CHECK constraint on `runners.cli` (`ck_runners_cli`) makes an unsupported CLI unreachable
  even by direct SQL.** A test that tried to write `cli = "kimi"` to prove the titler's guard
  raised `IntegrityError`. The guard is kept as defence for a third CLI and tested at the
  `build_title_command` level only.
- **Binding a runner before triggering an agent makes tests spawn a real `claude`.** Four tests in
  `test_title_generation.py` spent **3.6s each in teardown** waiting on a CLI that is not installed.
  Trigger first — `trigger_agent_directly` refuses to spawn an agent with no bound runner — then
  bind. That file went 24s → 2.1s and the suite 4:16 → 3:39.
- **`mcp_server.send_message` is a plain function, not a FastMCP object.** `send_message.fn(...)`
  raises `AttributeError`; call it directly.
- **`QuestionCreate` requires `from_agent`, `options` (min 2), `header` and `multi_select`.** A
  fixture with only `question` and `blocking` fails validation with four errors.
- **`AgentSummary` (from `@/api/agents`) has no `id` or `color_index`.** The rail's agents are
  `ProjectAgentSummary` from `@/api/projects`.
- **`localhost:8010/api/v1/projects/Agentweave/...` returns "Project not found"** despite
  `hub/.env` naming it. The real project is `proj-84d218db`.
- **My own test encoded the Show-more bug**, asserting the expander disappears after expanding.
  The operator caught it by running the app. A green suite proved nothing here.
- Carried and still true: **`pytest tests/` recreates `.agentweave/` at the repo root** (removed
  manually this session; it is *not* gitignored, so it shows up as untracked); **`openspec
  validate` reads only a requirement's FIRST LINE for `SHALL`/`MUST`**; **the `openspec` CLI
  cannot manage a date-prefixed change** (`openspec new change` / `status --change` reject a
  leading digit; `list`, `validate --changes`, `change show` are fine); **the default `python` on
  PATH has no pytest — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`**.

## Verification

**Ran, with real output:**
- **Live verification of handoff-0015's claims at session start** (the standing directive):
  `pytest hub/tests/ -q` → **983 passed, 10 skipped**, matching its recorded figure exactly. The
  three openspec changes were on disk as described. Also verified the un-handed-off commit
  `2c8b807`'s three load-bearing citations: `tasks.py:183-184` is a bare
  `task.status = body.status`; `schemas/tasks.py:105-110` checks set membership; `mcp_server.py:244`
  `update_task` accepts any status. All accurate.
- `pytest hub/tests/ -q` → **1060 passed, 10 skipped** in 3:54 (final full run before `9f77e45`).
- `pytest tests/ -q` → **372 passed, 3 skipped**. (Created `.agentweave/` at the repo root; removed.)
- `cd hub/ui && npx vitest run` → **549 passed, 62 files** (up from 528 at session start).
- `npx tsc --noEmit` → clean.
- `ruff check hub/hub/` → **3 errors, unchanged from the pre-session baseline.**
- `npx openspec validate --changes --strict` → 4 passed, 2 failed — the two failures are the
  handoff-rework and spec-execution-coordinator **skeletons, intentionally**.
- **Live, against the real database:** alembic head `0037`; 35 conversations preserved through
  0035's rebuild; `ck_conversations_lifecycle` and `ck_conversations_origin` both present in the
  DDL; all three indexes present; 77 `runs` rows still reference conversations; 35/35 titled after
  the backfill, longest 119 chars.
- **Live, against the running Hub:** `/openapi.json` lists all six conversation routes;
  `GET /projects/proj-84d218db/conversations` returns 35 open / 0 archived with titles and origins;
  the served bundle is the freshly built `index-BTpElNWl.js`.

**Explicitly NOT run/tested — do not assume:**
- **Nothing has been driven in a browser by me.** The operator opened the app and immediately found
  two things the suite could not: the missing "Show less", and that the recency view did not exist.
  Treat the rail as unvalidated by eye.
- **Light mode unchecked** on every new surface (11.10).
- **Title generation has never spawned a real `claude` or `codex`.** `_run_titler` is faked in
  every test. Whether the real CLIs print a usable title, and whether `title_from_output`'s
  last-non-empty-line rule survives real Codex chatter, is **unknown**. Task 11.9.
- **The rail↔`AgentOutputPanel` interaction is untested.** Clicking a conversation in the rail
  navigates, but `AgentOutputPanel` still owns `selectedConversationId` and auto-selects the first
  conversation. Whether the panel actually follows the rail, or fights it, **was never checked** —
  in tests or in the app. This is section 8's whole subject.
- Live tasks 11.6, 11.7, 11.8 not performed — no archive, rename, or archived-send was exercised
  through the running app, only through the test suite.
- `mkdocs build` not run.

## Git state

Branch `hub-native-experience`, HEAD `179cf8b`, **working tree clean**. **No upstream — nothing has
ever been pushed on this branch. 253 commits ahead of `master`** (was 245 at handoff-0015).

Six commits this session: `5b8d21a`, `37983d3`, `b259ae7`, `15880a0`, `9f77e45`, `179cf8b`.

**openspec in flight (6):** `2026-08-07-conversation-navigation` (**47/78**),
`2026-08-07-spec-execution-coordinator` (0/29, gated skeleton — do not start),
`2026-08-07-conversation-handoff-rework` (0/24, gated skeleton — do not start),
`2026-08-04-hub-charcoal-visual-refresh` (39/42), `2026-08-04-hub-contextual-navigation` (43/45),
`2026-07-30-hub-native-experience` (119/188).

## Next steps

1. **Start section 8 before section 7.** Open `hub/ui/src/components/agents/AgentOutputPanel.tsx`
   and read the effect at ~line 145 that auto-selects `conversations[0]`, plus the
   `selectedConversationId` state it seeds. Task 8.1: delete that state and accept the conversation
   as a prop from the destination. **Do this first because the rail is already shipped and the
   panel may currently be fighting it** — a bug the operator will hit the moment they click a
   conversation. `design.md` warns this is the most effect-dense component in the UI and that
   8.1–8.3 must not land as one commit (task 8.5).
2. **Then section 7's row menus.** `@radix-ui/react-dropdown-menu` is already a dependency. A
   visible `⋯` on the row, not right-click-only (operator directive). Conversation menu: rename,
   archive — **both endpoints already exist and are tested**, so this is pure UI. Note the dead
   end from handoff-0014: **Radix menus do not open from a synthetic `.click()`** in tests.
3. **Then section 9** — handoff onto the conversation header as a persistent labelled control,
   then delete `ConversationControls.tsx`'s overflow menu, `AgentsPage.tsx` and
   `AgentDetailPanel.tsx`.
4. **Section 11's live checks**, especially **11.9** (does a real CLI produce a usable title?) and
   **11.10** (light mode). 11.5 is done and must be redone after any further UI change.
5. **Ask the operator to look at the rail again** once section 8 lands. They found two defects in
   under a minute that 549 passing tests did not.
6. Carried and unresolved: the three older openspec changes; `pytest tests/` writing
   `.agentweave/` to the repo root; Codex per-file approval paths; the specification program.

## Open questions for the user

1. **Should `pytest-xdist` be added?** The suite is 1060 tests in ~3:40, already isolated per test,
   and the operator has twice asked why it is slow. Offered, not yet answered.
2. **Is the 120-character title cap too long?** The backfill produced titles like *"Call your
   mcp__agentweave__ask_user tool (it is an MCP tool available to you) to ask which package manager
   to use."* In a 252px rail almost all of them ellipsise before becoming distinguishable. This is
   the strongest argument yet for turning generation on — but it may also mean the *stored* cap
   should be shorter.
3. **Should `origin: peer` be visually distinct in the tree, or only in the conversation header?**
   Currently a small `peer` chip on the row. Carried from handoff-0015; implemented one way without
   an explicit answer.
4. Should `hub-native-experience` be pushed? Still no upstream, now **253** commits ahead. Carried
   unresolved since handoff-0012.
5. Should the Hub gain project/agent deletion? (Carried from handoff-0012.)
6. `npm run lint` in `hub/ui` does not start (ESLint 9, no flat config). Pre-existing.
7. Should the database backup at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept? The
   operator said this session that *"everything is test env"*, which probably answers it.
8. Should `.claude/handoffs/` stay tracked? It is (101 files).

## Read on resume

- `openspec/changes/2026-08-07-conversation-navigation/tasks.md` — the remaining 31 tasks, and the
  three prose notes recording where the plan did not survive contact. Start here.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — next step 1's target. The
  `selectedConversationId` state and the auto-select-first effect at ~line 145.
- `hub/ui/src/components/layout/AgentTree.tsx` — the shipped tree, so section 7's menus attach to
  the right rows and reuse `CONVERSATION_DISPLAY_CAP`.
- `hub/hub/api/v1/agent_chat.py` — the endpoints section 7's menus will call: PATCH rename, POST
  archive, POST unarchive, and `GET /projects/{id}/conversations`.
- `openspec/changes/2026-08-07-conversation-navigation/design.md` — the 8 decisions with their
  rejected alternatives. Read before deviating; note that decisions 2 and 8 above already deviate
  deliberately and say why.
- `hub/ui/src/components/agents/ConversationControls.tsx` — the overflow menu section 9 deletes,
  and currently a second conversation switcher competing with the rail.
