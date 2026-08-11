# Handoff: the approval defect fixed end to end, and six changes archived

**Date:** 2026-08-11T16:35+01:00 · **Branch:** hub-native-experience · **HEAD:** `2b2c3b7`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0034-2026-08-11-1423-decisions-settled-and-approval-defect-diagnosed.md`
**Status:** **chunk complete.** Working tree clean, 0 unpushed. One change implemented, verified
live by the operator, extended on their feedback, and archived. Five more archived. The board went
from **10 active changes to 4**.

## Goal

Handoff 0034 left the permission-approval defect diagnosed but unfixed. The operator chose it over
B0. This session implemented it, had the operator verify it live, acted on the one defect they
found, and then cleared the archive backlog that their verification unblocked.

The *why* that matters for judgement calls: the defect's cost was never "a card lingers". It was
that **clicking Allow returned `200 allowed` and nothing ran** — a false record that the operator
authorised an action that never happened, and for a permission that record *is* the audit trail.
Every design decision below follows from treating a wrong audit record as worse than a lost one.

## Current state

**Nothing is half-done.** Seven commits, all pushed, working tree clean.

### 1. `2026-08-11-permission-request-expiry` — SHIPPED, VERIFIED LIVE, ARCHIVED

The root cause from handoff 0034 was correct and is now fixed. **Two mechanisms, per design D1:**

- **The run reports.** `mcp_server._report_wait_ended` calls a new agent-facing route on the timeout
  path, best-effort on exactly `_report_decision`'s terms — every failure swallowed, no exception,
  no delay to the decision. This makes closure *prompt*.
- **The run's end sweeps.** `permission_requests.expire_pending_for_run(db, run_id)`, one
  `UPDATE ... WHERE status='pending'`, called from every run-end site inside the transaction that
  already sets `run.status`/`ended_at`. This makes closure *certain*.

Both guard on `status == "pending"`, so whichever lands second matches no rows.

**Task 3.3 ("check the assumption") was the highest-value task in the change. The design named two
run-end sites; there are FIVE:**

| site | what it is |
|---|---|
| `agent_trigger.py:1270` | PTY run end (named in design) |
| `agent_trigger.py:1656` | Codex appserver run end (named in design) |
| `agent_trigger.py:1086` | PTY spawn failure (`FileNotFoundError`) — nothing asked, swept anyway |
| `agent_trigger.py:1600` | Codex spawn failure — as above |
| **`run_reconciliation.py:43`** | **Hub restart orphan sweep — the worst case there is** |

The reconciliation site matters most: a Hub bounced while a card is on screen left a row whose run
no longer existed in *any* process, so the card outlived not just its run but the Hub that served
it — permanently, across every later restart. That path also uses a **sixth terminal status,
`"interrupted"`**, which a grep for completed/failed/stopped never finds. `scheduler.py:401` was
examined and **excluded** — it is a `JobRun`, not a `Run`.

**Expiry leaves `decided_at` NULL.** `db/models.py` says `decided_at` distinguishes an answer from
a timeout, which is only true if a timeout does not set it. The invariant is now
`decided_at is not None` ⟺ a human answered.

**The 409 guard needed no code change.** It was always correct; nothing ever reached it.

**One change beyond the tasks:** the poll loop used to report an expired request to the agent as
*"the operator refused this action"*. Nothing could expire a Claude row before, so that branch was
unreachable; the sweep makes it reachable, and it would have invented a refuser. Now reads *"this
request is no longer open, so it was not approved"*.

### 2. Dismissing an expired card — OPERATOR-FOUND, SHIPPED

The operator ran the §8 human checks and reported: *"the card saying that the agent was refused
doesn't have a dismiss button. It stays there forever. It should pile up but the user should be
able to dismiss it."*

The design's answer to clutter (D4) was that accumulation is a signal worth seeing. That is right
and incomplete: **a signal with no way to acknowledge it becomes wallpaper.**

- `PermissionRequest.dismissed` / `dismissed_at`, **beside `status`, not a new status value.**
  `status` is the run-facing fact; a `"dismissed"` status would read as a decision to every reader
  of that column, including the run's own poll loop. Same reasoning `questions.declined` sits
  beside `answered`.
- **Migration `0062`**, guarded like 0038–0061, NOT NULL + server default (SQLite rewrites the
  table). **No backfill** — expired rows predating it stay visible.
- `POST /projects/{id}/permission-requests/{rid}/dismiss`, idempotent, and **refuses a pending
  request with 409**: clearing a live card would deny it by neglect while the run still waits.
- The `×` reuses `AgentQuestionCard`'s decline control — same position, same `Icon name="x"`, same
  `--text-3`.

### 3. Six changes archived; the board is now 4 active

The operator confirmed that verification groups **A (reduced motion), B (keyboard), C (layout and
feel)** were already run in earlier sessions and passed. Those were recorded **as their
attestation, not as fresh runs** — that distinction is written into each task, because the agent
provably cannot force `prefers-reduced-motion` or drive real focus traversal.

Archived: `permission-request-expiry`, `hub-charcoal-visual-refresh`, `hub-contextual-navigation`,
`conversation-first-spec-workspace`, `one-chat-surface`, `run-task-binding`.

**Remaining active changes — 4:**

| change | open | needs |
|---|---|---|
| `2026-07-30-hub-native-experience` | 69 | the long-running umbrella change |
| `2026-08-11-charter-set-reshape` (B0) | 33 | **agent work — fully specced, no unknowns** |
| `2026-08-10-blocked-and-conversation-binding` | 4 | operator, over a day's real use |
| `2026-08-11-declining-a-question` | 2 | operator, same |

`openspec/specs/` is now **31 capabilities** (was 29); `openspec/changes/archive/` holds **57**.

## Files touched

Working tree **clean**, **0 unpushed**. Seven commits: `4dc606c`, `cb23ebb`, `cb3452b`, `685ceeb`,
`28a0930`, `cd76fd0`, `9754dcd`, `2b2c3b7`.

| path | what | done? |
|---|---|---|
| `hub/hub/permission_requests.py` | **new** — `expire_pending_for_run`, the one sweep helper | yes |
| `hub/hub/mcp_server.py` | `_report_wait_ended`; expired no longer reported as an operator refusal | yes |
| `hub/hub/run_reconciliation.py` | sweep at the restart-orphan site (the fifth run-end site) | yes |
| `hub/hub/api/v1/agent_actions.py` | `POST /permission-requests/{id}/expire`, run-scoped | yes |
| `hub/hub/api/v1/agent_trigger.py` | sweep at 4 run-end sites + import | yes |
| `hub/hub/api/v1/permissions.py` | `include_expired` flag; `dismiss` route; `dismissed` on schema | yes |
| `hub/hub/db/models.py` | `PermissionRequest.dismissed` / `dismissed_at` | yes |
| `hub/hub/migrations/versions/0062_add_permission_request_dismissed.py` | **new**, guarded | yes |
| `hub/tests/test_permission_request_lifecycle.py` | **new**, 12 tests, route-level both sides | yes |
| `hub/tests/test_permission_approver.py` | +3 tests (write-back attempted; unreachable Hub; no invented refuser) | yes |
| `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py` | head assertions 0061 → **0062** (9 + 1 sites) | yes |
| `hub/ui/src/api/permissions.ts` | `dismissed` field; `include_expired=true`; `useDismissPermissionRequest` | yes |
| `hub/ui/src/components/agents/PermissionRequestCard.tsx` | expired card, dismiss `×`, 409 surfaced | yes |
| `hub/ui/src/__tests__/permissionRequestCard.test.tsx` | 10 → **18** tests | yes |
| `hub/ui/src/__tests__/specChatSurface.test.tsx` | 2 fixtures gained `dismissed: false` | yes |
| 7 × `hub/ui/src/__tests__/*.test.tsx` | **mock repair** — see Dead ends | yes |
| `hub/hub/static/ui/**` | rebuilt twice, `diff -rq` identical both times | yes |
| `openspec/specs/agent-run-sandboxing/spec.md` | +4 requirements (expiry, refusal, visibility, dismissal) | yes |
| `openspec/specs/agent-conversation-workspace/spec.md` | 36 → 43 requirements | yes |
| `openspec/specs/hub-workspace-shell/spec.md` | 8 → 18 requirements | yes |
| `openspec/specs/agent-stream-events/spec.md` | 17 → 19 requirements | yes |
| `openspec/specs/hub-interaction-feedback/spec.md` | **new capability**, 6 requirements | yes |
| `openspec/specs/project-environment-settings/spec.md` | **new capability**, 5 requirements | yes |
| `openspec/changes/archive/` | 6 changes moved in | yes |
| `testbed/scratch/expiry_db_probe.py`, `sync_delta.py` | probe + sync helper — **gitignored**, intentionally uncommitted | kept |

## Key decisions

1. **Two mechanisms, not one (D1).** Reporting alone is best-effort by design and a killed run
   never reports; sweeping alone leaves the card up for the rest of a long turn. *Rejected: a
   periodic age-based reaper* — age is the wrong predicate; staleness is "nobody is waiting".
2. **Expiry is STORED though `declining-a-question` deliberately DERIVED `asker_waiting`.**
   `asker_waiting` is a live fact used for sorting; expiry is a terminal event that becomes true
   once. Recorded because a later reader will otherwise see an inconsistency.
3. **A stale approval is REFUSED where a stale question is merely marked (D3).** A stale question
   wastes attention; a stale approval writes a false record of authority.
4. **`decided_at` stays NULL on expiry**, so `decided_at is not None` means exactly "a human
   answered". Stated because the alternative (stamping it) also "works" and quietly destroys the
   only signal that separates an answer from a timeout.
5. **`dismissed` is a separate column, not a `status` value.** Folding it in would make tidying a
   card look like a decision to every reader of `status`, including the run's poll.
6. **Dismissing a *pending* request is refused (409).** Clearing a live card would deny it by
   neglect. *This is a judgement call the operator has not overruled but was told about.*
7. **`include_expired` is a second flag, not "drop the filter".** The query is capped at 100
   newest-first, so answered history would push live requests off the end.
8. **The operator's A/B/C verification is recorded as attestation, not as a fresh run.** Honest
   provenance matters more than a tidy checkbox.
9. **`run-task-binding` 8.15/8.16 closed as superseded, 6.6 closed as a recorded decision** — all
   three already carried written rationales; leaving them open misrepresented them as owed work.
10. **`spec-chat-session` deliberately NOT synced.** See Dead ends — the main spec is ahead of both
    deltas.

## Constraints and user directives (verbatim)

**From this session:**
- *"The permission defect"* → chosen over B0 as the work item.
- *"It works, tested."* — the operator ran the full §9 user test guide live and it passed,
  including a real Claude timing out against a real Hub and a Stop mid-wait.
- *"Just one thing that is annoying when you deny or stop. The card saying that the agent was
  refused doesn't have a dismiss button. It stays there forever. It should pile up but the user
  should be able to dismiss it."*
- *"Not deny but run out of time"* — clarifying the above refers to the **expired/timed-out** card.
- *"What are all the tasks needed from me because I think most of them I already did in previous
  runs"* — read as wanting a complete, precise inventory, not a summary.
- Settled by selection: **A, B and C already done**; **8.15/8.16 closed as superseded**.

**Carried and still binding:**
- **The `ci.yml` question is settled** — the operator chose "just push the branch", not a draft PR.
  **Do not raise it again.**
- **Handoff cadence:** only when asked, or when an openspec change is done.
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and wall-clock. Twice asked
  plainly *"what's next?"*, wanting a short prioritised answer and forward motion, **not** another
  question modal.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task
  complete on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session — the two that cost real time:**

- **A regex that silently deleted a requirement.** In the spec-sync helper,
  `re.search(r"^## ", text[start+1:end], re.M)` — slicing one character off `### ` leaves `## `,
  and `^` matches at **string start** under `re.M`. Every requirement block collapsed to a single
  `#`. It was caught only because the *next* change tried to modify the deleted requirement and
  failed loudly. **Fix: search from the end of the heading line, and gate the whole tool behind a
  byte-exact round-trip over all 31 specs before it may write anything.**
- **I read a unified diff backwards and regressed a spec.** In `difflib.unified_diff(a, b)`, `-`
  lines are in **a**, `+` in **b**. I concluded the delta was newer than the main spec, applied it,
  and **deleted 528 characters** of shipped, operator-verified behaviour (the pane-divider clause
  the operator had verified in group C). Reverted with `git checkout --`. **Then checked
  `spec-chat-session` requirement-by-requirement against `git show HEAD`: the main spec is ahead of
  BOTH deltas on every requirement.** It is now skipped by name with the evidence recorded.
- **Seven UI test files mock `@/api/permissions` WITHOUT `importOriginal`**, so adding a single
  export (`useDismissPermissionRequest`) broke **39 tests across 7 files**. This is the same trap
  already documented for `@/api/questions`; it is now true of this module too. The files:
  `agentHandoff`, `agentRunningComposer`, `batchedQuestionComposer`, `composerPermissionDefault`,
  `conversationControls`, `conversationDestination`, `handoffPlacement`.
- **A new field on `PermissionRequest` breaks TS fixtures** in `permissionRequestCard.test.tsx` and
  `specChatSurface.test.tsx` (2 places) — `tsc --noEmit` catches it, `vitest` alone does not.
- **`git checkout -- openspec/specs` does NOT reset newly created untracked capability dirs.** They
  survived a "clean slate" reset and made a later run report "already added" for work done moments
  earlier. Delete them explicitly.
- **`black --check` flags four files this session never touched** —
  `test_accounting_budget.py`, `test_task_transitions.py`, `test_project_workspace_unavailable.py`,
  `test_agent_trigger.py`. Pre-existing drift. **Left alone deliberately.**

**Carried and still true:**
- **A background shell started with the Bash tool dies at session teardown.** Start the Hub via WMI:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
  Log at `%TEMP%\agentweave-hub.log`, **not** in the repo. Find the real PID with
  `Get-NetTCPConnection -LocalPort 8010 -State Listen` — `Invoke-CimMethod` returns the `cmd.exe`
  wrapper's PID, not python's.
- **The Bash tool's cwd persists across calls.** Bit again twice this session (a `cat >>` and an
  `npm run build` both ran from `hub/ui`). Use absolute paths or re-`cd`.
- **`openspec` CLI rejects change names starting with a digit** — `openspec status --change
  2026-...` fails with *"Change name must start with a letter"*. Every change here is digit-initial,
  so the archive skill's status step cannot be used; do the checks by hand.
- **Nine UI test files mock `@/api/questions` explicitly** — any new export there breaks 52 tests.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. Default `python` has no
  pytest; use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check. **`npx tsc`/`npx vitest` fail
  outside `hub/ui`.**
- **`hub/data/agentweave.db` is the live database.** Project `proj-cddb0827`, named **Testbed**.
- **`preview_snapshot` is unreliable**; **`preview_press` and `preview_resize` do not work.**
- **`openspec validate --strict` only inspects a requirement's OPENING LINE for SHALL/MUST.**

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1514 passed, 10 skipped** (1500 baseline + 14 added here).
- `pytest tests/ -q` — **372 passed, 3 skipped**, exactly the baseline; no CLI code touched.
- `npx vitest run` — **767 passed across 80 files** (759 baseline + 8). `npx tsc --noEmit` clean.
- `ruff check hub/ src/` — all checks passed. `black --check` clean on every file touched here.
- `npx openspec validate --specs --strict` — **31 passed**; `--changes --strict` — **4 passed**.
- **Negative control on the reconciliation sweep:** removing that one line fails
  `test_a_request_does_not_survive_the_run_that_raised_it` with `assert 'pending' != 'pending'`.
- **Pre-fix defect reproduced at the route level** by a throwaway probe (written, run, deleted):
  with the run ended, the request was `STILL_LISTED: True` and `POST .../decide` returned
  **`200 allowed`**.
- **Probe against a COPY of the live database** (`testbed/scratch/expiry_db_probe.py`) —
  **22/22 checks**, both closing routes, including that **migration 0062 actually applies to the
  real board's schema** (`head=0062`, both columns present). Live board verified untouched
  afterwards; copy deleted explicitly (the async engine held the file, so `rmtree` failed silently
  the first time).
- **Live Claude probe** (`testbed/scratch/run_probe.sh`) at 0s and 65s — both still **allow** and
  write `hello.txt` (11s / 78s, against 10s / 72s pre-change). No regression.
- **Hub restarted twice by exact PID.** `/openapi.json` went 5 → 6 → **7** permission routes.
  Live DB migrated **0061 → 0062**; the operator's own 2 expired rows survive and are clearable.
- **Spec-sync round-trip gate:** all 31 main specs parse and reassemble **byte-identically**.
- **Post-sync audit:** every ADDED/MODIFIED requirement from all 5 archived changes is present and
  every REMOVED one absent — **0 missing**. No `### Requirement:` heading was deleted; counts only
  grew (36→43, 17→19, 8→18).
- **The operator ran the full §9 user test guide live and reported "It works, tested."**

**NOT run, and deliberately:**
- **No agent process has been spawned against `blocked-and-conversation-binding` or
  `declining-a-question`.** Their remaining 6 tasks need a day of real use, not a sitting.
- **B0 (`charter-set-reshape`) is a proposal only — zero implementation.** Unchanged from 0034.
- **`2026-07-30-hub-native-experience` (69 open) was not touched or assessed** this session.
- **The dismiss `×` has not been clicked by a human.** Backend, component and DB-copy probe all
  pass; the operator has not yet seen it on screen.
- **`black` was not run over the four pre-existing drift files** listed in Dead ends.

## Git state

Branch `hub-native-experience`, HEAD **`2b2c3b7`**, working tree **clean**, **0 unpushed**
(`origin/hub-native-experience` is at HEAD).

Hub running as PID **11764** on `:8010` (python; started 16:06), serving the 0062 schema.

## Next steps

1. **Implement `openspec/changes/2026-08-11-charter-set-reshape`, starting with task 1.1.** Read
   `design.md` D1–D8 first. The change re-shapes 21 seeded charters to 9 — keep 6 accountabilities
   (`tech_lead` absorbing `architect`, `code_reviewer`, `verifier` absorbing `qa_engineer`,
   `guardian`, `security_engineer`, `spec`), add `developer` (replacing the six `*_dev`/`*_engineer`
   variants, `technical_writer` folded in), add `underwriter` + `underwriting_approver`, remove 15.
   Removed activity charters are **parked** under
   `openspec/changes/2026-08-11-charter-set-reshape/parked-phase-guidance/` — **to be created; it
   does not exist yet** — rather than deleted (D4).
   Existing projects' charter rows are **left entirely alone** (D8).
   The verified defect: **16 of 21 seeded charters escalate to a "Tech Lead" that exists only if
   the operator made one**, which `openspec/specs/agent-charter/spec.md:83` already forbids;
   `hub/tests/test_agent_facing_text.py` enforces only a fixed `REMOVED_SUBSYSTEMS` needle list and
   has **nothing for the participant clause**.
2. **Or clear the last 6 operator tasks** — `blocked` 8.10–8.13 and `declining` 6.8–6.9 — which
   needs a day of real use and would archive two more changes.
3. **Assess `2026-07-30-hub-native-experience` (69 open).** It has not been looked at in several
   sessions and may contain work already done elsewhere, as five changes did this session.
4. **Remaining roadmap:** A2 (shell conformance audit), then B2–B7.

## Open questions for the user

1. **Should dismissing a *pending* permission request be allowed?** Currently refused with a 409,
   on the reasoning that clearing a live card denies it by neglect while the run waits. The
   operator was told and has not objected, but has not confirmed either.
2. Carried: should `.claude/handoffs/` stay tracked (**121 files, confirmed not gitignored**);
   `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.
3. **Resolved this session, do not re-ask:** which proposal to implement first; whether A/B/C were
   already done; whether to close `run-task-binding` 8.15/8.16.

## Read on resume

- **This file's "Dead ends" first** — the `^## ` regex trap and the backwards-diff regression both
  cost real time and both damaged files before being caught.
- `openspec/changes/2026-08-11-charter-set-reshape/design.md` — D1–D8, and `tasks.md` §1, which is
  next-step 1.
- `openspec/specs/agent-charter/spec.md` — particularly line 83, the participant clause that the
  16 defective charters violate.
- `hub/tests/test_agent_facing_text.py` — the test that should have caught it and did not; B0 has
  to close that gap, not just fix the text.
- `hub/hub/permission_requests.py` and `hub/hub/api/v1/permissions.py` — the shape this session
  settled on, if anything permission-related comes up again.
- `testbed/scratch/sync_delta.py` — **gitignored but reusable.** The next archive needs it; it now
  carries the round-trip gate and the `spec-chat-session` skip with its evidence.
