# Loop 7 — agents drive the evidence loop, but a skipped merge is terminal

**Date:** 2026-08-14 · **Project:** `aw-loop7` (`proj-e6c1de74`, `C:\Users\huida\Documents\aw-loop7`)
**Scope, set by the operator before anything was read:** phase 9.1 of
`openspec/changes/2026-08-14-the-loop-agents-can-drive` — re-run the loop from zero, pass condition
= an agent-driven project reaches `integration: integrated` with **no minted run credential and no
curl-as-agent**, against a task carrying requirement links.

**Verdict: the pass condition was met.** All 9 requirements read `verified / integrated`;
`b38e4646 → master` merged; the code is on `master` and its tests pass from a clean checkout. Every
evidence action — record, list, decide — went through the agents' own MCP tools. Last session this
was impossible and finishing the run took a hand-minted credential and a `curl`.

**But it did not run clean.** Three defects cost the run six extra agent runs and three operator
interventions that are not part of any intended flow. None of them is in the change under test;
all three sit between it and something older.

Two runners were used: a Claude builder, and Codex for the architect and verifier.

---

## Findings, ranked by what each cost

### 1. Evidence recorded during a turn is footprinted against the *previous* commit

An agent calls `record_evidence` while its turn is running. The commit containing that agent's work
is created by `snapshot_worktree` **after** the turn ends. So the footprint names whatever the
branch pointed at when the turn started — never the work being attested to.

The builder recorded 9 pieces of evidence. All nine were footprinted at `d6f6ff78`, the `init`
commit, which contains only `README.md`. The work was in `b38e4646`, which did not exist yet.

```
ev-82beff1b rejected  builder  commit=d6f6ff78 branch=agentweave/builder reachable_from_main=True
ev-5ce570f1 awaiting  builder  commit=b38e4646 branch=agentweave/builder reachable_from_main=False
```

The verifier caught it, unprompted and correctly:

> The first consistency check found a serious discrepancy: the evidence names implementation and
> test files at commit `d6f6ff7`, but this checkout at that same commit currently contains only
> `README.md`.

**Cost:** a full reject → re-record → re-review cycle. Three extra agent runs, all unattended.

**Why this is worse than a nuisance.** The stale footprint carried
`reachable_from_main=True` — because the init commit *is* `master`. Evidence pointing at code that
does not exist therefore reads as *already shipped*. A verifier less strict than this one would
have accepted nine rows that integration would then treat as already integrated, and the loop would
report success having merged nothing. That is precisely the failure mode
`2026-08-13-loop5-integration-reports-success-while-integrating-nothing.md` was written about; this
is a second, independent route into it.

