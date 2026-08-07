# Handoff: unasked-question backstop, batched questions, per-agent waits, then a housekeeping sweep

**Date:** 2026-08-07T20:11 · **Branch:** hub-native-experience · **HEAD:** 1b3f943
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0013-2026-08-07-1610-operator-in-the-loop-permissions-and-questions.md
**Status:** chunk complete. 17 commits, working tree clean, all suites green. Three of the
operator's five follow-ups from handoff-0013 are done (#1, #2, #3); #4 and #5 are not started.

## Goal

Close the operator's chosen follow-ups from handoff-0013 — a backstop for questions an agent never
asks, batched questions, and configurable waits — then answer the operator's design question about
where agent settings live, then a housekeeping sweep of stale docs, dead files and the openspec
backlog.

The *why* behind the sweep: the operator asked what is next for AgentWeave before redesigning
navigation. Answering that surfaced that the repo's own guidance documents describe subsystems
deleted weeks ago, which makes every future session start from a false picture.

## Current state

### Shipped, tested, and live-verified

**1. Unasked-question backstop** (`2026-08-07-unasked-question-backstop`, archived). A run that
completes on a trailing question having opened no `Question` row records an `UnaskedQuestion` and
broadcasts `question_not_asked`. Card above the composer with **Ask this properly** (re-prompts the
agent server-side) and **Dismiss**.

- Three suppressions: run not `completed`; run already opened a `Question` (via
  `Question.created_by_run_id`); agent's inbound queue non-empty (checked with the scheduler's own
  `queued_entries`, before `schedule_agent` runs).
- Whole check is wrapped — a backstop must never worsen the run it observes.

**2. Batched questions** (`2026-08-07-batched-operator-questions`, archived). `ask_user` now takes
`questions`, a list of 1–4. **The single-question signature is gone.** Rows share a `batch_id`;
`batch_index` and `batch_size` ride on each row. `POST /agent-actions/questions/batch`.

- `hub/ui/src/lib/pendingQuestions.ts` → `activeQuestionFor(questions, agent)` is the single
  selector used by *both* the card and the panel, so the composer cannot answer a different question
  from the one displayed.
- The `N/M` counter is now a real step counter, not a count of outstanding questions.

**3. Per-agent waits** (`2026-08-07-per-agent-waiting-settings`, archived).
`Agent.permission_timeout_seconds` / `question_timeout_seconds`, nullable (NULL = built-in default),
bounded 10–600. Reach the spawned tool process as `AW_DECISION_TIMEOUT` / `AW_QUESTION_TIMEOUT`.
`AgentInfoTab` gained **Bindings** and **Waiting for you** sections on `SettingsSection`/`SettingsRow`.

**4. Housekeeping.** Details under Files touched. Five openspec changes archived (8 in-flight → 3),
two specs reconciled, four root docs rewritten, dead files deleted, untracked work committed.

### Known-broken / not done

1. **`#4` (Codex per-file paths) not started.** Its file-change approvals carry only `grantRoot`,
   live `null`. Handoff-0013's suggestion: investigate whether `map_item_to_events` in
   `hub/hub/codex_appserver.py` already sees the file list and can be correlated by
   `itemId`/`turnId`. Exploration first — do not build until it is known to be recoverable.
2. **`#5` (real sandboxing) explicitly dropped by the operator:** *"let's skip this one for now."*
3. **Agent settings are hard to reach.** Operator: *"kind of confusing and hard to find. Also those
   3 buttons showing all the conversations is not good."* Path today: conversation → **⋮**
   ("Conversation actions") → scroll past "New conversation" and ~16 `conv-…` entries → **Agent
   details** at the bottom. This is unfixed and is the operator's next intended work.
4. **`AgentsPage` / `AgentDetailPanel` are unreachable.** Nothing imports `AgentsPage` outside its
   own file and tests. The "Settings" tab rename I made lives there and is therefore **inert**; the
   reachable surface is the drawer at `ConversationControls.tsx:224`, which renders `AgentInfoTab`
   directly under a "{agent} details" heading and has no tab label.
5. **Three openspec changes still in flight**, all needing new capability spec files that do not
   exist yet — see Next steps 4.

## Files touched

