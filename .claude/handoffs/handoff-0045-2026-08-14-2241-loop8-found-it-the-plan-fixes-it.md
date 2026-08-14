# Handoff: loop 8 drove the whole loop; a plan to fix what it found is approved-pending

**Date:** 2026-08-14T22:41+0100 · **Branch:** hub-native-experience · **HEAD:** `bcfdce1`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0044-2026-08-14-1724-six-seams-fixed.md`
**Status:** **chunk complete, nothing started.** One commit this session, 0 unpushed, tree clean apart
from one pre-existing stray file. A two-change implementation plan is written and was presented for
approval; **the user has not yet approved it and no implementation has begun.**

## Goal

Two things happened, in order.

1. **Ran `/e2e-loop` at the operator's instruction** — *"run e2e-loop to test everything. From spec to
   the final merge"*, then, asked to choose scope, **"Everything, including the UI stamp"** and
   **"Fully unattended"**. This was phase 9 of `openspec/changes/2026-08-14-the-seams-loop7-found/`.
   **Phase 9.1 passed.** The run also found nine things, one of them serious.
2. **The user said "Okay, enter plan mode and plan the fixes".** A plan exists at
   `C:\Users\huida\.claude\plans\tidy-bubbling-bubble.md`. `ExitPlanMode` was called; the client
   captured the plan and is waiting on the user.

The *why*, for judgment calls later: the previous three sessions built the evidence→integration
pipeline, made it agent-drivable, and fixed six seams loop 7 found. Loop 8 proves those fixes work
and proves that the **failure** paths around them do not. Everything found lives between two
features, invisible to 2358 passing tests.

## Current state

### The e2e run (project `aw-loop8`, KEPT deliberately)

`proj-94f3f169` at `C:\Users\huida\Documents\aw-loop8`. Drove from an empty directory: interview →
11-requirement spec for a parcel freight-quoting library → approval creating 3 tasks → a Claude
builder → a Codex verifier with `can_accept_evidence` → a rejection on merit → an unattended
peer-driven correction → two merges to `master`. Final: **11/11 requirements `verified / integrated`,
3/3 tasks `approved`**, `master` at `293b4c9`.

Kept because it is the live reproduction for findings 1 and 2. It minted no credentials.
Remove with `python .claude/skills/e2e-loop/e2e.py clean proj-94f3f169`.

Agents on it: `architect` (codex/Spec Author), `builder` (claude/Developer), `verifier`
(codex/Verifier, `can_accept_evidence=true`), `victim` (codex/Developer — the kill target).
`breaker` was never created; the Hub refused the bogus model.

### What was written

- `openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md` — **new**, the findings,
  ranked by cost, with a "What held" section.
- `openspec/changes/2026-08-14-the-seams-loop7-found/tasks.md` — phase 9 annotated with outcomes.
  **9.1, 9.2, 9.6 checked; 9.3 left UNCHECKED because it failed; 9.4, 9.5 unchecked as unreachable /
  still the operator's.**
- Both committed as `bcfdce1`, pushed.

### The findings, in the order the plan fixes them

**1. A runtime that dies mid-turn silently eats the input.** Kill the Codex app-server after the turn
starts: the run is `failed`, the agent returns to `idle`, and the queue entry stays
`state='delivered'` with `delivery_attempts = 0` — never retried, never abandoned, nobody told.
Reproduced twice (`run-332ef259`, `run-68eca96d`). `return_run_entries` is called from exactly two
places, both *pre-spawn* `except` blocks (`agent_trigger.py:1239` and `:1807`). A death once
`run_turn` is under way returns a failed `TurnOutcome` through the **normal** completion path, which
has no notion of returning input — so `RESUME_RETRY_LIMIT` and `DELIVERY_ATTEMPT_LIMIT` are
structurally unreachable on that path.

**2. Nothing drives the retry of a requeued entry.** The transport-failure branch requeues then
`return`s at `agent_trigger.py:1254` — before the `schedule_agent` the normal path runs at `:1504`.
`redrain_queued_agents` is reachable only from three project-lifecycle endpoints (project open,
settings save, relocate) and there is no periodic drain — `hub/hub/scheduler.py` is the jobs
scheduler. Observed: `entry-95f08a24` sat `queued` at attempt 1 until an unrelated `PUT /settings`
drove attempt 2, and a second one drove attempt 3.

**3. `CHECKOUT_DIRTY` instructs the operator to do the one thing that cannot work.** It says *"commit
or stash them and the next approval will merge"*. Verified: committed the dirt, re-approved → 200,
status `approved`, no new attempt, `master` unmoved; the retry route then merged immediately.
`CHECKOUT_ELSEWHERE` carries the same wording (`task_integration.py:54-61`).

**4. Two surfaces, two exit codes, one death.** `runs.error` said `exit 4294967295`
(`0xFFFFFFFF`, unsigned `-1`); the `run_failed` payload said `exit_code: 1` (the synthetic 0/1).

**5. `stderr_tail` never reaches anyone.** `_transport_failure_fields` (`agent_trigger.py:1013-1018`)
has no `stderr_tail` key at all. Empty on all four real failures. Of the three facts the last change
promised — exit code, method, stderr tail — **only `method` arrived**, and it arrived well.

**6. `ui_stale` names `make ui`; `make` is on PATH in neither Git Bash nor PowerShell here.**
`python scripts/refresh_ui_bundle.py` works. (`main.py:167`.)

**7. `requirement_ids` sorts lexicographically** — `FR-1, FR-11, FR-2, FR-3`. Cause is
`.order_by(SpecRequirement.identifier)` at `hub/hub/api/v1/tasks.py:91`.

**8. The spec declared "Open questions: None outstanding"** for the one interview area I deliberately
left unanswered, inventing six Non-goals. Its own "Limits" section contradicts it. **Not in the plan
— recorded as a question.**

**9. The merged library cannot run its own tests from a clean checkout** (`ModuleNotFoundError`;
needs `PYTHONPATH=src`, no `[tool.pytest.ini_options] pythonpath`). Both agents told the truth;
nothing in the chain asks whether the merged artefact is usable. **Not in the plan — recorded as a
question about what evidence is for.**

## Files touched

Everything is committed and pushed. `git status --short` shows only `?? hub/agentweave.db` — a stray
empty SQLite file **already untracked at session start**, named in the last four handoffs. Not the
live database; that is `hub/data/agentweave.db`. Left alone deliberately.

| path | what |
|---|---|
| `openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md` | **new this session** — nine findings ranked by cost, plus "What held". Committed. |
| `openspec/changes/2026-08-14-the-seams-loop7-found/tasks.md` | phase 9 annotated with real outcomes; 9.3 deliberately left unchecked. Committed. |
| `C:\Users\huida\.claude\plans\tidy-bubbling-bubble.md` | **new, outside the repo** — the two-change implementation plan. **Not committed and not in the repo**; it is the plan-mode file. |
| `hub/ui/src/api/tasks.ts` | edited and **reverted** during the 9.6 probe. `git status` on it is empty. No net change. |

Nothing under `hub/hub/`, `src/agentweave/`, or `hub/hub/static/ui/` was modified this session.

## Key decisions

1. **Scope was established from the user's own words before looking at what was built**, per the
   skill. They said "from spec to the final merge"; when reconciled against the six fixes, they chose
   **"Everything, including the UI stamp"** and **"Fully unattended"**.
2. **9.3 is left unchecked in `tasks.md` rather than annotated-and-checked.** It failed. The standing
   directive is that only real, verified implementation closes a task, and a phase that found a
   data-loss bug has not passed.
3. **The requeue rule is the user's explicit choice: "Any failed run, capped at 3."** I recommended
   the narrower "only when the runtime died" (`outcome.exit_code is not None`); they chose the
   broader rule. **Do not re-propose the narrow one.** Its consequence — a run that fails for a real
   reason re-runs twice then is abandoned with a reason — is accepted, and is why the plan adds the
   "your earlier attempt was cut off" note to the redelivered prompt.
4. **Two changes, not one** (also the user's choice): the data-loss fix and the text sweep have
   different risk profiles.
5. **`aw-loop8` is kept**, because findings 1 and 2 reproduce in it and the fix needs a live target.
6. **Findings 8 and 9 are deliberately out of scope** — the user chose "Findings 1-7, as two
   changes". They are product-shape questions, not defects, and are recorded in the exploration.
7. **The plan mirrors `run_reconciliation.py` rather than inventing a mechanism.** That file already
   returns entries, reports abandonment, and schedules the agent for a restart-orphaned run — it is
   the in-repo precedent for exactly the rule the user chose.
8. **`exit_code` in the `run_failed` payload is not changed; `runtime_exit_code` is added alongside.**
   `AgentOutputPanel.tsx`'s handoff detection reads the synthetic 0/1, so repurposing it would
   silently break that feature.
9. **The `AgentTool` was not used** and no workflows were run, per the session directive.

## Constraints and user directives (verbatim)

**From this session:**
- **"run e2e-loop to test everything. From spec to the final merge"**
- **"Everything, including the UI stamp"** — chosen over spec→merge only.
- **"Fully unattended (Recommended)"**
- **"Okay, enter plan mode and plan the fixes"**
- On the requeue rule: **"Any failed run, capped at 3"** — chosen over my recommended narrow rule.
- On scope: **"Findings 1-7, as two changes (Recommended)"**.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- **G5 (the interview backstop) is a non-goal** — *"actually that's okay because this is a AI test.
  The AI should answer or not deliberately based on the test."* **Do not re-propose it.** Loop 8
  re-observed it a third time (architect asked four areas as prose, `select count(*) from questions`
  → 0) and it is recorded **as an observation only**.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence: *"The evidence can be anything… Whatever the model thinks it's necessary to show that
  his work is good."* · *"only test agents can accept the evidence… If no tester agent then all
  defers to the operator."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet."*
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; **never mark a task complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.
- Session directive: **do not call the Agent tool, and do not use workflows or deep-research, unless
  the user requests it.**

## Dead ends

**New this session:**

- **`PATCH /api/v1/projects/{id}/settings` is a 405.** The route is **`PUT`**
  (`hub/hub/api/v1/projects.py:388`). Cost several minutes.
- **`GET .../project/documents/content?path=…` does not exist** (404). The spec router's routes are
  listed at `hub/hub/api/v1/spec.py`; use `GET /spec` or read the file from the project directory.
- **`GET /project/spec/requirements` returns identifier/key/anchor only — no requirement text.** The
  wording lives in the document; `_attach_requirements` reads it per document.
- **`GET /queue/status` returned `[]`** for a project with a parked entry; it did not surface the
  attempts sentence. Not chased — may be per-agent.
- **You cannot point a runner at a bad binary through the product.** `POST /runners` with a bogus
  model is refused (400, *"'not-a-real-model-xyz' is not a model 'codex' declares"*), and there is no
  per-runner binary override. The user test guide's step 7 ("point a codex runner at a binary that
  exits non-zero") assumes a surface that does not exist. Kill the process instead.
- **The Bash tool's cwd resets to the repo root between calls.** `e2e.py` must be invoked as
  `cd /c/Users/huida/Documents/projects/AgentWeave/.claude/skills/e2e-loop && python e2e.py …`
  every single time, or you get `No module named 'e2e'` / `can't open file`.