**One defect or a design gap?** A design gap. `record_evidence` has no way to name a commit that
does not exist yet, and the Hub commits on delivery by deliberate design
(`0c88233`'s D6: the staging placement before delivery "is load-bearing"). Either the footprint is
resolved at delivery rather than at record time, or `record_evidence` must be able to say "the
commit this turn produces".

**Not covered by any existing change or exploration** — `grep` over `openspec/` finds nothing.

### 2. A skipped integration can never be retried, and the error tells you to do the one thing that will not work

Integration fires **only** on the transition into `approved`. There is no retry surface anywhere:
`hub/hub/api/v1/tasks.py:341` exposes read-only history (`history_for`), and no
reintegrate/retry route exists in the codebase.

I deliberately left `main_branch` unset to exercise test-guide step 6. Both tasks were approved by
agents and both merges were skipped:

```
13:55:05 task-8822cced skipped  — this project has no main branch set — choose one in the project's settings
13:56:07 task-e99f86a3 skipped  — this project has no main branch set — choose one in the project's settings
```

I then did exactly what the message asks — chose `master` in settings. Nothing re-ran. The tasks
were already `approved`, so the trigger had already fired. **The remediation the error message
instructs the operator to perform cannot take effect.**

The verifier tried to recover and reported the wall precisely:

> Could not complete the re-open: AgentWeave rejected `approved → under_review` with HTTP 409
> because approved tasks have no agent transitions. I re-issued `approved`, but integration did not
> run.

Re-issuing `approved` is accepted and refreshes the timestamp, but does not re-run integration —
so the one recovery an agent *can* perform silently does nothing.

The operator hits the same 409, which at least names the way out:

```
409: Cannot move a task from 'approved' to 'under_review'.
     From 'approved' the available transitions are: revision_needed.
```

Recovery required walking `approved → revision_needed → in_progress → completed → under_review →
approved` by hand. That works — the merge then ran and succeeded — but it is undocumented, it
falsifies the task's review history, and no agent can do it.

**Cost:** the run's only unrecoverable-by-agents stall. This is the single most likely way a real
operator loses an afternoon.

**One defect or a design gap?** A gap with a cheap fix available: make the skip reason actionable
(offer a retry), or re-attempt integration when a project's `main_branch` is set while approved
tasks have skipped merges.

### 3. A failed run returns its input to the queue, and every later turn stacks behind it

The Codex app-server died mid-run (`run-de931e56`). The run's queue entry went back to `queued`
rather than being consumed. Every subsequent turn to that agent — including `--fresh` — was
deferred behind it:

```
status: queued  an older conversation's queued input is being delivered first
```

Because the requeued entry is bound to the dead conversation, each delivery re-crashed the
app-server. Four entries piled up and four consecutive runs failed:

```
entry-50d9f7de verifier queued  'Reply with just the word OK.'
entry-07556308 verifier queued  'Quick check: reply with the current HEAD commit...'
entry-48b6b158 verifier queued  "I have now chosen 'master' as the project's main branch..."
entry-93dc4364 verifier queued  "I have now chosen 'master' as the project's main branch..."
```

`--fresh` is defeated by this: the operator's escape hatch for a poisoned conversation cannot be
reached while a queue entry from that conversation exists.

`DELETE /api/v1/projects/{id}/queue/entries/{entry_id}` does exist
(`hub/hub/api/v1/inbound_queue.py:209`) and withdrawing all four unwedged the agent immediately —
a `--fresh` turn then returned `OK`. But nothing in the failure surfaces that route, and the
symptom ("queued behind an older conversation") reads as patience being required rather than
intervention.

**Root cause isolated:** the verifier's *conversation* was poisoned, not the agent and not Codex.
The architect, also Codex, ran fine throughout; the verifier ran fine on a fresh conversation once
the queue was cleared.

### 4. `app-server process ended` carries no diagnostics

```json
{"agent": "verifier", "run_id": "run-de931e56", "error": "app-server process ended"}
```

No exit code, no stderr tail, no last JSON-RPC method. The Hub log holds nothing either. Four
failures produced four identical strings, so nothing distinguishes a crash from a kill from a
protocol error. Diagnosing finding 3 required inferring the cause from which agents still worked.

### 5. `requirement_ids` reads `None` on `TaskResponse` while 18 link rows exist

Both tasks returned `requirement_ids: None` from `GET /projects/{id}/tasks`, yet
`task_requirement_links` held 9 rows each. The links are real — they are what let the merge join
evidence to a task — but the API says the task has none. Anyone diagnosing a `NOTHING_TO_MERGE`
from the API response would conclude the links are missing and go fix the wrong thing. This is the
exact trap `tasks.md` 6c.1 warns about, reachable from the read side.

### 6. `/health` reports `ui_stale` for a UI commit that could not change the bundle

```
"ui_stale": true, "hub/hub/static/ui was last rebuilt 2026-08-14T14:06:13+01:00,
 but hub/ui/src has commits as recent as 2026-08-14T14:20:18+01:00"
```

The later commit (`73f3017`) added four lines of TypeScript *types* to `api/tasks.ts`. Types are
erased at build; I rebuilt and `diff -rq` against `hub/hub/static/ui` was identical. The check
compares commit timestamps and cannot know that, so it cries stale on any type-only change. Minor,
but it trains the operator to ignore a staleness warning that is usually real.

### 7. An agent interviewing in prose opens no question row

The architect asked six substantive, well-formed questions — and asked them as chat text, not via
`ask_user`. `GET /projects/{id}/questions` returned `[]` and the run finished `completed`. An
operator not reading the transcript sees a finished run and no pending anything.

Recorded as an observation only: **G5, the interview backstop, is a declared non-goal** — *"the AI
should answer or not deliberately based on the test."* Noting it because the run exercised it, not
to re-propose it.

---

## What held

Worth as much as the findings, and several of these were the change's whole point.

- **The three evidence tools work from real agents.** `record_evidence` ×18, `list_evidence`,
  `decide_evidence` ×18, all through MCP from Claude and Codex agents. This is what `0c88233` set
  out to fix and it is fixed.
- **The `can_accept_evidence` grant sets and reads back** — `{'verifier': True}` after PATCH,
  `False` for the other two. The hand-built `AgentSummary` trap (6a.2) is genuinely covered.
- **The task-document context block works.** The builder was told a task ID and *nothing else* — no
  document path — and read the specification without asking anyone for it. Phase 7's purpose,
  confirmed live for the first time.
- **Build artefacts stay out of the Hub's commit.** 23 tests ran, so `__pycache__` certainly
  existed; the snapshot commit is 4 files, `git status` in the worktree is clean, and nothing
  matching `__pycache__|*.pyc` is anywhere on the branch or on `master`. Phase 1, confirmed live.
- **Declared task titles are board-sized** — "Implement refund calculation", "Verify refund rules".
- **Partial settings updates work.** `PUT {"main_branch": "master"}` alone returned 200 and left
  `hop_budget` and every other field untouched. This was a 422 before phase 4.
- **The unattended peer correction loop closed.** Verifier rejected → `send_message` → builder
  re-recorded against the right commit → `send_message` → verifier accepted. Six agent runs, zero
  operator involvement, ending in correct state.
- **The verifier was genuinely strict.** It rejected all nine on a commit mismatch *despite*
  independently confirming the behaviour was correct (23/23 tests, a 7,022,808-case `Fraction`
  oracle sweep). Correct-but-unattestable was refused. That is the behaviour the evidence plane
  exists to get.
- **The architect caught a contradiction in the operator's own answers.** I stated "the cancellation
  day counts as USED" and then gave a formula and worked example implying the opposite. It refused
  to guess, computed both branches, and asked which was authoritative.
- **The architect preserved a deliberately unanswered question.** Question 6 was left unanswered on
  purpose; it recorded it as an explicit open question rather than deciding for me — and said so.
- **The arithmetic is right, checked by hand to the cent.** `1999 × 22/31 = 43978/31`,
  `divmod → (1418, 20)`, `2×20 > 31` → **1419**. `1005 × 4/8` reduces to `1005/2`,
  `divmod → (502, 1)`, exact tie, 502 is even → **502**, not 503. The half-even tie survives
  `Fraction`'s reduction, which is the part most likely to have broken silently. An independent
  sweep of tie cases found zero mismatches.
- **The integration refusal without a main branch is clear and correct**, and the settings panel now
  has the control it points at (test-guide step 6 — the message's *advice* is the problem, finding 2,
  not its accuracy).

## Not exercised

- **The grant's refusal paths.** No agent attempted to accept its own evidence, and no ungranted
  agent attempted to decide. The `self_acceptance` and `acceptance_not_granted` 403s exist only in
  tests. The grant was verified permissive, never restrictive.
- **The Codex refusal event** (phase 5). No Codex agent tried anything outside its workspace this
  run, so no refusal reached a timeline. Test-guide step 7 remains unperformed.
- **Spec evolution and peer-to-peer messaging as a scope** — deliberately out of scope again.

## Environment axis varied

Tests were run under the default console encoding and under `PYTHONIOENCODING=utf-8`: 23 passed
both times. Two runners were used throughout (Claude, Codex), which is what surfaced finding 3 as
agent-specific rather than global.