Full list: `git diff --name-only 96884f4..HEAD` (111 files, +11535/−1600, incl. `hub/hub/static/ui`).

**Backend — backstop**
- `hub/hub/unasked_question.py` — **new.** Pure `trailing_question(text) -> str`; `MAX_QUESTION_CHARS=400`. Complete.
- `hub/hub/api/v1/unasked_questions.py` — **new.** List / dismiss / ask, plus `REPROMPT_TEMPLATE`. Complete.
- `hub/hub/api/v1/agent_trigger.py` — `_flag_unasked_question`, called from **both** completion sites
  before `schedule_agent`; `_codex_decision_timeout`; `_await_operator_permission` gained
  `timeout_seconds`; `AW_DECISION_TIMEOUT`/`AW_QUESTION_TIMEOUT` added to spawn env. Complete.
- `hub/hub/api/v1/agent_actions.py` — `severity="warning"` → `"warn"`; `AgentQuestionBatchCreate`,
  `AgentQuestionBatchResponse`, `POST /questions/batch`. Complete.
- `hub/hub/api/v1/permissions.py` — `severity="warning"` → `"warn"`. Complete.
- `hub/hub/api/v1/questions.py` — `ask_question_for_actor` gained `batch_id`/`batch_index`/`batch_size`. Complete.
- `hub/hub/api/v1/agents.py` — `MIN_WAITING_SECONDS=10`, `MAX_WAITING_SECONDS=600`,
  `WAITING_SETTING_FIELDS`, `_validated_waiting_seconds`; both fields in PATCH, in
  `_unrestricted_fields`, and on the roster; `_tool_surface_lines()` describes `ask_user(questions)`. Complete.
- `hub/hub/api/v1/__init__.py` — registers `unasked_questions_router`. Complete.
- `hub/hub/mcp_server.py` — `ask_user` takes a list and polls every id; `_configured_wait`;
  `MIN/MAX_WAITING_SECONDS` restated. Complete.
- `hub/hub/db/models.py` — `UnaskedQuestion`; `Question.batch_id/batch_index/batch_size`;
  `Agent.permission_timeout_seconds/question_timeout_seconds`. Complete.
- `hub/hub/schemas/questions.py` / `schemas/agents.py` — batch fields; waiting fields. Complete.
- Migrations `0032_add_unasked_questions.py`, `0033_add_question_batches.py`,
  `0034_add_agent_waiting_settings.py`. **Head is 0034.** 0033/0034 guard for a missing table.

**Frontend**
- `hub/ui/src/lib/pendingQuestions.ts` — **new.** `activeQuestionFor`. Complete.
- `hub/ui/src/api/unaskedQuestions.ts` — **new.** Complete.
- `hub/ui/src/components/agents/UnaskedQuestionCard.tsx` — **new.** Complete.
- `hub/ui/src/components/agents/AgentQuestionCard.tsx` — uses the selector; real step counter;
  "Then N more." hint. Complete.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — mounts `UnaskedQuestionCard`; uses the
  selector; **`answerPendingQuestion` gained a `chosenLabels` parameter (bug fix, see Dead ends).** Complete.
- `hub/ui/src/components/agents/AgentInfoTab.tsx` — `WaitingSetting` component; Bindings and
  "Waiting for you" `SettingsSection`s; bindings moved out of "Roles & Configuration". Complete.
- `hub/ui/src/components/agents/AgentDetailPanel.tsx` — `info` tab labelled "Settings". **Inert** (see above).
- `hub/ui/src/api/questions.ts`, `api/agents.ts`, `api/runners.ts` (`useUpdateAgentWaiting`,
  `MIN/MAX_WAITING_SECONDS`), `hooks/useSSE.ts`, `lib/eventSummary.ts`. Complete.
- `hub/hub/static/ui/**` — rebuilt and **currently in sync**.

