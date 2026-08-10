# Handoff: B1 shipped and archived — a task's status now means something

**Date:** 2026-08-10T18:50+01:00 · **Branch:** hub-native-experience · **HEAD:** `a0f9a48`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0029-2026-08-10-1538-spec-and-tabs-blended-branch-pushed.md`
**Status:** **chunk complete.** B1 archived, 47/47 tasks. Working tree clean, 0 unpushed.

## Goal

Handoff 0029 closed the spec surfaces and left the next target unnamed. The operator picked **B1 —
the task transition machine** from the roadmap's three remaining independently-shippable changes
(A2, B0, B1). Its purpose: make a task's status *mean* something, so `approved` says a real review
happened rather than that some process wrote a string into a column.

It is now implemented, verified live by the operator, and archived to
`openspec/changes/archive/2026-08-10-task-transition-machine/`.

## Current state

**Shipped and live on `:8010`.** An agent cannot skip lifecycle stages, cannot approve work its own
agent completed, and cannot walk around either rule by creating a task already `approved`. Every
accepted transition is recorded append-only, so "who completed this, and who approved it" is
answerable for the first time.

### What exists

- `hub/hub/task_transitions.py` — the declaration: 8 statuses, 18 edges, each edge naming which
  actor kinds may take it. Plus the `Actor` type and query helpers. No I/O.
- `hub/hub/task_transition_service.py` — the machine meeting a row: legality, author/reviewer
  separation, the same-status no-op, and the append-only recorder. **This is the seam B3's evidence
  checks and B4's completion gates plug into** — inside `apply_transition`, before the history row.
- `task_transitions` table (migrations `0052` + `0053`) — append-only, ordered by an autoincrement
  `sequence`, carrying `run_id` **and** `actor_agent`.
- `GET /api/v1/projects/{id}/tasks/transitions/allowed` — the operator's actor-scoped view of the
  map, fetched once per session.
- A status menu on `TaskCard`, built on the existing `RowMenu`, offering only operator-legal moves.

### The two defects found *during* the work, both mine, both fixed

1. **The history did not read back in the order it happened.** Transitions staged in one flush share
   a `created_at` to the microsecond and the tiebreak was a *random* `ttr-` id. Fixed with an
   autoincrement `sequence` PK, the shape `InboundQueueEntry` already uses.
2. **Author/reviewer separation compared `run_id` and therefore forbade nothing.** The operator's
   agent completed `task-4c9b26e7` on `run-1ecc4ec7` and approved it on `run-6d704bb8`. **Every turn
   is a new run**, so "a different run must approve" is satisfied by an agent simply continuing. I
   had recorded this as an accepted limitation and called it "collusion across runs" — filing a
   main-path failure as an edge case. Fixed to compare **agent identity** (`actor_agent`, migration
   `0053`).

## Files touched

Working tree is clean; everything below is committed and pushed across six commits
(`1778342`, `0ce1ed1`, `07a7a62`, `1b24ea5`, `bcaa7a3`, `9160cb4`, `20d6be3`, `a0f9a48`).

| path | what | done? |
|---|---|---|
| `hub/hub/task_transitions.py` | **new.** The map, `Actor`, `allowed_targets`, `allowed_map_for`, `refusal_detail`, `ENTRY_STATUSES` | yes |
| `hub/hub/task_transition_service.py` | **new.** `apply_transition`, `guard_entry_status`, `history_for`, the four `*Error` types | yes |
| `hub/hub/migrations/versions/0052_add_task_transitions.py` | **new.** Creates the table, guarded on `tasks` **and** `projects` | yes |
| `hub/hub/migrations/versions/0053_add_task_transition_agent.py` | **new.** Adds `actor_agent` | yes |
| `hub/hub/db/models.py` | `TaskTransition` model | yes |
| `hub/hub/api/v1/tasks.py` | `update_task_for_actor` takes an explicit `Actor`; `guard_entry_status` on create; the `transitions/allowed` route | yes |
| `hub/hub/api/v1/agent_actions.py` | passes `run_actor(run_id, agent)`; `AgentTaskCreate.status` narrowed to entry statuses | yes |
| `hub/hub/schemas/tasks.py` | `TaskCreate.status` narrowed to `_ENTRY_STATUSES` | yes |
| `hub/hub/main.py` | one app-level `TransitionRefusedError` handler → 409/403 | yes |
| `hub/tests/test_task_transitions.py` | **new.** 56 tests — the declaration + the append-only source scan + the MCP agreement test | yes |
| `hub/tests/test_task_transition_service.py` | **new.** 27 tests — what only a database can answer | yes |
| `hub/tests/test_task_transitions_api.py` | **new.** 20 tests — both routes, both transports, refusal shape, SSE | yes |
| `hub/tests/test_migrations.py` | head → `0053`; three `0052` tests; `_create_all_at` helper | yes |
| `hub/tests/test_project_persistence.py` | head assertion → `0053` | yes |
| `hub/ui/src/api/tasks.ts` | `useAllowedTransitions` hook | yes |
| `hub/ui/src/components/tasks/TaskCard.tsx` | status menu + refusal display via `readableApiError` | yes |
| `hub/ui/src/components/tasks/TasksBoard.tsx` | sticky column headers; removed the blocking `overflow-hidden` and the nested `overflow-y-auto` | yes |
| `hub/ui/src/__tests__/taskStatusControl.test.tsx` | **new.** 13 tests | yes |
| `hub/ui/src/__tests__/agentColorSurfaces.test.tsx` | wrapped `TaskCard` in a `QueryClientProvider` (fair fallout) | yes |
| `hub/hub/static/ui/**` | rebuilt artefact | yes |
| `openspec/specs/task-lifecycle-governance/spec.md` | **new capability**, 7 requirements | yes |
| `openspec/specs/agent-capability-plane/spec.md` | run-attribution requirement strengthened for task status | yes |
| `openspec/explorations/2026-08-10-enforcing-the-development-cycle.md` | **new.** validity vs liveness; the four enforcement tiers; the hook rule | yes |
| `openspec/explorations/2026-08-10-operator-approval-not-honoured.md` | **new.** the permission defect, recorded not fixed | yes |
| `openspec/changes/archive/2026-08-10-task-transition-machine/` | archived: proposal, design (D1–D15), tasks (47/47), delta specs | yes |

## Key decisions

Full rationale lives in the archived `design.md` (D1–D15). The ones that will otherwise be
re-litigated:

1. **D2 — the actor is explicit, not inferred from a null run id.** `Actor` refuses a run without an
   agent *and* an operator carrying one. That second check makes the privilege escalation
   unstateable rather than merely unlikely. Rejected: keep inferring — the failure mode is a silent
   privilege escalation.
2. **D9 — the operator gets *more edges*, not an exemption.** Early rejection and reopening are
   operator-only *edges*, so the operator is still bound by the map and every recorded history
   describes a legal sequence. Rejected: a forced-move override — with the edges, it is unnecessary,
   and every B3/B4 gate would have had to account for a bypass path.
3. **D10 — creation is restricted to `pending`/`assigned`.** Found by a scan: `AgentTaskCreate.status`
   accepted any of the eight, so a task could be born `approved`. Also levelled HTTP with MCP by
   **narrowing HTTP**, not widening MCP — widening would have propagated the hole.
4. **D13 — one actor-scoped map endpoint.** Rejected: `allowed_transitions` on the task response (a
   resource that varies by asker breaks every cache, React Query's key included) and a per-task
   endpoint (forty cards, forty identical answers).
5. **D14 — author/reviewer separation compares agents.** `actor_agent` is denormalised rather than
   joined through `runs`: an integrity record must answer "who approved this" without depending on a
   run row that may be pruned.
6. **D15 — `completed → under_review` stays, question still open.** Operator: *"too early to say"*.
   The state holds nothing yet, so it would read as a formality whatever it turns out to be for.
   Revisit when B3 gives it content. Both rejected alternatives are written down in D15.
7. **No backfill anywhere (D8, and 0053).** Pre-existing rows keep `actor_agent` NULL and NULL is
   treated as "not the same agent", so old tasks stay approvable. Inventing an agent would put a
   guess in the one record whose value is that everything in it happened.

## Constraints and user directives (verbatim)

**From this session:**
- *"Do not call the AgentTool unless the user requested it"* / *"Do not use workflows or
  deep-research unless the user requested it"* — from the session environment. Honoured throughout.
- *"Continue until done"* — the mandate under which sections 2–8 were built.
- *"When the permissions are not to allow all and a agent needs to delete or execute something even
  if he asks via agentweave and we give a positive answer it still doesn't allow it to run. This is
  a hard bug that we need to revisit later."*
- *"the header of the table is not fixed. When I scroll down I lose what each column means."*
- *"Should we keep the kanban view? … Thinking that each task will mostly relate to the spec should
  we change how we view this page?"* — answered: wait for B3, the link does not exist yet.
- *"Why each turn is a run? Seems like a bad pattern?"* — answered: it is one process execution;
  `pid` + `last_heartbeat_at` drive crash recovery and the run token is per-spawn authority.
  **The pattern is sound; using it as an actor identity was the error.**
- 9.6 answered **"too early to say"**; 9.4 answered **"Now I did"**.

**Carried and still binding:**
- **Handoff cadence:** only when asked, or when an openspec change is done. This one was asked for.
- **STANDING DIRECTIVE:** every change's `tasks.md` splits agent-verifiable from human-only and
  emits a user test guide. B1's section 9 was written that way and it worked — five of the six were
  later corroborated against the transition history rather than taken on report.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and wall-clock.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"first I think we have to many we need to cut some of those"* (the 21 charters); *"the charter
  exists to give instructions so I can use agentweave for more then developing."*
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task
  complete on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **`hub/data/agentweave.db` is the live database, not `~/.agentweave/hub/data/agentweave.db`.**
  `settings.database_url` defaults to `sqlite+aiosqlite:///data/agentweave.db` — **relative to the
  working directory**. The Hub runs from `hub/`. I ran a migration check against the wrong database
  and reported it as "your real data"; it held a different project. **Check `projects` before
  believing a database is the one in use.**
- **Restarting the Hub: kill by exact PID, and verify the new process bound.** A PowerShell PID
  lookup returned several ids, the wrong one was killed, and the new instance ran migrations and
  then *failed to bind* because the old process still held 8010. Result: `0053` applied while the
  serving code stayed stale, and my own verification returned a false pass. The tell was
  `actor_agent` NULL in rows written after the "restart". **Confirm with a behavioural probe, not
  an HTTP 200.**
- **Static UI updates without a restart; Python does not.** `hub/hub/static/ui` is read from disk
  per request. A stale process therefore serves the *new* UI against the *old* API — which looked
  like "the status menu is missing" when the menu was correctly rendering nothing against a 404.
- **`position: sticky` dies under an ancestor with `overflow-hidden`** — that ancestor becomes the
  scrollport, so the element pins to a box that never scrolls. A nested `overflow-y-auto` does the
  same. Measured 172 → −128 before the fix, 160 → 160 after.
- **`openspec` CLI rejects change names starting with a digit.** `openspec new change` and
  `openspec status --change` both refuse `2026-08-10-...`. Create with a letter-initial name, then
  `git mv` to the repo's date convention. `openspec validate --changes --strict` works regardless.
- **There is no `openspec sync` command** — the skill applies deltas by hand.
- **`openspec … --json` prints a warning line before the JSON** (`Unknown artifact ID in rules:
  "spec"`). Strip with `sed -n '/^{/,$p'` before parsing.
- **ruff N818** requires exception names to end in `Error` (matching `HubAPIError`,
  `TriggerAgentError`). **The raw-hex UI contract scans comments too** — describing a colour as
  `#ffffff` in a comment fails it.
- **A blunt source assertion matches your own prose:** `not.toMatch(/background/)` failed against the
  comment explaining the removal. Scope to `style=\{\{[^}]*background`.

**Carried and still true:**
- **PowerShell here-strings (`@'…'@`) mangle a commit message in the Bash tool.** Write the message
  with the Write tool and `git commit -F`.
- **`cp -r dist/* static/ui/` merges rather than replaces** — `rm -rf` the destination first or
  stale hashed assets survive and `diff -rq` fails.
- **`cd hub/ui` first** — `npx vitest` from the repo root resolves a different project.
- **`npm run lint` does not work**; `tsc --noEmit` is the check.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. **The default `python`
  has no pytest** — use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`preview_snapshot` is unreliable**; `preview_evaluate` answers nearly everything.
  **`preview_press` and `preview_resize` do not work.**

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1384 passed, 10 skipped** (1280 at the start of this session).
- `pytest tests/ -q` — **372 passed, 3 skipped.**
- `npx vitest run` — **716 passed across 76 files.**
- `npx tsc --noEmit` — clean. `ruff check hub/hub/ hub/tests/` — clean. `black` — applied.
- `npx openspec validate --specs --strict` — **28 passed**; `--changes --strict` — **6 passed**.
- `npm run build` + `rm -rf` + copy + `diff -rq` — identical.
- **Live against `proj-cddb0827` after restarting the Hub:** an illegal operator move returns 409
  naming the reachable set; the same agent on a *new run* is refused **403** with *"Starting a new
  run does not make you a different actor"*; a different agent is accepted 200.
- **Live sticky header:** pinned at 160px through scroll positions 200 and 500.
- **Operator's own testing**, corroborated against `task_transitions` rather than taken on report —
  9.1 (`task-5da91c5a`: agent stops at `under_review`, the approval row is the operator's),
  9.2 (`task-25d8cfd0`: five operator transitions in 13s), 9.3, 9.4 (`in_progress → rejected`,
  operator), 9.5 (`task-393eaee3`: `approved → revision_needed` plus three later moves, nothing
  removed).

**Not verified, and deliberately:**
- **CI has still never run on this branch** — now **360 commits ahead of master**. `ci.yml` triggers
  only on push/PR to `master`, so pushing this branch runs nothing. Everything above is Windows, one
  Python, one browser. A **draft PR to master** would trigger the 3-OS × 5-Python matrix with no
  workflow edit. Deferred by the operator; now raised **eight times**.
- **The permission defect is not fixed and not investigated beyond a first-pass elimination.**
- **Nobody has looked at the task board visually since the sticky-header fix** — it is measured, not
  seen.
- The four human-only items still blocking `hub-charcoal-visual-refresh` (8.8, 8.10, 8.11) and
  `hub-contextual-navigation` (7.7).

## Git state

Branch `hub-native-experience`, HEAD **`a0f9a48`**, working tree **clean**, **0 unpushed**,
**360 commits ahead of master**.

## Next steps

1. **Ask the operator what to work on next.** B1 is closed and no successor was named. Do not pick
   one — the candidates below are unequal in kind and the choice is theirs.
2. **The permission defect** — `openspec/explorations/2026-08-10-operator-approval-not-honoured.md`.
   Reproduce in `testbed/` with the composer's Permissions pill on **"Ask me"**, ask an agent to
   delete a file, answer **yes**, and capture: which runner, the run's `AW_PERMISSION_POSTURE` and
   `AW_DECISION_TIMEOUT`, the `_report_decision` output, and what the agent's transcript received.
   The `approve_tool_call` return-annotation trap is already ruled out; four leads are listed.
   **This is the highest-value open item** — while it is broken the only working postures are
   allow-everything and block-everything.
3. **The run→task binding** (`openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`)
   — B1 gives *validity*, not *liveness*. It is also B3's prerequisite: evidence is produced *by a
   run* about *a task*, and that edge does not exist.
4. **Remaining roadmap changes:** A2 (shell conformance audit), B0 (aw-spec charter honesty repair,
   blocked on the charter-count decision), then B2–B7.
5. **Clear the older debt:** the four human-only checks on the two visual changes.

## Open questions for the user

1. **What is the next target?** Blocking next-step 1.
2. **The `ci.yml` branch trigger** — deferred again; **raised eight times**. A draft PR is the
   zero-edit alternative.
3. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks archiving
   `hub-charcoal-visual-refresh` (8.11).
4. **How many charters, and which non-software domains?** Still blocks B0.
5. **The kanban board's future.** Answered "wait for B3", but two cheap improvements were offered
   and not taken: collapse/hide empty columns, and move `rejected` fully out of the main grid.
   Worth recording against B5 if wanted.
6. Carried: should `.claude/handoffs/` stay tracked (**now 118 files, not gitignored**); the two
   model-less runners on `proj-cddb0827`; `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.

## Read on resume

- **This file's "Dead ends" section first** — the database-identity and Hub-restart traps both
  produced false verifications this session, and both will recur.
- `openspec/changes/archive/2026-08-10-task-transition-machine/design.md` — D1–D15, the reasoning
  behind everything shipped, including the two corrections recorded rather than rewritten.
- `hub/hub/task_transitions.py` and `hub/hub/task_transition_service.py` — the machine, and the seam
  B3/B4 plug into.
- `openspec/explorations/2026-08-10-enforcing-the-development-cycle.md` — validity vs liveness, the
  four enforcement tiers, and the "no capability may exist only in a hook" rule.
- `openspec/explorations/2026-08-10-operator-approval-not-honoured.md` — the open defect and what is
  already ruled out.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — the A/B sequence
  and what remains after B1.