- **`sleep N` chained before another command is blocked by the harness.** Use a polling `for` loop,
  or `run_in_background`.
- **A DB timestamp is naive UTC while the machine is UTC+1.** I briefly mis-concluded that a retry
  had happened spontaneously; it had not. Compare DB times to DB times.
- **`hub/hub/api/v1/spec.py`'s coverage endpoint returns a bare list**, not `{requirements: [...]}` —
  `e2e.unwrap` on it yields strings if you guess wrong.

**Tooling quirks, re-confirmed:**

- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
  Find the PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`.
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`black` without `--target-version py311`** reformats into py38-invalid `with` statements.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`**
  (`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`). `e2e.py` reads it itself.
- **The spec router is mounted at `/api/v1/projects/{id}/project/spec/...`** — note the doubled
  `project`.
- **`git commit -m @'…'@` is PowerShell syntax; the Bash tool is Git Bash.** Use `git commit -F -`.
- **`npx openspec new change` rejects a name starting with a digit** — create by hand.
- **The openspec validator reads only a requirement's FIRST PHYSICAL LINE** for SHALL/MUST.
- **A heredoc through the Bash tool mangles `\n` inside Python string literals.** Use `Write`.
- **Long pytest runs exceed the 600s Bash timeout** (~8–12 min for the hub suite). Use
  `run_in_background: true`; the output file stays empty until the process exits.

