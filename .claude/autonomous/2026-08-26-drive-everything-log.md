# 2026-08-26 — drive everything, then fix it

An unattended run of the `/e2e-loop` method: drive AgentWeave end to end as a real operator would,
across every feature area, and fix what breaks. Newest entry at the **bottom**.

Written for someone who was asleep. Each entry says what was attempted, what actually happened, and
what a reviewer should distrust.

- **Branch:** `autonomous/2026-08-26-drive-everything-and-fix-it`
- **Parent:** `master` at `721909089e2d7664a5891a1a90c8e5fc8f5e069f` (handoff 0088)
- **Window:** 00:05 → 08:00 local
- **Runner:** headless `claude` (Sonnet 5), `unattended-full-access`, one iteration per firing of the
  `AgentWeaveAutonomousSession` scheduled task
- **Findings numbering:** F51 onward in `scripts/drive/FINDINGS.md`, continuing the 2026-08-23 series

---

## Iteration 0 — preparation (attended, operator awake)

Written by the interactive session that armed the run, before any queue work.

**What the operator asked for, in their words:** *"Prepare and execute a autonomous run untill 8AM.
Basically is a e2e-loop to drive everything in agentweave and then fix everything that you found that
did not work."*

**Four things settled with the operator awake**, so the loop meets none of them at 3am:

| Question | Answer | Rejected alternative, and why it matters |
|---|---|---|
| Runner | Claude **Sonnet 5** | Opus 5 (stronger on between-features judgement, materially more expensive over 8h); Codex (different blind spots, untested as driver on recent work) |
| Spend | Real agents, **cheap models only** — Haiku 4.5 and gpt-5.4-mini | No-agent-spawns was rejected as structurally blind to the run/checkpoint/review seams, which is where most findings have come from |
| F50 | **Pre-authorised** — render the probe failure | Skipping the checkpoint was rejected: the computed half is the Hub's own and stays accurate, so discarding it to avoid a bad paragraph is the more expensive error |
| F47 | **Parked** — not selected | Left in `decisions_for_user`; if the drive re-finds it from the outside that is confirmation, not news |

**Environment prepared, and two real traps found while preparing it.** Both would have cost the loop
an iteration, and both are now in `STATE.json`'s `dead_ends`:

1. **The `e2e-loop` skill's own reference restart command omits `DATABASE_URL`.** A Hub started with
   it lands on `hub/data/agentweave.db` — a real but stale database last written 2026-08-23 that
   nothing serves. It comes up `{"status":"ok"}` and lists a **completely different set of
   projects**, so it looks entirely healthy. Measured here: after restarting with that command,
   `GET /api/v1/projects` returned `ui-showcase-2026-08-22` instead of `ledger-stress`, and
   `GET /projects/proj-18e5d4e0/tasks` returned **404 Project not found** — which reads as data loss
   rather than as a wrong file. Restarted again with `DATABASE_URL` set to the beta profile and
   confirmed the project list, not just `/health`.
2. **`e2e.py`'s `DB` constant defaults to the same stale path**, so the harness's sqlite read paths
   report an empty world unless `AW_HUB_DB` is set. Its HTTP paths are unaffected, which makes the
   mismatch look like missing data. The harness invocation in `STATE.json` sets it.

**State of the world at arming time, measured rather than assumed:**

- Trial Hub on **8010**, PID 9116, started from `hub/` from source on `7219090`, serving
  `~/.agentweave/hub/profiles/beta/agentweave.db`. Confirmed by the project list.
  Backed up first to `agentweave.db.bak-pre-0089-drive`.
- The previous instance (PID 24628, started 19:40) was serving **pre-F43 code** — handoff 0088 said
  so and it was correct. That is why it was bounced.
- Four projects. `ledger-stress` (`proj-18e5d4e0`) carries the accumulated state: an approved
  document, 15 tasks including **two in `under_review`** (`task-23a0986e7fe9` with `critic`,
  `task-3cd54c17faa6` with `relay`), agents `builder`/`critic` on Haiku and `relay` on Codex mini.