**Tests — new:** `hub/tests/test_unasked_question.py`, `test_unasked_question_backstop.py`,
`test_question_batches.py`, `test_agent_waiting_settings.py`;
`hub/ui/src/__tests__/unaskedQuestionCard.test.tsx`, `pendingQuestions.test.ts`,
`batchedQuestionComposer.test.tsx`, `agentWaitingSettings.test.tsx`.
**Modified:** `test_blocking_questions.py` (rewritten for the list contract), `test_mcp_server.py`,
`test_bola.py`, `test_migrations.py`, `test_project_persistence.py`,
`test_agent_actions_coordination.py`, and four frontend suites needing new mocks
(`conversationControls`, `agentRunningComposer`, `agentHandoff`, `runnersUi`, `chartersUi`).

**Housekeeping**
- **Deleted:** `AI_CONTEXT.md` (unfilled template at repo root), `.agentweave/` (stray, forbidden —
  **but see below, it comes back**), `src/agentweave/templates/roles/` + `hub/hub/data/roles/`
  (empty), `VALID_ROLES`, `WATCHDOG_PID_FILE` and `WATCHDOG_LOG_FILE` in
  `src/agentweave/constants.py` (`WATCHDOG_HEARTBEAT_FILE` kept — 5 live readers), `sync-roles` in
  `Makefile`.
- **Rewritten:** `CLAUDE.md` (architecture tree was wrong in both directions), `ROADMAP.md`,
  `AGENTS.md` (524 lines → pointer), `README.md` (one claim).
- **Committed, previously untracked:** `.claude/skills/{handoff,resume,review-iteration}/`,
  `src/agentweave/templates/skills/{handoff,resume}.md`, `tests/test_handoff_resume_templates.py`,
  `scripts/sync_skills.py`, 33 handoffs, `openspec/explorations/2026-08-03-specification-authority-technical.md`.
- **openspec:** archived `2026-08-07-{unasked-question-backstop,batched-operator-questions,per-agent-waiting-settings,hub-answered-permission-approver}` and
  `2026-08-06-operator-in-the-loop-turns` (superseded). Reconciled
  `openspec/specs/agent-tool-surface/spec.md` and `openspec/specs/agent-capability-plane/spec.md`.

## Key decisions

1. **The backstop mirrors `PermissionRequest`, not `permission_denied`.** Handoff-0013 said to
   surface it "the way `permission_denied` already is". Checked against the running code and
   rejected: `permission_denied` is *not* in the conversation — it reaches the Activity log and the
   Messages tab as its own bare event name, with `reason` rendered nowhere. Copying it would have
   built a second invisible signal, which is the bug being fixed.
2. **A durable row with a status, not an `EventLog` row.** An event has no status, so a card driven
   by one could never be resolved. An `EventLog` row is *also* written, as a record, not the
   mechanism.
3. **`ask_user` always takes a list.** Rejected accepting either shape — that is the tolerant reader
   the previous change already decided against, and Claude Code's own `AskUserQuestion` always takes
   a list. 1–4; the cap is Claude Code's.