## Verification

**Ran this session, with real output:**
- **The full e2e loop**, unattended, against a Hub restarted onto `d38419f` — confirmed on the new
  code by `INFO [alembic] Running upgrade 0071 -> 0072` in `%TEMP%\agentweave-hub.log`.
- **9.1 proved against git, not the API:** the footprint's blob for `_models.py` is
  `2c5c07b9759f…`, and `git rev-parse b8b8664:src/freightquote/_models.py` returns the same;
  `git ls-tree -r --name-only 87c050f` (the parent) returns **only `README.md`**.
- **The verifier's FR-3 rejection independently reproduced** — `Decimal("NaN")` raises
  `decimal.InvalidOperation`, not `InvalidParcel`. I also found one it missed: `Decimal("Infinity")`
  was **accepted** as a valid length.
- **Five pricing cases computed by hand from the spec and compared to the code**, all matching to the
  cent, including `0.725 → 0.73` half-up and both exact boundaries (120 cm, 30 kg).
- **Axis varied:** 111 tests pass under `PYTHONIOENCODING=cp1252`, under `PYTHONUTF8=0 LANG=C
  LC_ALL=C`, and from a foreign cwd. **No encoding-class defect this time.**
- **Findings 1 and 2 reproduced from the database**, not inferred: entry rows showing
  `state='delivered', delivery_attempts=0` after two kills; an entry parked at attempt 1 until an
  unrelated settings save moved it.
