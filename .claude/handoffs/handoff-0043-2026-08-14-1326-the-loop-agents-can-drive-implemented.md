# Handoff: an e2e run found the pipeline agents cannot drive — and all six fixes implemented

**Date:** 2026-08-14T13:26+0100 · **Branch:** hub-native-experience · **HEAD:** `a0067e0`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0042-2026-08-14-1046-what-the-loop-found-and-what-fixed-it.md`
**Status:** **chunk complete.** 9 commits this session, 9 unpushed, working tree clean apart from
one pre-existing stray file. Phases 1–8 of one openspec change done and green; phase 9 is
human-only and is the operator's.

## Goal

Three things happened this session, in order.

1. **Closed out the previous session's two verification steps.** Both green; then three small
   defects found by looking at the real project rather than the suite, fixed in `615f415` (already
   pushed).
2. **Ran `/e2e-loop` from zero** at the operator's request, scope set by them *before* anything was
   read: *"Full loop from zero"*, driven end to end. It completed — and needed rescuing twice.
3. **The operator approved a plan and said "implement iot"** (implement it). All of it is
   implemented.

The *why*, for judgment calls later: the last two sessions built `verified → integrated`. This run
found that **no agent can drive it** — both evidence routes exist on the agent plane and no MCP tool
reached either, so approval reports `skipped: no accepted evidence names a commit`. Finishing the
run took a run credential minted straight into the database and a `curl`, which no operator can do.

## Current state

### The e2e run (project `aw-loop6`, preserved)

Drove a project from nothing: interview → 10-requirement specification → approval creating 3 tasks →
a Claude builder that wrote a library late-fee calculator → a Codex reviewer, **triggered by the
builder, not by me**, which found a real `date.max` `OverflowError` the builder's own 18 tests
missed → an unattended peer-driven revision cycle → a merge to `master`.

Findings are in `openspec/explorations/2026-08-14-loop6-the-pipeline-agents-cannot-drive.md`,
ranked by cost, including a "what held" section and three corrections to my own misreads.

### What was implemented

One openspec change, `openspec/changes/2026-08-14-the-loop-agents-can-drive/`, **phases 1–8
checked, phase 9 (human-only) unchecked**. Eight commits, one per phase:

1. **`1ab590b`** — the Hub stops committing build artefacts. `snapshot_worktree` runs `git add -A`,
   so whatever an agent leaves becomes the Hub's commit; two `.pyc` files rode a builder's branch
   onto a real project's `master`.
2. **`b9ae2d6`** — declared tasks get board-sized titles. `title` is now a real payload field;
   `MAX_TITLE` 200 → 80 with a word-boundary clip.
3. **`29e525c`** — the operator can choose the main branch, plus `ProjectSettingsUpdate` for partial
   settings bodies.
4. **`2674186`** — a latent serialization bug the previous commit *exposed* (see Dead ends).
5. **`7550071`** — a Codex sandbox refusal is recorded; it previously produced no event at all.
6. **`0c88233`** — **the headline.** Three evidence tools + the grant plumbing + the read route.
7. **`73f3017`** — a task-bound agent is told which specification it implements.
8. **`a0067e0`** — task checkboxes.

## Files touched

Everything is committed. `git status --short` shows only `?? hub/agentweave.db` — a stray empty
SQLite file **already untracked at session start** and in the previous two handoffs. Not the live
database; that is `hub/data/agentweave.db`. Left alone deliberately.

Full diffstat is `git diff --stat 44600ab..HEAD` — 46 files, +3567/−529.

| path | what |
|---|---|
| `hub/hub/repo_hygiene.py` | `EXCLUDE_PATTERNS` gains `__pycache__/`, `*.pyc`, `node_modules/`, `.venv/`, `dist/`, `build/`; the module's own contradicting rule rewritten; docstring states it does **not** untrack |
| `hub/hub/spec_tasks.py` | `MAX_TITLE` 200→80, `ELLIPSIS`, word-boundary clip in `_title_from`, new `_title_for` preferring a declared title |
| `hub/hub/spec_payload.py` | `Task.title` optional field |
| `hub/hub/spec_render.py` | renders the declared title before the description |
| `hub/hub/api/v1/projects.py` | **new** `ProjectSettingsUpdate` (derived via `create_model` + `_as_optional`); `exc.errors(include_url=False, include_context=False)` |
| `hub/hub/codex_appserver.py` | **new** `_REFUSAL_LABELS` + `approval_label()`; `run_turn` gains `on_refusal`; caller reports declines. `decide_approval` **unchanged and still pure** |
| `hub/hub/api/v1/agent_trigger.py` | **new** `_on_refusal` emitter; binding resolved *before* the context render; `task_spec_document`/`task_id` passed to the renderer; import set changed |
| `hub/hub/api/v1/agents.py` | **new** `GRANT_FIELDS`; hand-built `AgentSummary` gains `can_accept_evidence`; 3 tool-surface bullets; **new** "You can decide evidence" context block; **new** task-document context block; renderer signature +2 params |
| `hub/hub/api/v1/agent_actions.py` | **new** `GET /spec/evidence` reusing `spec.py`'s `_evidence_view`/`_footprints_for`, joining `FR-n` identifiers |
| `hub/hub/mcp_server.py` | **new** `EvidenceDecision` alias; **new** `record_evidence`, `list_evidence`, `decide_evidence` — all **above** the `__main__` guard; `submit_spec_document` docstring names `title` |
| `hub/hub/run_task_binding.py` | **new** `BoundTask` NamedTuple, **new** `resolve_bound_task` (read-only), **new** `spec_document_for_task` |
| `hub/hub/api/v1/tasks.py` | `create_task_for_actor` records `spec_document_id` from agreeing requirement links |
| `hub/hub/schemas/agents.py` | `can_accept_evidence` |
| `hub/hub/schemas/tasks.py` | `spec_document_id`, `spec_task_key` |
| `hub/ui/src/api/projects.ts` | `main_branch`; **new** `MainBranchSuggestion` + `useMainBranchSuggestion`; stale comment corrected |
| `hub/ui/src/api/agents.ts` | `can_accept_evidence` + grant union |
| `hub/ui/src/api/tasks.ts` | `spec_document_id`, `spec_task_key` |
| `hub/ui/src/components/environment/ProjectSettingsPanel.tsx` | main-branch row + "Use «branch»" button |
| `hub/ui/src/components/agents/AgentSettingsControls.tsx` | **new** `EvidenceGrantSetting` |
| `hub/ui/src/components/agents/AgentSettingsPage.tsx` | mounts it in the Access section |
| `hub/hub/static/ui/` | rebuilt twice, `diff -rq` identical both times |
| **new tests** | `test_repo_hygiene.py` (12), `test_spec_declared_task_titles.py` (12), `test_agent_evidence_plane.py` (13), `test_agent_evidence_grant.py` (9), `test_task_spec_document_context.py` (12) |
| **extended tests** | `test_spec_declared_tasks.py` (+2), `test_operator_projects_api.py` (+4), `test_codex_appserver_run_turn.py` (+8), `test_mcp_body_contract.py` (+5 cases), `test_mcp_tool_schemas.py` (+2 rows), `projectSettingsPanel.test.tsx` (+4), `agentCheckpointSettings.test.tsx` (+4), `eventSummary.test.ts` (+2) |
| `openspec/changes/2026-08-14-the-loop-agents-can-drive/` | **new** — proposal, design (D1–D12), tasks, and 7 spec deltas |
| `openspec/explorations/2026-08-14-loop6-…-cannot-drive.md` | **new** — the run's findings |

## Key decisions

1. **The grant plumbing lands before the tools** (tasks 6a then 6b, never reversed). A tool whose
   route 403s for every agent is worse than no tool: the agent reports the capability as *broken*
   rather than absent, and the turn is lost either way.
2. **Three tools, not two.** Deciding names one evidence id, so listing is what makes the grant more
   than decorative; the agent plane had no `GET` at all.
3. **`decide_evidence`, not `accept_evidence`.** Rejection is half the route. A tool that can only
   accept makes rejection unreachable while HTTP allows it — a parity violation.
4. **`kind` stays a bare `str`; only `decision` gets a `Literal`.** `EVIDENCE_KINDS` is open at the
   edges *on purpose* (`db/models.py:1814-1823`); a `Literal` would make the tool narrower than its
   route, which `agent-capability-plane` forbids in either direction.
5. **`can_accept_evidence` is its own setting, not a third checkpoint grant.** Those two widen what
   an agent may *read*; this decides whether work may *merge*. Rejected: appending to
   `CHECKPOINT_GRANT_FIELDS`.
6. **The task-document context block is a new block, not the open-document block reworded.** The
   existing one says the operator is *viewing* a document and to treat it "not as an instruction to
   act on it" — backwards where the document is the work. When both name the same path, only the
   task framing renders.
7. **The task-derived path deliberately avoids `spec_turn_notice`.** It prepends "SPECIFICATION
   TURN", which is *authoring* instruction; handing it to an implementer tells it to write a
   document instead of implement one. There is a dedicated test.
8. **`resolve_bound_task` reads only; the staging stays put.** Context renders at
   `agent_trigger.py:~405`, the task bound at `~549`. The resolver hoists; `rebind_conversation` /
   `bind_run_to_task` / `record_response_run` do **not** — that placement (before delivery, which is
   what commits) is load-bearing. `BoundTask.named` exists because collapsing "this turn named a
   task" into "the thread was already about one" would rebind on every follow-up.
9. **`turn_scheduler.py` untouched.** Its `spec_document` is the operator's viewing position;
   resolving a binding in two places would guarantee drift.
10. **`create_task` records the document its requirement links *agree on*, and nothing when they
    disagree.** Guessing which document mixed work is against is worse than leaving the agent to ask.
    **Flagged to the operator as a judgement call they may want to narrow to explicit
    `spec_document` only — not yet answered.**
11. **`ProjectSettingsUpdate` derived from `ProjectSettings`, not retyped** — the handler `setattr`s
    over `merged.model_dump()`, so a field on one and not the other would validate, merge, and
    silently write nothing. Per-field constraints **are** carried (otherwise one type error
    short-circuits and hides the value errors); the cross-field `validate_threshold` is **not**.
12. **`decide_approval` stays pure**; refusal reporting is a caller callback. Reported only on a
    decline, and never when the operator was asked — that path already emits via `permissions.py`.
13. **Ignore rules cover what the Hub's own commit would sweep in** — the operator chose this over
    keeping the prior "only what the Hub creates" rule. Does **not** untrack what is already
    committed.

## Constraints and user directives (verbatim)

**From this session:**
- Scope, set before anything was read: **"Full loop from zero"**; autonomy: **"Drive it all, report
  at the end"**. Spec evolution and peer-to-peer were offered in the same list and **not** chosen —
  they remain unexercised and out of scope.
- On artefacts: **"Seed a short build-artefact list (Recommended)"**.
- On packaging: **"One change, all of it (Recommended)"**.
- On the 46 unpushed commits earlier in the session: **"Yes, push the branch"** (done — `b6afe05`).
- **"implement iot"** — approving the plan at `C:\Users\huida\.claude\plans\validated-foraging-russell.md`.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
  (Confirmed this session: no CI runs on branches; workflows trigger on `master` and tags.)
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- **G5 (the interview backstop) is a non-goal** — *"actually that's okay because this is a AI test.
  The AI should answer or not deliberately based on the test."* **Do not re-propose it.**
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence: *"The evidence can be anything… Whatever the model thinks it's necessary to show that
  his work is good."* · *"only test agents can accept the evidence… If no tester agent then all
  defers to the operator."* **(This is now actually implementable — it was not before `0c88233`.)**
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet."*
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; **never mark a task
  complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**

- **`ProjectSettings` has five required fields**, so FastAPI rejected a partial body *before* the
  handler's `exclude_unset` merge could run. The merge's own comment described behaviour nothing
  could reach. My first diagnosis ("full replacement") was right in effect, wrong in cause.
- **`exc.errors()` is not JSON-serializable when a `model_validator` raises** — the `ValueError` is
  in `ctx`, and FastAPI turns the 422 into a `TypeError` while serialising the refusal. Latent for
  as long as the body model was fully required. Needs `include_context=False`. Three
  `test_checkpoint_configuration.py` tests found it instantly; **no assertions changed**.
- **Deriving an update model with `create_model` drops per-field constraints unless you deep-copy
  the `FieldInfo`.** Without them, one type error short-circuits and hides every value error.
- **`test_operator_projects_api.py`'s `main_branch` is gated on the branch existing** — a partial-PUT
  test using `{"main_branch": "trunk"}` gets a 400, not a 422. Use `token_budget` for that test.
- **`resolve_agent_workspace` is stubbed suite-wide** by `conftest._no_real_worktree_provision`. A
  test needing the real one must capture it at import time and `monkeypatch.setattr` it back — the
  pattern is `test_agent_trigger.py:22`.
- **The `agent-context` route is `GET /agents/agent-context?agent=<name>`**, not
  `/agents/{name}/context`. The latter returns something with no `context` key.
- **`screen.queryByText(/^Use /)`** matched an unrelated `<option>` "Use the runner's model" in the
  settings panel. Anchor UI text assertions tighter than you think you need to.
- **`Button` has no `secondary` variant** — it is `primary | ghost | outline | destructive`.

**Tooling quirks, new and repeatable:**

- **The Bash tool intermittently cannot see files PowerShell can list** (hit on
  `openspec/changes/**`, `hub/tests/test_operator_projects_api.py`, `hub/ui/src/__tests__/`).
  `Glob` fails the same way. **Workarounds:** PowerShell `Get-ChildItem`, the `Read` tool, or an
  absolute path. `pytest <relative>` failed where `pytest "C:\...\<abs>"` worked.
- **`cd hub/ui && …` in one Bash call does not persist**; a later `black hub/hub/x.py` then fails
  with "Path does not exist". Prefix with `cd /c/Users/huida/Documents/projects/AgentWeave`.
- **A heredoc through the Bash tool mangles `\n` inside Python string literals.** Use `chr(10)` or
  the `Write` tool. Corrupted `repo_hygiene.py` once; restored from a backup copy.

**Carried and still true:**
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`black` without `--target-version py311`** reformats into py38-invalid `with` statements.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`**
  (`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`).
- **PowerShell's `Invoke-RestMethod` swallows error bodies** — use `curl` via Bash to read a refusal.
- **`git commit -m @'…'@` is PowerShell syntax; the Bash tool is Git Bash.** Use `git commit -F -`.
- **`npx openspec new change` rejects a name starting with a digit** — create by hand.
- **`git add -A` after `black`/`ruff --fix`** sweeps unrelated reformatting; stage paths explicitly.
- **The openspec validator reads only a requirement's FIRST PHYSICAL LINE** for SHALL/MUST.
- **Do not assert `fetchMock.mock.calls[0]` in UI tests** — any added query takes slot zero.

## Verification

**Ran, with real output, at `a0067e0`:**
- `pytest hub/tests/ -q` — **1949 passed, 10 skipped** (7m05s).
- `pytest tests/ -q` — **360 passed, 3 skipped.**
- `npx vitest run` — **854 passed, 88 files.** The documented `chartersUi`/`runnersUi` load flake
  did **not** recur in the last three full runs.
- `npx tsc --noEmit` — clean. `ruff check hub/ src/` — all checks passed.
  `black --target-version py311` on every file touched.
- `npx openspec validate --changes --strict` — **17 passed, 0 failed.**
- `npm run build`; `hub/hub/static/ui` replaced; `diff -rq` **identical** (done twice).

**Two mutation checks, because a vacuous assertion has bitten this codebase twice:**
- Deleting the `can_accept_evidence=` line from the hand-built `AgentSummary` makes
  `test_the_operator_grants_it_and_reads_it_back` fail on exactly the read-back assertion.
- Restoring the old `.gitignore` mechanism makes **all six** ignore-rule tests fail, including the
  one asserting a clean `git status` inside a real agent worktree.

**Live, earlier in the session (all on real projects, not fixtures):**
- The `615f415` ignore fix — `git status` inside `aw-loop6`'s builder worktree was **clean**.
- The footprint fix — `{"branch": "agentweave/builder", "commit_sha": "639bf9a2…",
  "reachable_from_main": false}`, matching `git rev-parse` exactly.
- The full integration chain — `skipped (nothing to merge)` → `merged` → `skipped: already in
  master` → coverage `verified / integrated` → `drift/detect` raises `[]`.

**NOT run, and it matters:**
- **Phase 9 (human-only) has not been done** — five judgements, `tasks.md` §9.
- **Nothing in this change has been exercised by a real agent.** Every assertion is a test. No agent
  has called `record_evidence`, no operator has clicked the grant checkbox, no Codex refusal has
  been seen in a live timeline, and the task-document context block has never been read by a model.
- **The Hub on `:8010` is running pre-change code** (started 12:15, before all nine commits).
- **Spec evolution and peer-to-peer messaging remain unexercised**, deliberately out of scope.

## Git state

Branch `hub-native-experience`, HEAD **`a0067e0`**, working tree **clean** except
`?? hub/agentweave.db` (pre-existing stray, not the live DB), **9 unpushed commits**.

**Live environment:** Hub on `:8010`, health `ok`, PID from 12:15 — **pre-change code, restart
before any live verification.** Find the PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`.

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4`, `aw-e2e`, `aw-loop5`
(`proj-30d900a7`), and **`aw-loop6` (`proj-c28f08df`, at `C:\Users\huida\Documents\aw-loop6`)**.

**Keep `aw-loop6`.** It is the reproduction for findings 1–5 of this session's exploration and the
only project with a real agent worktree, a real merge, and a spec whose arithmetic was verified by
hand. It contains a **hand-minted run credential `run-ev6`, token `aw_run_loop6_evidence`**, created
to work around the very defect this change fixes — **delete that row if the project is ever shared.**
Remove the whole project with `python .claude/skills/e2e-loop/e2e.py clean proj-c28f08df`.

`aw-loop5` (previous session's reproduction) also still holds a `run-verify5` credential.

## Next steps

1. **Push.** 9 unpushed commits; the `ci.yml` question is settled (*"just push the branch"*).
   `git push` — the branch already tracks `origin/hub-native-experience`.
2. **Restart the Hub onto the new code** before anything live, using the WMI command in Dead ends.
   The running process predates all nine commits, and attributing its behaviour to this change is
   the single most expensive mistake available here.
3. **Phase 9 human-only verification** —
   `openspec/changes/2026-08-14-the-loop-agents-can-drive/tasks.md` §9. **9.1 is the one the change
   rests on:** re-run `/e2e-loop` from zero, pass condition = an agent-driven project reaches
   `integration: integrated` with **no operator HTTP calls**, against a task carrying requirement
   links. §10 of the same file is the step-by-step operator guide.
4. **Answer the open question below** about `create_task`'s document inference (Key decision 10).
5. **Archive the three changes** once phase 9 passes, **in this order** —
   `2026-08-13-approved-means-it-is-in-the-product`, then
   `2026-08-14-what-the-product-actually-built`, then `2026-08-14-the-loop-agents-can-drive`.
   The last **MODIFIES** a `local-project-workspace` requirement the middle one **ADDS**, and it is
   not in the main spec yet; applied out of order the modification has nothing to modify. This is
   stated in that change's `proposal.md` under "Archive ordering". By hand — the openspec CLI
   rejects names starting with a digit.

## Open questions for the user

1. **`create_task`'s document inference** (Key decision 10). It records `spec_document_id` from the
   document its requirement links agree on, even when the caller did not pass `spec_document`.
   Should it instead only ever record an explicitly-passed document? Raised at the end of the last
   turn; not answered.
2. **`aw-loop6` cleanup** — keep as the worked example (recommended), or clean it? The minted
   `run-ev6` credential lives in it either way.
3. Carried, still unanswered: should `.claude/handoffs/` stay tracked (**now 129 files**)?

## Read on resume

- `openspec/explorations/2026-08-14-loop6-the-pipeline-agents-cannot-drive.md` — all eight findings,
  what held, and the three corrections to my own misreads. The record of what the run cost.
- `openspec/changes/2026-08-14-the-loop-agents-can-drive/tasks.md` — §9 is what remains, §10 is the
  operator test guide to follow.
- `openspec/changes/2026-08-14-the-loop-agents-can-drive/design.md` — D1–D12. **Read D6 and D7
  before touching the trigger path or the context blocks**; they encode the two traps that would
  otherwise be rediscovered.
- `hub/hub/run_task_binding.py` — `resolve_bound_task`, `BoundTask`, `spec_document_for_task`. The
  newest seam, and the one whose ordering is subtle.
- `hub/hub/mcp_server.py` — the three evidence tools, and the `__main__` guard that must stay last.
- `hub/tests/test_agent_evidence_plane.py` — the fixture shape any future agent-plane test should
  copy, and its docstring explains the `TaskRequirementLink` gate that makes a naive verification
  read as "the fix failed".