4. **One row per sub-question sharing a `batch_id`**, rejected one row holding a JSON list: every
   existing reader (answer endpoint, options storage, the backstop's `created_by_run_id` check) is
   written against one row = one question.
5. **Batch answers persist as given, departing from T3**, which holds all drafts and submits at the
   end (`buildPendingUserInputAnswers` returns `null` until complete). The agent is blocked up to
   240s; a refresh mid-batch would discard everything. **Accepted cost: an earlier answer cannot be
   revised.**
6. **`batch_size` denormalized onto every row** so the step counter works from the unanswered rows
   the panel already holds — no second request.
7. **One selector for the active question.** The card and the panel derived it independently; safe
   with one question outstanding, silently wrong with a batch (read question 2, answer question 1).
8. **Waiting settings: `NULL` means the default, not a copy of it.** A row storing today's number
   would keep saying it after the default moved, and the operator could not tell "chosen" from
   "inherited".
9. **Settings live on the agent's own tab, not behind a new gear.** `AgentInfoTab` already edited
   runner/charter bindings, and the overflow menu already opens it without unmounting the
   conversation. A gear would be a third home and would blur the distinction that makes the composer
   pills legible: **pills are this conversation, the tab is this agent.**
10. **`AGENTS.md` became a pointer, `CLAUDE.md` stays canonical.** Two ~500-line documents describing
    one repository is *how* both drifted. Claude Code loads `CLAUDE.md` automatically and drives this
    repo, so the common case stays zero-cost; Codex/Kimi/OpenCode read the pointer.
11. **`operator-in-the-loop-turns` archived as superseded, never implemented**, with a table naming
    which successor closed each bullet — so the archive does not read as work that happened.

## Constraints and user directives (verbatim)

- *"Ok, fix #1. #2: Yes. #3: Make it configurable. Should we have a config screen for agents for
  things like this and future things? Having a gear somewhere in the screen, the chat box or chat
  screen? #4: explore. #5: okay, let's skip this one for now. #6: okay."*
- *"take #2. Number 3 was more like a question to you to help me decide where is best to have the
  agent settings"*
- *"kind of confusing and hard to find. Also those 3 buttons showing all the conversations is not
  good."*
- *"Okay, first I have to know what's next to implement? I have an idea how to solve this but first
  I have to know what would be the next steps on the development of agentweave"* — **the operator has
  an unstated idea for the navigation fix. Ask for it before proposing a competing design.**
- *"So first let's do some house keeping. Fixing any specs that need fixing and archiving. Updating
  stale references like claude.md. Updating documentation. Read.me, those kind of things. Scan the
  repo and find house keeping things that need to be done. Stale files that needs deletion, files
  that need updating."*
- *"You can read all the handoffs to trace the development"*
- On card styling, from handoff-0013: *"I don't want it to be colorful it should be like the chat box
  but maybe a little lighter with highlight on the cards just like T3. It should feel as a extension
  of the chat box"*
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly, never `git add -A`; openspec, never aw-spec skills; `Icon` is the only icon
  system; never mark a task complete on the strength of a plan existing.
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All 16 commits were unprompted.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at
  session start (910/372/491 all matched handoff-0013). **Repeat next session.**

## Dead ends

- **Deleting `.agentweave/` at the repo root does not stick — `pytest tests/` recreates it.**
  Measured while validating this handoff: delete it, run the CLI suite from the repo root, and
  `.agentweave/logs/events.jsonl` is back. `logging_handlers.setup_logging()` does
  `LOGS_DIR.mkdir(parents=True, exist_ok=True)` and `LOGS_DIR` is `constants.AGENTWEAVE_DIR / "logs"`,
  which is **relative to the process cwd**. `tests/test_logging_handlers.py` exercises it.
  It is gitignored so it never gets committed, but **the repo's own test suite violates CLAUDE.md's
  "NEVER create `.agentweave/` at the repository root" rule on every run.** Do not "fix" this by
  deleting the directory again — the fix is to point those tests at a `tmp_path` log dir (see Next
  steps 7). Running `pytest hub/tests/` alone does *not* recreate it.
- **A real pre-existing bug the new tests caught:** `handleQuestionToggle` called
  `setQuestionSelection([label])` and then `answerPendingQuestion('')` **in the same tick**, which
  read `questionSelection` from a closure it had not updated — saw nothing selected and returned
  without sending. **Clicking a single-choice option did nothing and the agent kept waiting.**
  Multi-select was unaffected because it submits from the composer on a later tick, which is why it
  survived handoff-0013's live testing. Fixed by passing the label explicitly.
- **`openspec validate` reads only a requirement's FIRST LINE for `SHALL`/`MUST`.** A requirement
  with `SHALL` on line two fails with `requirements.N.text: Requirement must contain SHALL or MUST`.
  Cost a debugging cycle; the whole-paragraph check I wrote to find it reported all requirements OK.
- **Migration 0033 initially failed 9 tests** with `NoSuchTableError: questions`. Upgrades starting
  from an early revision reach a migration with only that revision's tables. Guard with
  `inspector.get_table_names()` and return early — 0034 does the same.
- **`git stash push <path>` does not stash untracked files**, so a "clean baseline" measured that way
  still included new untracked source. That is why a stashed baseline reported 493 tests instead of
  491; the real explanation was that `projectScopedApiContract.test.tsx` globs `src/api/*.ts` and
  generates tests per file, so a new API module adds two passing tests automatically.
- **`preview_click` returns a schema-validation error but the click still lands.** Verify via
  `preview_evaluate` or the API rather than retrying; retrying double-clicks.
- **Radix menus do not open from a synthetic `.click()` in `preview_evaluate`** — use `preview_click`
  for the trigger, then read the menu with `preview_evaluate`.
- Carried from handoff-0013 and still true: **`--permission-prompt-tool` has three unguessable
  details** — `tool_use_id` must be in the signature, the answer must be a JSON *string* in a text
  block, and **`structuredContent` must be absent**, which is why `approve_tool_call` has **no return
  annotation**; **background-shell Hub dies between turns** (start it detached, see Live environment);
  **Bash `/tmp` and Windows Python do not share a filesystem view**; **`cd hub/ui && npm run build`
  then `cp` with repo-relative paths fails** because the Bash tool's cwd persists.

## Verification

**Ran, with real output, final state:**
- `pytest hub/tests/ -q` — **983 passed, 10 skipped** (910 at session start).
- `pytest tests/ -q` — **372 passed, 3 skipped**.
- `cd hub/ui && npx vitest run` — **528 passed, 60 files** (491 at start). `npx tsc --noEmit` clean.
- `ruff check hub/hub/` — only the 3 pre-existing errors (2× SIM105 in `codex_appserver.py`,
  1× I001 in `api/v1/jobs.py`). None in touched files.
- `npx openspec validate --specs --strict` — **24 passed, 0 failed**.
- `npm run build` + `diff -rq hub/ui/dist hub/hub/static/ui` — identical.
- **Live**, Hub on `127.0.0.1:8010`, project `proj-84d218db`:
  - Backstop: Codex ended a turn on "Which database should I use?" as prose → detected with the exact
    text → **Ask this properly** → Codex re-asked through `ask_user` with a header and three
    described options. Dismiss worked; second action → **409**. Suppression verified live too: an
    earlier run *did* call `ask_user`, and the backstop correctly stayed silent.
  - `question_not_asked` EventLog row confirmed with `severity: "warn"`.
  - Batching: Codex asked all three in one call (`qbatch-befea52c`, indices 0–2, size 3). Stepped
    through in a **browser**: `1/3 Database` → `2/3 Package Manager` ("Then 1 more") → `3/3 Tests
    First` (hint gone). Agent returned *"`PostgreSQL`, `pnpm`, and `Yes` for tests first."*
  - Waits: set haiku-1's question wait to 30s, asked, answered nothing — it gave up at **30s** and
    reported the note verbatim. Cleared to null. Out-of-range → **400**.
  - Migrations `0031→0032`, `0032→0033`, `0033→0034` all ran against the real database.
  - Settings drawer rendered in a browser: **Bindings** and **Waiting for you** present, inputs
    showing `120`/`240` placeholders, opened from a live conversation without unmounting it.

**Explicitly NOT run/tested — do not assume:**
- **Light mode** not checked for any new CSS.
- **Codex `multi_select`** never exercised — Codex has only ever produced `multi_select: False`.
- **A batch of 4** never exercised live (3 was the maximum tried).
- **A partly-answered batch at timeout** is unit-tested only, never live.
- **`bypassPermissions`** never exercised live (carried from handoff-0013).
- **`AgentDetailPanel`'s "Settings" tab** never rendered — that surface is unrouted.
- **No charter has been bound to an agent and run** (carried unresolved since handoff-0012).
- **`mkdocs build` was not run** — docs nav was checked by script for missing targets only.
- Task 6.11 of the approver change (live failure of the reporting endpoint) — still open with a
  written reason, now in the archive.

## Git state

Branch `hub-native-experience`, HEAD `1b3f943`, **working tree clean**. **No upstream — nothing has
ever been pushed on this branch** (carried from every prior handoff). **242 commits ahead of
`master`.**

17 commits this session, oldest→newest: `c80d115`, `9449af9`, `6ad5896`, `11239e9`, `a725da5`,
`c7a0d9d`, `4ca6c2b`, `3cd0094`, `d5a2735`, `e0b2b57`, `18ce552`, `d587510`, `7eedf92`, `ccadcef`,
`95b86c1`, `d071ea6`, `1b3f943`. (`96884f4` was handoff-0013's final HEAD.) 112 files, +11538/−1604.

**openspec in flight (3, down from 8):** `2026-07-30-hub-native-experience` (119 done/69 open,
superseded by its own 2026-08-02 direction override), `2026-08-04-hub-charcoal-visual-refresh`
(39/3), `2026-08-04-hub-contextual-navigation` (43/2).

## Next steps

1. **Ask the operator for their navigation idea before designing anything.** They said *"I have an
   idea how to solve this"* and it was never stated. Do not propose a competing design first. The
   concrete problem: `hub/ui/src/components/agents/ConversationControls.tsx` builds one overflow menu
   containing "New conversation", every conversation id (16 live), "Handoff", and "Agent details"
   last — so durable agent settings sit under a conversation switcher.
2. **Scope the navigation work to anticipate the specification and governance surfaces.** Per
   `openspec/explorations/2026-08-02-product-direction.md`, those are the next two major slices and
   have no home in the shell. Fixing the menu only for today's surfaces means redoing it.
3. **Follow-up #4 — explore whether Codex's per-file paths are recoverable.** Read
   `map_item_to_events` in `hub/hub/codex_appserver.py` and check whether thread items streamed
   *before* the approval request carry the file list, correlatable by `itemId`/`turnId`. Exploration
   only; do not build until it is known to be recoverable.
4. **Decide the fate of the 3 remaining openspec changes.** Archiving them requires **creating ten
   capability spec files that do not exist** (`hub-interface-feel`, `hub-visual-language`,
   `hub-native-runtime`, `agent-conversation-timeline`, `agent-identity-and-skills`,
   `agent-inbound-queue`, `spec-authoring`, `spec-traceability`, `hub-interaction-feedback`,
   `project-environment-settings`). That is spec authoring, not housekeeping — and some describe UI
   the navigation rework may replace, so step 1 should probably come first.
5. **Delete or route `AgentsPage`/`AgentDetailPanel`.** Nothing imports `AgentsPage`; it is tested
   and maintained but unreachable. Logged as a follow-up in
   `openspec/changes/archive/2026-08-07-per-agent-waiting-settings/tasks.md`.
7. **Stop the CLI test suite writing `.agentweave/` into the repo root.** `setup_logging()` builds
   its log path from the process cwd, so `pytest tests/` creates it every run — see Dead ends. Point
   `tests/test_logging_handlers.py` (and anything else calling `setup_logging()`) at a `tmp_path`,
   or make the log root overridable by env var in the tests' conftest.
8. **The specification program remains the stated differentiator and is unstarted.** Of 13 MCP tools,
   none touch specs, reviews, evidence or gates. The direction doc says it *"should no longer be
   treated as the last slice."* It has been next since 2026-08-02.

## Open questions for the user

1. **What is the navigation idea?** (Blocks next step 1.)
2. Should `hub-native-experience` be pushed? Still no upstream, now 242 commits ahead of `master`.
   Carried unresolved since handoff-0012.
3. Should the Hub gain project/agent deletion? (Carried from handoff-0012.)
4. `npm run lint` in `hub/ui` does not start (ESLint 9, no flat config). Pre-existing.
5. Should the database backup at `C:\Users\huida\Documents\aw-db-backup-2026-08-06\` be kept?
6. Should `.claude/handoffs/` stay tracked? It now is (131 files). They are session notes, so
   gitignoring them would be defensible — but the operator explicitly used them this session to trace
   development, which argues for keeping them.

## Read on resume

- `openspec/explorations/2026-08-02-product-direction.md` — the authoritative direction, and the
  answer to "what is next". Read before proposing anything structural.
- `hub/ui/src/components/agents/ConversationControls.tsx` — the overflow menu the operator objected
  to, and where `AgentInfoTab` is mounted as a drawer (line ~224).
- `hub/ui/src/components/agents/AgentInfoTab.tsx` — the settings surface: Bindings, "Waiting for
  you", `WaitingSetting`.
- `hub/ui/src/lib/pendingQuestions.ts` — the shared active-question selector; small, and explains why
  the card and composer cannot disagree.
- `hub/hub/codex_appserver.py` — `map_item_to_events`, `_thread_policy`, `decide_approval`; needed
  for next step 3.
- `CLAUDE.md` — rewritten this session; the architecture tree is now accurate.