- **9.6 both directions:** an uncommitted types-only edit under `hub/ui/src` raised `ui_stale` within
  the TTL and reverting cleared it, with **no Hub restart**. `refresh_ui_bundle.py --check` passes.
- `npx openspec validate --changes --strict` — **18 passed, 0 failed.**
- `command -v make` and `powershell Get-Command make` — **absent in both.**

**NOT run, and it matters:**
- **No test suite was run this session.** `pytest hub/tests/`, `pytest tests/`, `npx vitest run`,
  `npx tsc --noEmit` and `ruff` were **not** executed. The last known-good numbers are from handoff
  0044 at `4ec3c50`: hub 1998 passed / 11 skipped, cli 360 passed / 3 skipped, vitest 864 passed.
  Nothing in `hub/hub/` or `src/` changed since, so they should still hold — but that is an
  inference, not a measurement.
- **Not one line of the plan is implemented.** No fix exists for any of the nine findings.
- **The plan itself is unapproved.** `ExitPlanMode` returned "the client captured your proposed plan.
  Stop here and wait for the user's feedback".
- **`make ui` still has never been executed** anywhere — `make` does not exist on this machine.

## Git state

Branch `hub-native-experience`, HEAD **`bcfdce1`**, working tree **clean** except
`?? hub/agentweave.db` (pre-existing stray, not the live DB), **0 unpushed commits** — pushed at
`d38419f..bcfdce1`.