- **Six jobs, all disabled. No enabled jobs in any project.** Nothing was spending at arming time.
- All four projects read `main_branch: null`. Whether that is pre-F4 data or F4 failing to fire is
  **undetermined** and is Q1's job to settle. Recorded as a decision for the operator because fixing
  it on `ledger-stress` would be a write to their fixture.
- `claude` 2.1.238 and `codex` both on PATH.

**Not yet verified at the time of writing:** the full Hub suite was started at 23:50 and was at 33%
when this entry was written. The arming step below does not proceed until it is green — if it is
not, the first iteration inherits a red suite and cannot tell its own breakage from the inherited
one.

**What a reviewer should distrust in this entry:** nothing was driven yet. Everything above is
environment measurement, and the only claims are ones with a command and its output behind them.

---

## Iteration 0b — the baseline is green, and prep found three more things

**The green baseline, measured on the branch tip before any queue work.** This exists so that a
failure appearing overnight is known to be *this run's* rather than inherited:

| Check | Result |
|---|---|
| `py -3.11 -m pytest hub/tests/ -q` | **3127 passed, 84 skipped, 1 xpassed, 0 failed** in 672s |
| `py -3.11 -m pytest tests/ -q` | 440 passed, 3 skipped |
| `py -3.11 -m ruff check src/ hub/ tests/` | All checks passed |
| `black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311` | 481 files unchanged |
| `npx openspec validate loop-becomes-a-flow --strict` | valid |

Note the suite took **11 minutes, not the 22–23** every recent handoff claims. That figure is stale
and is corrected in `STATE.json`.

**Three things prep found, beyond the two database traps in iteration 0.**

**1. The driver ignored the model the operator chose.** `run-iteration.ps1` invoked `claude -p`
with no `-m`, so every firing would have fallen back to the CLI's own default. This machine's
`~/.claude/settings.json` says `"model": "opus[1m]"`. The operator selected **Sonnet 5**, so an
eight-hour run would have been **Opus end to end**, at several times the authorised cost, while
`STATE.json` recorded `"model": "claude-sonnet-5"` as pure decoration. Fixed for both runners —
leaving half of it makes the next Codex run silently wrong the same way. Verified: parses under
PS 5.1, ASCII-only, and `claude -p ... --model claude-sonnet-5` answers. (`f739ea6`)

**2. `e2e.py clean` printed "removed" over a directory that was still there.** Found by cleaning a
throwaway project during prep and then *looking* — the rows went, the tree stayed.
`shutil.rmtree(..., ignore_errors=True)` is a lie on Windows: git marks everything under
`.git/objects` read-only, `rmtree` raises `PermissionError` on the first one, and `ignore_errors`
swallows it. This matters because Q10's tidy-up depends on `clean` being honest, and the skill's
own warning is that *a stray test project is indistinguishable from a real one a week later*.
Fixed and verified causally against the abandoned directory: `exists after -> False`. (`03e785e`)

**3. F4 is not broken, and the brief was corrected before the loop could waste an iteration on it.**
All four projects appeared to read `main_branch: null`. They do not — `GET /api/v1/projects` and
`GET /projects/{id}` simply **do not carry the field**; it lives on `GET /projects/{id}/settings`,
the same trap `checkpoint_runner_id` set for handoff 0088. A project created fresh during prep came
up `main_branch: "master"`, and `ledger-stress` already reads `"master"`, so **Q5's integration
step is not blocked**. What had been written as a decision for the operator is now recorded as
resolved.

**Armed with:** ten queue items alternating drive and fix; `Q4` carrying the highest-value gap in
the repository (F43's run-boundary checkpoint hook has never fired live, which handoff 0088 names
as the residual risk in `loop-becomes-a-flow`); F50 pre-authorised; F47 parked; cheap models only.

**What a reviewer should distrust:** still nothing driven. Every claim above has a command and its
output behind it, and the three fixes were each verified causally rather than by assertion. The one
thing prep could **not** establish is whether the queue is correctly *sized* for eight hours — that
is a guess, and the morning summary should say how far it actually got.

---

## Iteration 1 — Q1: cold start, a fresh project through the whole setup path

