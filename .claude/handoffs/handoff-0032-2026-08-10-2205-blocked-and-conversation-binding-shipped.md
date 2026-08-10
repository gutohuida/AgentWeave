# Handoff: a task can say it is waiting, and the binding outlives the run

**Date:** 2026-08-10T22:05+01:00 · **Branch:** hub-native-experience · **HEAD:** `8288f9b`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0031-2026-08-10-2052-run-task-binding-shipped-and-two-findings-proposed.md`
**Status:** **chunk complete.** `2026-08-10-blocked-and-conversation-binding` is implemented,
verified live, committed and **pushed**. Working tree clean. Only human-only checks (8b) and the
live-agent user test guide (8c) remain.

## Goal

Handoff 0031 left the successor change written but not implemented, gated on five open questions.
The operator chose to implement it, and to push the branch without a draft PR.

Two gaps in the run→task binding, both consequences of the binding being built one run at a time:

1. **An agent that stopped to ask was indistinguishable from one that dropped the work.** The run
   ended, the task had not moved, a divergence was recorded — and under `retry` the agent was
   restarted while still blocked on the same unanswered question.
2. **Only the first run of a conversation was bound.** The composer sends no `task_id`, so a
   five-turn piece of work was checked once, at the end of turn one — when an agent is most
   legitimately unfinished — and was silent for the turn where it actually stopped.

## Current state

**Shipped and live on `:8010`** (Hub restarted this session, PID 9360 → **22012**, migrations
`0058 → 0060` applied to the real database).

A ninth status, `blocked`, means work began and stopped on something only a person can supply. The
runtime records it by observing a run end with an unanswered blocking question; the answer releases
it. A blocked task is not divergent. The binding now lives on the conversation, so every turn is
bound and checked, and is released explicitly or when the task is approved/rejected.

**Tasks 1–7 and 8a complete.** 8b (4 human-only questions) and 8c (the user test guide, needing a
real spawned agent) are open.

### The five questions, settled before any code (design.md, R1–R5)

1. **R1** — a non-blocking question does not block the task.
2. **R2** — a timed-out question leaves the task parked; **no auto-unblock**, because that hands it
   back to the divergence check while the agent still waits on the same question. Staleness surface
   deferred, deliberately.
3. **R3** — `blocked` renders as a treatment inside the In Progress column, not a ninth column.
4. **R4** — the binding lives on the **conversation**.
5. **R5** — a block names what it is waiting for; required for a hand-set one.

Plus D4 (a column on `Question`, not a join table) and D5 (the divergence check excludes on the
task's *status at the boundary*, keeping `origin` meaning "who caused this").

## Files touched

Working tree **clean**. Six commits, all **pushed** (`5d4ddbc`, `7c1ae25`, `033ec4c`, `3770a7f`,
`0116a2a`, `8288f9b`).

| path | what |
|---|---|
| `hub/hub/task_transitions.py` | `blocked` + its 4 edges; `STATUS_BLOCKED` |
| `src/agentweave/constants.py`, `hub/hub/schemas/tasks.py` | the two pinned declarations |
| `hub/hub/mcp_server.py` | `blocked` **withheld** from `TaskStatus`, with a do-not-add comment |
| `hub/hub/db/models.py` | `Task.blocked_reason`, `Question.blocked_task_id`, `Conversation.task_id` |
| `hub/hub/migrations/versions/0059_add_blocked_reason_and_question_task.py` | **new**, guarded |
| `hub/hub/migrations/versions/0060_add_conversation_task.py` | **new**, guarded, no backfill |
| `hub/hub/run_task_binding.py` | `unanswered_blocking_question`, `block_task_for_question`, `release_reason`, `release_block_for_answer`, `binding_for_conversation`, `rebind_conversation`, `release_conversations_bound_to`, `TERMINAL_FOR_BINDING`; blocked-guard in `bind_run_to_task` |
| `hub/hub/run_divergence.py` | block-before-diverge, `blocked` exclusion, `_announce_block` |
| `hub/hub/api/v1/questions.py` | release on answer; `_asking_run_has_ended`; `task_unblocked` event |
| `hub/hub/api/v1/tasks.py` | agent refused `blocked`; reason set/cleared; terminal release |
| `hub/hub/api/v1/agent_trigger.py` | inherit / rebind the conversation binding at spawn |
| `hub/hub/api/v1/agent_chat.py` | `task_id` on `ConversationResponse`; `DELETE …/conversations/{id}/task` |
| `hub/hub/schemas/tasks.py` | `blocked_reason` in/out; required-on-blocked validator |
| `hub/ui/src/components/tasks/TasksBoard.tsx` | blocked renders in In Progress, sorted first |
| `hub/ui/src/components/tasks/TaskCard.tsx` | "Waiting on you" banner, purple treatment, reason prompt |
| `hub/ui/src/components/agents/AgentOutputPanel.tsx`, `BannerStack.tsx` | binding banner, new `info` tone |
| `hub/ui/src/api/tasks.ts`, `agentChat.ts`, `client.ts` | types, `releaseConversationTask`, `deleteJson` |
| `hub/ui/src/lib/eventSummary.ts` | `task_blocked` / `task_unblocked` in words |
| `hub/tests/test_task_blocked.py` | **new**, 13 tests |
| `hub/tests/test_conversation_task_binding.py` | **new**, 12 tests |
| `hub/ui/src/__tests__/taskBlockedTreatment.test.tsx` | **new**, 9 tests |
| `hub/ui/src/__tests__/blockedStaysInProgress.test.tsx` | **new**, 4 tests |
| `hub/hub/static/ui/**` | rebuilt, `diff -rq` identical |
| `openspec/specs/{task-lifecycle-governance,run-task-binding,agent-capability-plane}/spec.md` | deltas applied |

## Key decisions

1. **`blocked` is withheld from `mcp_server.TaskStatus`** so an agent cannot express the request at
   all — stronger than refusing it. The service refuses it too, since the HTTP route is reachable
   without the tool. Both omissions asserted, so nobody "completes the list".
2. **`bind_run_to_task` will not unpark a blocked task.** `blocked → in_progress` is a legal run
   edge, so without the guard, *starting a run* would release the block and that run's end would
   record a divergence — the bug this change removes, reintroduced sideways.
3. **The divergence exclusion keys on the task's status at the boundary**, not on which run parked
   it. That is what makes multi-turn blocked work safe now that every turn is checked.
4. **`blocked → completed` is not an edge.** Work passes back through `in_progress`, so no history
   says a task completed while waiting on someone who never answered.
5. **The release-on-answer is attributed to the operator with `origin=actor`** — they answered.
   `runtime` there would additionally exempt it from the divergence check for no reason.
6. **Terminal release is `approved`/`rejected` only.** `completed`/`under_review` excluded: work
   under review comes back, and releasing there would unbind the thread about to do the revisions.
7. **The UI release is a plain function, not a mutation hook.** `AgentOutputPanel` is tested without
   a `QueryClientProvider`; a hook failed 39 tests across 7 files. Matches
   `dismissCheckpointWarning` / `withdrawQueueEntry`.

## Constraints and user directives (verbatim)

**From this session:**
- Chose **"Blocked + conversation binding"** over the permission defect, A2, and the live user test.
- Chose **"Just push the branch"** over a draft PR — so **the ci.yml question is settled**: the
  operator does not want a draft PR. Stop raising it.
- Settled R3 (treatment, not a column), R4 (conversation, not agent), R2 (leave parked).

**Carried and still binding:**
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
- **The visual-language contract rejects raw hex**, including as a `var(--x, #fallback)` default.
  `--purple` already existed in both themes.
- **A mutation hook in `AgentOutputPanel` breaks 39 tests** across 7 files that render it without a
  `QueryClientProvider`. Use a plain async function, as that file already does.
- **`test_no_code_path_deletes_conversations_outside_reset` flags `@router.delete(...)`** when the
  same line carries `response_model=ConversationResponse`. Scan now skips decorator lines.
- **The `Task` table has `created_at` and a NOT NULL `updated`**, not `created` — raw SQL inserts in
  migration tests need both.
- **The conversation routes are under `/projects/{id}/agent/{agent}/conversations/...`**, not
  `/agents/...`.
- **The `/tmp` trap from handoff 0031 is real and I hit it** — `curl -o /tmp/x` then reading it from
  native `python.exe` fails. Use a repo-relative path.
- **`session.get(RunDivergence, id)` does not work** — the primary key is `sequence`, not `id`.

**Carried and still true:**
- **`hub/data/agentweave.db` is the live database.** Check `projects` before believing otherwise.
- **Restarting the Hub: kill by exact PID and verify the new process bound.**
- **Static UI updates without a restart; Python does not.**
- **`openspec` CLI rejects change names starting with a digit**; **there is no `openspec sync`**.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. **The default `python`
  has no pytest** — use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check. **`npx tsc` fails outside
  `hub/ui`.**
- **`black` warns "Python 3.11 cannot parse code formatted for Python 3.12"** — a safety-check
  warning, not a failure.
- **`preview_snapshot` is unreliable**; **`preview_press` and `preview_resize` do not work.**

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1481 passed, 10 skipped** (1437 at this change's start).
- `pytest tests/ -q` — **372 passed, 3 skipped.**
- `npx vitest run` — **739 passed across 79 files** (726 at start). `npx tsc --noEmit` clean.
- `ruff check` clean; `black --check` — 287 files unchanged.
- `npx openspec validate --specs --strict` — **29 passed**; `--changes --strict` — **7 passed**.
- `npm run build` + `rm -rf` + copy + `diff -rq` — identical.
- **Live:** Hub restarted by exact PID (9360 → **22012**, port confirmed free between). Proved new
  **behaviourally** — `/openapi.json` publishes `blocked_reason` on `TaskUpdate`/`TaskResponse`,
  `task_id` on `ConversationResponse`, and the `DELETE …/conversations/{id}/task` route. Migrations
  `0058 → 0060` on the real database, **no backfill** (0 bound conversations, 0 blocked tasks).
- **Behavioural probe against a copy of the operator's real database** (`proj-cddb0827`, real
  conversation `conv-e7aefe3c`, agent `claude-1`): bound run → `in_progress`; run ended with an
  unanswered blocking question → task `blocked`, reason from the question text, question recorded
  the task, **zero divergences despite a `retry` policy**; turn two inherited the binding, did not
  unpark it, was not divergent; the answer released it and cleared the reason; a later run that
  dropped it **was** divergent (`div-418dbaf9`); terminal release unbound the thread. Copy deleted;
  **the operator's live board was not written to** (0 probe rows).

**Not verified, and deliberately:**
- **No agent process was ever spawned.** The six-step user test guide (`tasks.md` 8c) is untouched,
  and step 6 of the *previous* change's guide is still untouched too.
- **The Codex path is wired but never live-exercised.** Runner-agnostic by construction, since it
  sits at the Hub-owned run boundary.
- **Nobody has looked at the new card or banner visually.** Tested, not seen.
- **CI has still never run on this branch.** The operator declined a draft PR — this is now a
  settled decision, not an open question.
- **The permission defect is untouched** —
  `openspec/explorations/2026-08-10-operator-approval-not-honoured.md`.

## Git state

Branch `hub-native-experience`, HEAD **`8288f9b`**, working tree **clean**, **pushed** (`baf955a..8288f9b`),
**379 commits ahead of master**.

## Next steps

1. **The user test guide (`tasks.md` 8c)** — six steps, needs a real spawned agent in `testbed/`.
   This and the previous change's step 6 are the only things standing between these two changes and
   being archivable. **Nothing in either has ever run against a live agent.**
2. **8b's four human-only questions** — in particular 8.12: now that every turn of a bound
   conversation is checked, is the volume of stalled markers informative or noise? That is the real
   answer to the previous change's Open Question 1, which could not be judged before.
3. **The permission defect** — still the highest-value untouched item.
4. **Remaining roadmap:** A2 (shell conformance audit), B0 (blocked on the charter-count decision),
   then B2–B7.

## Open questions for the user

1. **Run the user test guide now, or move on?** Blocking archival of both changes.
2. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks archiving
   `hub-charcoal-visual-refresh` (8.11).
3. **How many charters, and which non-software domains?** Still blocks B0.
4. Carried: should `.claude/handoffs/` stay tracked (**118 files, confirmed not gitignored**); the
   two model-less runners on `proj-cddb0827` (`claude-1`, `codex-1`) will block the test guide's
   later steps; `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.

## Read on resume

- **This file's "Dead ends" first** — several cost real time, and the Hub-restart trap is still live.
- `openspec/changes/2026-08-10-blocked-and-conversation-binding/design.md` — R1–R5 and D1–D8, the
  reasoning behind everything shipped.
- `hub/hub/run_task_binding.py` — now holds all four halves: binding, waiting, the boundary
  question, and the conversation binding.
- `hub/hub/run_divergence.py` `evaluate_run_end` — the order of the checks is load-bearing.
- `openspec/changes/2026-08-10-blocked-and-conversation-binding/tasks.md` — 8b and 8c, the only
  open work.