**Live environment:** Hub on `:8010`, started this session via WMI onto `d38419f` (PID was 14304;
re-find it rather than trusting that number). It is **one commit behind HEAD**, but `bcfdce1` is
documentation only, so it is functionally current.

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4`, `aw-e2e`, `aw-loop5`,
`aw-loop6` (`proj-c28f08df`), `aw-loop7` (`proj-e6c1de74`), and **`aw-loop8` (`proj-94f3f169`, at
`C:\Users\huida\Documents\aw-loop8`)**.

**Keep `aw-loop6`, `aw-loop7` and `aw-loop8`.** Loop 6 holds a hand-minted credential `run-ev6` /
`aw_run_loop6_evidence` — **delete that row if ever shared.** Loop 7 is loop 7's reproduction. Loop 8
is the reproduction for findings 1 and 2 and minted no credentials.

## Next steps

1. **Ask the user whether to implement the captured plan** — it was presented and they have not
   answered. Do not start without that. If they say yes, begin with **Change A, step A1**: in
   `hub/hub/api/v1/agent_trigger.py`, in the session block at ~`:1855-1890` (the Codex path), add
   `returned = await return_run_entries(db, run_id)` when `final_status == "failed"`, before that
   block's `await db.commit()`; then after the commit call
   `await _report_abandoned_entries(db, project_id, agent, run_id)` and persist+broadcast
   `queue_entry_queued` per returned id, copying the loop at `:1250-1253`. Then do the identical
   thing at `:1415-1451` for the exec path. Read `hub/hub/run_reconciliation.py:29-99` first — it is
   the template.
2. **Create the two openspec changes by hand** (the CLI rejects names starting with a digit):
   `openspec/changes/2026-08-14-a-failed-run-does-not-eat-its-input/` and
   `openspec/changes/2026-08-14-what-a-failure-tells-the-operator/`, each with `proposal.md`,
   `design.md`, `tasks.md` (agent-verifiable split from human-only, plus a user test guide) and
   `specs/<capability>/spec.md` deltas. Capability mapping is in the plan file.
3. **State the archive ordering in each proposal.** Both changes MODIFY requirements that the
   still-unarchived `2026-08-14-the-seams-loop7-found` ADDS. Full order: the four changes named in
   handoff 0044, then `2026-08-14-the-seams-loop7-found`, then A, then B.
4. **Re-run the kill test after implementing** — trigger a Codex agent on a long turn, kill the
   `codex` process, and expect a new run to start **on its own** with `delivery_attempts = 1`.
   `aw-loop8` is already set up for this; the `victim` agent exists for exactly this purpose.

## Open questions for the user

1. **Approve, amend, or reject the plan at `C:\Users\huida\.claude\plans\tidy-bubbling-bubble.md`.**
   This is the blocking one.
2. **Finding 8** — may a spec document assert "Open questions: None outstanding" about an area the
   operator never addressed? Deliberately out of the plan's scope.
3. **Finding 9** — evidence proves behaviour but nothing proves the merged artefact is usable. The
   widest of the findings; probably wants an exploration of its own rather than a fix.
4. Carried, still unanswered: should `.claude/handoffs/` stay tracked (**now 131 files**)?

## Read on resume

- `C:\Users\huida\.claude\plans\tidy-bubbling-bubble.md` — the plan. **Outside the repo.** Read first;
  everything in Next steps depends on it.
- `openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md` — the nine findings with
  their evidence, and the "What held" section that says which gates were exercised and passed.
- `hub/hub/run_reconciliation.py` — 99 lines, the template for all of Change A. Its comment at
  `:53-60` is the reason divergence evaluation is skipped when entries were returned.
- `hub/hub/api/v1/agent_trigger.py` — the four sites Change A touches: `:1239`, `:1254` (pre-spawn,
  exec), `:1807`, `:1822` (pre-spawn, codex), `:1415-1451` (normal, exec), `:1855-1890` (normal,
  codex).
- `hub/hub/inbound_queue.py` — `return_run_entries` (`:159`), the two limits, and
  `format_turn_prompt` (`:94`) which Change A step A3 modifies.
- `openspec/changes/2026-08-14-the-seams-loop7-found/tasks.md` — §9 now records what passed and what
  did not; §10 is the operator test guide, whose step 7 is known to be unperformable as written.