**2026-08-26T00:07+01:00.** Reconciled first: branch and `git log` matched `STATE.json` exactly
(`2ab1ec8` tip), tree clean, Hub `/health` ok and `/api/v1/projects` listed `proj-18e5d4e0
ledger-stress` — the beta database, not the stale one.

**Setup.** `e2e.py setup drive-2026-08-26` created `proj-8605b92d0028` at
`C:\Users\huida\Documents\drive-2026-08-26`, marker confirmed:
`.agentweave/project.json = {"version": 1, "project_id": "proj-8605b92d0028"}`, nowhere else on
disk.

**Seeded a real subject, not a fixture.** `inventory.py` + `test_inventory.py`: an `Item`/pricing
module with three defects the tests do not cover — `apply_bulk_discount`'s off-by-one drops the
last item (`range(len(items) - 1)`), `is_low_stock` uses float `==` instead of a threshold
comparison, `add_tag` carries a mutable default-argument list across calls. All four tests pass
(`4 passed in 0.01s`) while masking every one of the three — the same shape as `ledger`. Committed
into the drive project's own git repo (`c88133f`) so a reviewer/author agent in Q2 has something
real to look at.

**Registered the two cheap-runner agents**, with one piece of self-caught friction: the first
attempt bound `author` with charter substring `"writ"`, which matched `Underwriter` (the substring
is *inside* "Underwriter") rather than failing or reaching `Spec Author` — a harness (`e2e.py`)
naive-substring issue, not a product defect; `e2e.py`'s own `cmd_agent` is idempotent on PATCH, so
re-running with `"Spec Author"` fixed it cleanly. Final state, confirmed from
`GET /api/v1/projects/{id}/agents`:

| agent | runner | charter |
|---|---|---|
| `author` | `runner-4943e0702172` (claude / claude-haiku-4-5-20251001) | `charter-35ddf2283310` Spec Author |
| `reviewer` | `runner-e7784567779d` (codex / gpt-5.4-mini) | `charter-3be3dd63c942` Code Reviewer |

**What HELD.** The board came up empty and coherent (`GET /tasks` → `[]`, no half-populated state).
The two project-default runners (`Claude (default)`, `Codex (default)`) appeared alongside the two
just-registered ones — seeding worked, nothing was overwritten. All 9 starter charters were present.
`GET /projects/{id}/settings` read `main_branch: "master"` on the very first read of a freshly
opened project — reconfirms F4 fixed, now on a *second* fresh project, independent of the one used
during prep. Repository root `git status` stayed clean throughout.

**No new product findings.** Q1 was cold-start plumbing and every measured row was correct on the
first real try (after the self-caught harness substring mistake, which is not product behaviour).
Nothing to number as F51 yet — the first real product finding, if any, will come from Q2 driving the
document flow.

**What a reviewer should distrust:** the charter-substring friction was self-inflicted (my choice of
match string, not a harness or product bug) — recorded so nobody re-diagnoses it as a real defect.
Everything else in this entry has a command and its output behind it above.

**Next:** Q2 — drive the spec flow live on `proj-8605b92d0028`, with `author` interviewing on a new
document, honestly answered but one `ask_user` question left deliberately unanswered.

---

## Iteration 2 — Q2: drive the spec flow, document to materialised tasks

**2026-08-26T00:07–00:18+01:00.** Reconciled first: branch/log matched `STATE.json`, tree clean,
Hub `/health` ok, `e2e.py state proj-8605b92d0028` showed the empty board Q1 left.

