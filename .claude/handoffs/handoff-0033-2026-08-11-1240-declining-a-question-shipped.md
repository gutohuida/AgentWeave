# Handoff: declining a question shipped; three changes now await one live-agent run

**Date:** 2026-08-11T12:40+01:00 · **Branch:** hub-native-experience · **HEAD:** `7fa1fcc`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0032-2026-08-10-2205-blocked-and-conversation-binding-shipped.md`
**Status:** **chunk complete.** `2026-08-11-declining-a-question` is implemented, verified live,
committed and **pushed**. Working tree clean, nothing unpushed. Only human-only checks remain, on
this change and on the two before it.

## Goal

Handoff 0032 shipped `2026-08-10-blocked-and-conversation-binding`. This session opened the app for
the operator to test it, and they immediately hit a defect in the surrounding surface:

> *"We need a way to close the answer box without answering. Why? Because for example it asked me a
> question once, I didn't respond, and then it tried again — I responded. But once I sent an answer
> the first question was still there... In some cases we might want this behavior, in others we
> don't. We need a way to not answer and free the screen."*

That is now built. The *why* that matters for judgement calls: an unanswered blocking question is
what parks a task as `blocked`, so "close without answering" is not a UI convenience — it decides
what happens to a task, and to an agent that is still waiting.

## Current state

**Shipped and live on `:8010`** (Hub restarted this session, PID 12492 → **21272**, migration `0061`
applied to the real database).

A question can be declined: closed without answering. Three consequences, all settled with the
operator before implementation:

- **A waiting agent is told.** `ask_user` ends on answered *or* declined and reports which, instead
  of spending its full `AW_QUESTION_TIMEOUT` on a decision already made.
- **A parked task is released.** If the question had put a task in `blocked`, declining returns it
  to `in_progress` and clears the reason.
- **Dead questions stop cutting the line.** A question whose asking run has ended is marked
  "no longer waiting" and sorts behind live ones.

**All implementation tasks done; 2 human-only checks open** (`6.8`, `6.9`).

### What is NOT done, and matters

- **No agent process has ever been spawned against any of the last three changes.** Everything is
  unit tests plus probes against database copies. Three user test guides are now queued:
  `2026-08-10-run-task-binding` (step 6), `2026-08-10-blocked-and-conversation-binding` (8c, six
  steps), `2026-08-11-declining-a-question` (6c, five steps).
- **The single most important unverified behaviour is decline-step 2**: that a *real* `ask_user`
  call ends promptly when the operator declines. The poll change is tested against a stubbed Hub
  only. If the agent sits there anyway after a dismiss, that is the failure.

## Files touched

Working tree **clean**, **nothing unpushed**. Two commits this session (`90ec75d`, `7fa1fcc`), both
pushed.

| path | what | done? |
|---|---|---|
| `hub/hub/db/models.py` | `Question.declined`, `Question.declined_at` | yes |
| `hub/hub/migrations/versions/0061_add_question_declined.py` | **new**, guarded, no backfill | yes |
| `hub/hub/api/v1/questions.py` | `POST /questions/{id}/decline`; `_with_asker_state` computes `asker_waiting` in one query; `release_block_for_answer` → `release_block_for_question` | yes |
| `hub/hub/run_task_binding.py` | `release_block_for_answer` **renamed** to `release_block_for_question`; `unanswered_blocking_question` excludes declined rows | yes |
| `hub/hub/schemas/questions.py` | `declined`, `declined_at`, `asker_waiting` on `QuestionResponse` | yes |
| `hub/hub/mcp_server.py` | `ask_user` poll ends on declined; `ask_user` docstring states the three outcomes; the `note` distinguishes declined from expired; `get_answer` returns `declined` and treats it as not-pending | yes |
| `hub/ui/src/api/questions.ts` | `declined`/`declined_at`/`asker_waiting` on `Question`; `useDeclineQuestion` | yes |
| `hub/ui/src/lib/pendingQuestions.ts` | skips declined; sort key now `(not asker_waiting, batch_index, created_at)` | yes |
| `hub/ui/src/components/agents/AgentQuestionCard.tsx` | dismiss `×`, "no longer waiting" marker, `onDecline`/`isDeclining` props | yes |
| `hub/ui/src/components/agents/AgentOutputPanel.tsx` | `useDeclineQuestion`, `handleDeclineQuestion`, wired to the card | yes |
| `hub/tests/test_question_declined.py` | **new**, 12 tests | yes |
| `hub/tests/test_blocking_questions.py` | 4 tests appended (poll ends on decline; decline ≠ expiry; mixed batch; `get_answer`) | yes |
| `hub/tests/test_migrations.py` | head → `0061`; 3 new per-migration tests | yes |
| `hub/tests/test_project_persistence.py` | head assertion → `0061` | yes |
| `hub/tests/test_mcp_server.py` | `get_answer` expectation gains `declined` | yes |
| `hub/tests/test_task_blocked.py` | follows the `release_block_for_question` rename | yes |
| `hub/ui/src/__tests__/pendingQuestions.test.ts` | 6 tests, incl. **batch contiguity** | yes |
| `hub/ui/src/__tests__/agentQuestionCard.test.tsx` | 6 tests for dismiss + stale marker | yes |
| `agentHandoff`, `agentRunningComposer`, `batchedQuestionComposer`, `composerPermissionDefault`, `conversationControls`, `conversationDestination`, `conversationShell`, `handoffPlacement`, `specChatSurface` `.test.tsx` | each `vi.mock('@/api/questions')` gains `useDeclineQuestion` | yes |
| `hub/hub/static/ui/**` | rebuilt, `diff -rq` identical | yes |
| `openspec/changes/2026-08-11-declining-a-question/` | proposal, design D1–D6, 2 delta specs, tasks | yes |
| `openspec/specs/agent-capability-plane/spec.md`, `task-lifecycle-governance/spec.md` | deltas applied | yes |

## Key decisions

Full rationale in `openspec/changes/2026-08-11-declining-a-question/design.md` (D1–D6).

1. **D1 — declining is its own terminal state, not an empty answer.** `declined` beside `answered`.
   Collapsing them would make every reader of `answered` treat a decline as an answer — including
   `unanswered_blocking_question`, which decides whether a task is parked. *Rejected: a `status`
   enum replacing `answered`* — cleaner on paper, touches every query, schema and UI path that reads
   `answered`, for a distinction two booleans express exactly.
2. **D2 — a decline ends the agent's wait, and is reported distinctly from an expiry.** An expiry
   means nobody was there; a decline means someone was and chose not to answer, which says the call
   is the agent's. *Rejected: letting it time out* — spends the interval on a decision already made
   and makes declining feel inert.
3. **D3 — declining releases a parked task, through the same function answering uses.** Two
   functions differing only in what settled the question would be two things to keep in step, and a
   block released one way but not the other is precisely the bug. Hence the rename.
4. **D4 — a declined question does not park a task.** Without it the run boundary re-parks the task
   on the question the operator just closed, and the release is undone by the mechanism meant to
   satisfy it.
5. **D5 — `asker_waiting` is computed from the asking run, and defaults to `True` when unknown.**
   Stored, it would go stale at exactly the transition it describes. Presuming "not waiting" would
   mark a live question inert and sort it behind dead ones — the worse error.
6. **D6 — live questions sort first, and batches stay contiguous by construction**, because every
   question in a batch comes from one `ask_user` call by one run and so shares one `asker_waiting`.
   Asserted, not assumed, because `activeQuestionFor` is the one selector both the card and the
   composer's send read.
7. **No reason for declining, and no reopening.** A decline ends the matter; requiring an
   explanation taxes the cheap escape this exists to provide, and if it still matters the agent asks
   again. Flagged to the operator; they have not objected.
8. **The UI release of a conversation binding is a plain async function, not a mutation hook** —
   carried from last session, and the reason 39 tests failed when first written as a hook.

## Constraints and user directives (verbatim)

**From this session:**
- *"We need a way to close the answer box without answering... In some cases we might want this
  behavior in other we don't we need a way to not answer and free the screen for use"*
- *"That's all good."* — on the six-step blocked-status test guide and the app opening.
- *"it says that live updates are disconnected. The app seems offline for some reason"* — the Hub
  had been killed at session teardown.
- Settled: declining **tells** a waiting agent; declining **releases** a parked task; a stale
  question is **marked and sorted out of the way**.

**Carried and still binding:**
- **The `ci.yml` question is settled** — the operator chose "just push the branch", not a draft PR.
  **Do not raise it again.**
- **Handoff cadence:** only when asked, or when an openspec change is done.
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and wall-clock.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task
  complete on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **A background shell started with the Bash tool dies at session teardown.** That is what took the
  Hub down mid-testing — no crash, the log just stops. **Start it via WMI so it is not a child of
  the shell:**
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
  `Start-Process` from the PowerShell tool also dies. Log lives at `%TEMP%\agentweave-hub.log` —
  **not** in the repo, where it would be untracked and un-gitignored.
- **Nine UI test files mock `@/api/questions` explicitly** (not `...actual`), so **any new export
  breaks 52 tests** across them. Adding an export means patching each mock. Two shapes exist:
  a multi-line object, and a one-liner `vi.mock('@/api/questions', () => ({ useQuestions: ... }))`.
- **`hub/ui/src/components/common/Icon.tsx` has `x`** (line 127) — no need for `close`.
- **Renaming an exported function breaks test collection for the whole suite**, not just its own
  file — `pytest hub/tests/` aborts with one ImportError. Grep for the old name after any rename.
- **`npx tsc` / `npx vitest` fail outside `hub/ui`**, and the Bash tool's cwd persists across calls.

**Carried and still true:**
- **`hub/data/agentweave.db` is the live database.** Project is `proj-cddb0827`, named **Testbed**.
- **Restarting the Hub: kill by exact PID and verify the new process bound.**
- **Static UI updates without a restart; Python does not.**
- **Git Bash `/tmp` is not what native Windows Python sees** — use a repo-relative path.
- **`openspec` CLI rejects change names starting with a digit** — create letter-initial, then `mv`.
  **There is no `openspec sync`**; the deltas are applied by hand.
- **The visual-language contract rejects raw hex**, including as a `var(--x, #fallback)` default.
- **`test_no_code_path_deletes_conversations_outside_reset` flags `@router.delete(...)`** lines
  carrying `response_model=ConversationResponse`; the scan now skips decorator lines.
- **`session.get(RunDivergence, id)` does not work** — the primary key is `sequence`.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. **The default `python`
  has no pytest** — use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check.
- **`black` warns "Python 3.11 cannot parse code formatted for Python 3.12"** — a warning, not a
  failure.
- **`preview_snapshot` is unreliable**; **`preview_press` and `preview_resize` do not work.**

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1500 passed, 10 skipped** (1481 at this change's start).
- `pytest tests/ -q` — **372 passed, 3 skipped.**
- `npx vitest run` — **751 passed across 79 files** (739 at start). `npx tsc --noEmit` clean.
- `ruff check hub/ src/` clean; `black` — 287 files unchanged after formatting.
- `npx openspec validate --specs --strict` — **29 passed**; `--changes --strict` — **8 passed**.
- `npm run build` + `rm -rf` + copy + `diff -rq` — identical.
- **Live:** Hub restarted by exact PID (12492 stopped, port confirmed free, **21272** bound). Proved
  new **behaviourally** — `/openapi.json` publishes `declined` and `asker_waiting` on
  `QuestionResponse` and the `POST .../questions/{id}/decline` route. Migration `0061` on the real
  database, **no backfill** (0 declined rows).
- **Behavioural probe against a copy of the real database** (`proj-cddb0827`, agent `claude-1`):
  an unanswered blocking question parked the task with its text as the reason; declining released it
  to `in_progress` and cleared the reason; a later run's boundary check did **not** re-park it on
  the closed question and **did** record a divergence (`div-92e9e7ef`) — the decline holds and the
  check resumes. Copy deleted; **the live board was not written to** (0 probe rows).

**Not verified, and deliberately:**
- **No agent process was ever spawned**, for this change or the two before it.
- **Decline-step 2 is the weakest claim**: no real `ask_user` call has ever been declined. The poll
  change is tested only against a stubbed `_hub_request`.
- **Nobody has looked at the dismiss control or the "no longer waiting" marker visually.**
- **The Codex path is wired but never live-exercised** for any of the three changes.
- **CI has still never run on this branch** — settled as intentional; do not raise it.
- **The permission defect is untouched** —
  `openspec/explorations/2026-08-10-operator-approval-not-honoured.md`.

## Git state

Branch `hub-native-experience`, HEAD **`7fa1fcc`**, working tree **clean**, **0 unpushed commits**
(`origin/hub-native-experience` is at HEAD). **378 ahead of local `master`, 382 ahead of
`origin/master`.**

Hub running as PID **21272** on `:8010`, started via WMI so it survives session teardown.

## Next steps

1. **Run the three user test guides against a live agent, in `testbed/` or the Testbed project.**
   Start with `openspec/changes/2026-08-11-declining-a-question/tasks.md` §6c step 2 — get
   `claude-test-1` to ask a blocking question, then dismiss it while the run is still going, and
   confirm the agent continues promptly rather than sitting until its question timeout. That single
   step is the weakest claim across all three changes.
2. **Then §6c steps 1, 3, 4, 5**, and the six steps in
   `openspec/changes/2026-08-10-blocked-and-conversation-binding/tasks.md` §8c.
3. **Archive whichever changes pass**, via `openspec-archive-change`. Three are waiting:
   `2026-08-10-run-task-binding`, `2026-08-10-blocked-and-conversation-binding`,
   `2026-08-11-declining-a-question`.
4. **The permission defect** — the highest-value untouched item.
5. **Remaining roadmap:** A2 (shell conformance audit), B0 (blocked on the charter-count decision),
   then B2–B7.

## Open questions for the user

1. **Should declining carry a reason, or be reopenable?** Both were deliberately left out; flagged
   to the operator, no objection yet. `6.11` in the tasks file is the check on whether that matters.
2. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks archiving
   `hub-charcoal-visual-refresh` (8.11).
3. **How many charters, and which non-software domains?** Still blocks B0.
4. Carried: should `.claude/handoffs/` stay tracked (**119 files, confirmed not gitignored**);
   `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.

## Read on resume

- **This file's "Dead ends" first** — the Hub-start-via-WMI recipe is needed to test anything, and
  the nine-mock trap will bite on any new `@/api/questions` export.
- `openspec/changes/2026-08-11-declining-a-question/design.md` — D1–D6, and `tasks.md` §6c, which is
  next-step 1.
- `openspec/changes/2026-08-10-blocked-and-conversation-binding/tasks.md` §8c — the six steps queued
  behind it.
- `hub/hub/run_task_binding.py` — binding, waiting, the boundary question, and the conversation
  binding all live here now.
- `hub/hub/mcp_server.py` `ask_user` — the poll loop and the three outcomes an agent is told.
- `hub/ui/src/lib/pendingQuestions.ts` — the one selector both the question card and the composer's
  send read; the sort order is the risky part of this change.