**Reproduced the UI's own "start exploration" flow through the real HTTP surface**, in the same
order the frontend makes the calls: `e2e.py doc-new` (`POST .../project/documents`, what
`ConversationView.tsx`'s `startExploration` calls via `createDocument.mutate`) created
`spec/changes/onyx-sylph/spec.html`, then `e2e.py turn author ... --doc <that path>` triggered the
interview with `spec_document` set to it, exactly as `specDocumentPath` feeds the composer.

**F51 (A) — found here, live, and written up with row ids in `scripts/drive/FINDINGS.md`.** The
agent never wrote to the document the operator's press created. It called `create_spec_document`
and built an entirely new one (`spdoc-f64ba8051a5b`, born `golden-sylph`, renamed to
`fix-three-bugs-in-inventory-module`) **in the same run** (`run-8555716d6b9b`) that received
`spec_document=spec/changes/onyx-sylph/spec.html`. The operator's own document
(`spdoc-9c8691592be1`) sits in `exploring` with `requirements: []` and was never touched again —
confirmed straight from `spec_document_events`, not the transcript. Root cause is in
`hub/hub/api/v1/agents.py`'s "Open specification document" context block: it tells the agent
*"This is where they are looking right now. Treat it as context for what they ask, not as an
instruction to act on it"* — correct for an unrelated document happening to be open, wrong for the
one `startExploration` just created specifically to be written into — and nothing downstream
(the phase-duty text, the `create_spec_document` tool description, or `spec_turn_notice`) ever
names the open path as the one to pass to `submit_spec_document`. Every "start exploration" press
produces exactly this: a correct document plus a permanent empty husk, compounding into F37. Full
write-up, root cause with line numbers, and a fix sketch are in the findings file. Left unfixed for
Q3.

**Deliberately left one question unanswered, and it HELD.** The agent's first reply asked five
clusters of questions in prose (the exploring-phase duty: "interview in your reply, not through a
tool"). I answered four honestly and decisively, omitting `add_tag`'s two sub-questions entirely.
The next turn (`run-1b0019b3a0da`) did **not** invent an assumption and did **not** submit anything
— it stopped and asked the same `add_tag` question again, explicitly. Confirmed from `--- document
events ---`: no new `content` row between the two turns. This is the exact failure mode F38 was
fixed against, and it held on live re-drive.

**F35 reconfirmed live, not new.** Once I answered the last question, `submit_spec_document` failed
**nine times** in one turn (`run-ada01aa19b51`) before succeeding — `scope` must be a dict, then
`requirements` need a `key`, then a `modal` field restricted to `MUST/SHOULD/MAY/SHALL`, then
`acceptance_criteria` need `given`/`when`/`then` and their own `key`, and so on — the agent
rediscovering the nested schema one Pydantic error at a time, same shape `scripts/drive/FINDINGS.md`
already records as F35 (C). Not logged as a new finding; logged here as a second live sample
confirming the existing one.

**Close → propose → approve, and real requirement traceability, confirmed from rows, not
titles.** `e2e.py close` then `propose` then `phase ... approved` moved
`spec/changes/fix-three-bugs-in-inventory-module/spec.html` from `exploring` to `proposed` to
`approved` and returned `tasks_created: [task-06e74937de88, task-a9f72e6c80f8,
task-9b0b4a141b21]`. `tasks.requirements` is `NULL` on all three (a legacy/unused column, not a
bug) — the real link lives in `task_requirement_links`, and it is correct:
`task-06e74937de88` ↔ `FR-1` + `FR-2` (`apply-bulk-discount-all-items`,
`apply-bulk-discount-validate`), `task-a9f72e6c80f8` ↔ `FR-3` (`is-low-stock-lte`),
`task-9b0b4a141b21` ↔ `FR-4` (`add-tag-no-accumulation`) — matching exactly what the agent's own
reply said it was bundling. This is the dependency graph the queue item asked to verify, and it
HELD.

**What a reviewer should distrust:** I did not exercise a genuine `ask_user` tool call this
iteration — the exploring-phase duty routes the interview through reply text, not the tool, so the
"blocks / times out / vanishes" question from the queue item is answered here only for the
reply-text path (it neither blocked nor vanished; see above). The `ask_user` tool itself, its
timeout, and F14 are Q8's job, not exercised here. Everything else above has a row id or a
transcript quote behind it.

**Repository root** stayed untouched — `git status` after the whole drive showed only
`FINDINGS.md` and `STATE.json` modified.

**Next:** Q3 — fix pass 1. F51 is the one severity-A finding this run produced and is the natural
first item: it is a real product defect (not a design gap), reproducible in two lines of HTTP calls,
and its fix sketch is already written in the findings file. Mutation-check it per the queue's rule
before calling it done, and verify live against a fresh `doc-new` + `turn --doc` pair on this same
project once fixed.

---

## Iteration 3 — Q3: fix pass 1, F51

**2026-08-26T00:07–00:31+01:00.** Reconciled first: branch/log matched `STATE.json` (`d92b466`
tip), tree clean, `next_action` named F51 as Q3's single item.

**Root cause read from the code, not just the findings file.** `_render_hub_agent_context`'s "Open
specification document" block (`hub/hub/api/v1/agents.py`) tells the agent to treat the open
document as context, never an instruction — correct for an unrelated document, wrong for the one
`startExploration` just created to be written into.

**One correction to the findings file's own fix sketch, made during implementation.** The sketch
said to key off `content_digest` being empty. It is not: `POST /documents` ("start exploration")
calls `spec_service.save_document` immediately with `requirements: []`, so `content_digest` is set
from the moment of creation — every open document looks "written" by that signal, including the
one this fix exists for. `requirement_digests` is the real signal: `{}` until a submission carries
at least one requirement (`spec_digest.payload_digests` returns `{}` for zero requirements), which
is exactly "start exploration"'s own state and never a genuinely-written document's. Caught by
writing the regression test first and watching it fail against the sketch's own logic before the
fix was even applied — worth recording because the sketch was written confidently and was wrong in
a way that would have shipped a fix that never fires.

**Fix.** `_render_hub_agent_context` and `spec_turn_notice` (`hub/hub/launchability.py`) both now
branch on `phase == "exploring" and not row.requirement_digests`: when true, the block names
`open_spec_path` directly as the `submit_spec_document` target and says not to call
`create_spec_document`. `_spec_phase_for` (`hub/hub/api/v1/agent_trigger.py`) now returns
`(phase, is_unwritten)` instead of just `phase`, so the turn-prompt copy carries the same signal as
the canonical context — the queue item's own point, that `spec_turn_notice` is "the copy that wins
competing attention" and needed the identical fix, not just the standing context.

**Regression tests**, `hub/tests/test_task_spec_document_context.py`, three new (`test_f51_*`): one
asserts the new instruction fires and the old framing is absent on an unwritten document; one
asserts the *old* framing still holds on a document that already has content — this is the guard
against over-firing, since the general "treat it as context" framing is correct there and must
survive; one exercises `spec_turn_notice` directly for both cases. 23/23 passed in the two files
touched (`test_task_spec_document_context.py`, `test_spec_turn_notice.py`).

**Mutation-checked** per the queue's rule: stashed only the three source files (not the tests),
reran — exactly `test_f51_an_unwritten_open_document_is_named_as_the_write_target` and
`test_f51_spec_turn_notice_names_the_unwritten_path` failed, by name, with the expected messages
(old framing present where it should be absent; `spec_turn_notice` raising `TypeError` on the new
kwargs). The "keeps the old framing" guard test correctly still passed — that case was never
broken, which is the point of having it.

**Verified LIVE**, not just against the fixture. Restarted the trial Hub (`Stop-Process` on the PID
holding port 8010, relaunched `uvicorn hub.main:app` from `hub/` with `DATABASE_URL` pointed at the
beta profile — confirmed via `e2e.py state proj-8605b92d0028` reading the same project state as
before the restart, so this was the beta database, not `hub/data/agentweave.db`). On
`proj-8605b92d0028`, the same project F51 was found on: `e2e.py doc-new` produced
`spec/changes/lilac-chimera/spec.html`; turn one (a genuine interview reply, prose only, no tool
call) left **no document event at all** — no second document, which is the negative case the fix
protects; turn two, answered honestly, ended in `rename_spec_document` then `submit_spec_document`
(with one blocking retry — five requirements against a three-per-task limit, an unrelated and
already-known shape, not F51). `spec_document_events` afterward: `renamed` then `content`, both
`agent/author`, **no `created` event** after the operator's own `doc-new` press. Three documents on
the project afterward, not four — `create_spec_document` was never called. Resolution written up
under F51 in `scripts/drive/FINDINGS.md` with the corrected root cause and the live evidence.

Ran the touched-file slice of the suite in the background while driving live (`-k "spec or
agent_context or agent_trigger or launchability"`): 672 passed, 18 skipped, 1 xpassed, 0 failed.
`ruff check` clean on the four changed files; `black --check` initially flagged
`agent_trigger.py` (the new multi-line `_spec_phase_for` signature and the `spec_notice` call
site), reformatted with `--target-version py311` and reverified both the formatter and the tests
after.

**What a reviewer should distrust:** the full `hub/tests/` suite (all ~3100) has not been rerun
this iteration — only the touched-file slice (672 tests) and the two directly-relevant files. Q9's
full sweep is still where the whole-suite green gets re-established. The live verification used a
throwaway document (`lilac-chimera` → `cli-wrapper-for-inventory-stock-level-queries`) on the
Q1 drive project rather than a fresh project — deliberate, to reuse `proj-8605b92d0028`'s existing
two cheap-runner agents rather than registering a third pair, and because the queue's own
`next_action` named this project for the re-drive.

Q3 closes: F51 was the only severity-A finding Q1/Q2 produced, and it is now fixed, tested,
mutation-checked, and verified live.

**Next:** Q4 — exercise the run-boundary checkpoint hook live on `proj-18e5d4e0` (ledger-stress).
Create a flow job over a loop, enable it, let a real agent turn end so the hook fires, confirm from
the rows (checkpoint with non-null `loop_id`, note matching the author's, briefing containing it),
then disable the job again before the iteration ends.

---

## Iteration 4 — Q4: exercise the run-boundary checkpoint hook live, and F52 instead

**2026-08-26T00:35–01:05+01:00.** Reconciled first: branch/log matched `STATE.json` (`0f2d225`
tip), tree clean, Hub `/health` ok, `e2e.py state proj-18e5d4e0` matched what handoff/Q3 described.

**Chose `loop-a5613d9f7723` ("Width bench", `job-f632ee565238`) over the pre-existing "Ledger
flow" loop.** `job-bdea22bb0308` ("Ledger flow", the loop F43/F44's write-up already used) carries
inherited mess from 2026-08-24/25 — a stalled queue, one open question, two tasks showing
`agent_role: "working"` against `firing_active: false` (a likely stale in-flight marker from an
interrupted run) — and firing it risked producing results contaminated by state this iteration did
not cause. "Width bench" was clean: `run_count: 0`, three pending tasks, no stall, no open
questions, `checkpoint_runner_id` already set project-wide. Enabled it, fired it manually
(`POST /jobs/{id}/run`), then watched the real run.

**First friction, harness-only: `POST /jobs/{id}/run`'s own `run_id` is a `JobRun` id, not a
`Run` id.** `e2e.py watch <that id>` reported "no such run" — the actual agent conversation's run
id (`run-2f63d76eeae2`) had to be read from the `runs` table directly. Not a product defect (the
two ids are genuinely different rows for different purposes), but worth a `dead_ends` entry so the
next session does not lose a cycle to it.

**The job fired twice unattended before I could disable it** — my manual trigger at 23:39 UTC, then
the standing `*/5 * * * *` cron at 23:45 UTC, both real firings, both completing before I read the
first one's result. Disabled immediately on noticing (`run_count: 2` at disable time); confirmed via
a sweep of all five projects' `/jobs` that nothing anywhere is enabled. Recorded rather than hidden:
this is exactly the "spends money all night" risk the queue names as the single most expensive
mistake available, and it cost two firings, not one, because watching and disabling are not the
same action and I did the first before the second.

**F52 (A) — found here, live, unstaged, and it is bigger than what Q4 went looking for.** Neither
of the two real `builder`/Haiku runs that fired could commit anything. Every git-touching tool call
across both runs was refused — `git add -A && git commit`, a PowerShell heredoc form, bare
`git config`, a Python `subprocess.run(['git', ...])` wrapper, a committed helper script, and even
a bare, single, read-only **`git --version`** — all with the identical Claude Code CLI message
"contains multiple operations... requires approval." 29 of 98 tool calls failed across the two
runs, 10 naming `git` explicitly. Traced to the database, not the transcript: zero
`permission_requests` rows and zero `permission_denied` events for either conversation, which means
`approve_tool_call` (`mcp_server.py`'s `_decide`, the "workspace" posture's own answerer) was never
invoked — and `_decide` is pure and total, unconditionally allowing any command with no absolute
path outside the workspace, so it would have said yes to all of these if it had ever been asked.
The refusal happens inside Claude Code itself, before the configured `--permission-prompt-tool` is
ever reached, with no row anywhere recording that it happened. Both agents worked around it by
declaring the task `completed` anyway — `task-3292072f63c3` and `task-bb86d53a94d5` both read
`completed` with zero commits and zero evidence, the code sitting only as uncommitted edits in
`aw-stress/.agentweave/worktrees/builder`. Neither agent used `ask_user` to escalate, though one
explicitly considered messaging a peer about it mid-transcript. Full write-up, the refusal table,
the two negative-result queries, and three unfixed candidate directions are under **F52** in
`scripts/drive/FINDINGS.md`. Left unfixed — this is severity A and foundational (it undercuts every
evidence/review/merge claim this drive has verified or will verify), but the existing queue
reserves severity-A fixes for a dedicated pass, and Q6 as currently scoped only names B/C from
Q1/Q2/Q4/Q5. Recorded in `decisions_for_user` below rather than unilaterally reordering the queue.

**What held.** `review_unstaffed` fired correctly after the first task completed: this loop has no
second agent to review its own work, and the scheduler recorded exactly why, once, rather than
silently proceeding or retrying every tick forever — a genuinely new case (no reviewer at all, not
merely one that is busy) handled the way `loop-becomes-a-flow`'s own `DECISION_IN_FLIGHT`/F48
reasoning intends.

**Q4's original target — not verified this iteration.** Neither run reached `submit_checkpoint_notes`
(both spent the turn fighting the permission wall instead), so no new `Checkpoint` row with a
non-null `loop_id` was produced live this session. The two checkpoints that already exist in the
database for `loop-e4b864459808` (`ckpt-a545dd785d8d`, ready/passed, author `builder`; and
`ckpt-9cba6c0e8e40`, failed/failed, author `critic` — the F50 sample) both predate this drive
(2026-08-24/25) and were generated by the change's own live verification, not by this run. **The
run-boundary hook remains covered only by that pre-existing evidence, unit tests, and code
reading — handoff 0088's residual-risk note stands.** The two `checkpoint_notes` still unconsumed
(`note-9a008b27abe3`, `note-e32be32d192c`, both `relay`) are also inherited, not fresh.

**What a reviewer should distrust:** the F52 root-cause hypothesis (Claude Code CLI classifying
`git` invocations as needing a confirmation no `--permission-prompt-tool` can satisfy, independent
of the "compound command" framing its own error text uses) is well-evidenced but not proven against
a controlled comparison — the CLI installed here is 2.1.238, newer than the 2.1.221 the Hub's own
code comments say the permission-prompt-tool contract was measured against, and no older build was
available to test against. Whether Codex-backed agents (`relay`, `gpt-5.4-mini`) hit the same wall
was not tested this iteration — Codex approvals route through `codex_appserver.decide_approval`
entirely, a different mechanism, so it is plausible this is Claude-CLI-specific; that is exactly
the kind of two-runner check this drive's own Q1 note insists on, and it did not happen here.

**Repository root** stayed untouched except `FINDINGS.md` and `STATE.json`/the log, confirmed by
`git status` before this commit.

**Decision for the operator**, recorded in `STATE.json`: F52 is severity A and foundational, but
the standing queue plan puts severity-A-from-Q4 fixing nowhere explicit (Q3 already closed, Q6 is
scoped to B/C). Absent a redirect, the next iteration will treat F52 as the priority fix ahead of
continuing further live drives that would otherwise inherit the same broken commit path.

**Next:** given F52's severity, the next iteration should either (a) attempt a fix for F52 with a
regression test and live re-verification (testing whether `relay`/Codex is also affected, and
whether an `--allowedTools` allow-list for `git add`/`git commit`/`git config` sidesteps the CLI's
own gate), or (b) if the operator has redirected via `decisions_for_user`, follow that instead.
Q4 itself stays open until the checkpoint hook gets a fresh live firing that actually reaches
`submit_checkpoint_notes` — worth retrying on `relay` specifically once F52's cross-runner question
is answered.
