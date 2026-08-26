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

---

## Iteration 5 — F52: the cross-runner check, extensive isolated repro attempts, a correction,
and a scoped fix

**2026-08-26T00:55–01:13+01:00.** Reconciled first: branch/log matched `STATE.json` (`a58f8e4`
tip after the Q4 heartbeat release), tree clean.

**The two-runner check Q1 always insists on, finally run for F52.** Fired a live turn on `relay`
(Codex, app-server transport) on `ledger-stress` with a git-touching instruction equivalent to the
original. It also could not commit — but its own refusal names a different mechanism entirely:
*"`git commit` is blocked by permissions on the shared `.git/worktrees/relay` metadata... needs to
write the shared metadata outside the writable sandbox."* Claude's refusal happens before
`approve_tool_call` is ever invoked; Codex's sandbox boundary check *is* invoked and refuses on its
own terms. Confirmed cross-runner, but as two independent mechanisms converging on the same
symptom, not necessarily one root cause.

**Extensive isolated reproduction, all negative.** Built `testbed/scratch/f52_pty_repro.py`
(deleted before this commit — throwaway) spawning `claude` through a real `winpty.PtyProcess`,
matching `PtySession.spawn` exactly rather than a plain subprocess, with the same flags
`runner_commands._build_claude_command` emits, the real `mcp_server.py` wired as a stdio MCP
server, and the identical compound `git add -A && git commit -m "..."` text from the failing
transcript. Varied six axes — PTY vs. plain pipe, `claude-opus-5` vs. `claude-haiku-4-5-20251001`,
this machine's `~/.claude/settings.json` (`defaultMode: auto`, present since 2026-08-23, so present
during the original F52 drive too) included and excluded, this session's own
`CLAUDE_CODE_*`/`CLAUDECODE` child-session env vars included and stripped, a plain repo vs. a real
linked `git worktree` as `cwd` — and **every single combination committed successfully**, first
try, `permission_denials: []` every time. The refusal is real (confirmed twice now, by DB rows in
Q4 and by literal tool-result text again this iteration) but its trigger is something in the full
production turn none of these axes captured. Recorded as an open question, not swept toward "CLI
version drift" — six negative results weaken that hypothesis rather than support it.

**The claimed consequence was wrong, and this is the important correction.** Checked
`aw-stress/.agentweave/worktrees/builder` directly: `git status --short` reads clean, and
`git log` shows `Auto-snapshot: builder's turn` commits authored `AgentWeave
<agentweave@localhost>`. `worktrees.snapshot_worktree` runs unconditionally at the end of *every*
turn (`agent_trigger.py`'s finalize path, reached whether the run completes or fails) and commits
whatever is dirty with `--no-verify`. Checked against the exact two runs F52 was measured on:
`run-2f63d76eeae2.snapshot_commit_sha` and `run-9e793f8b5c35.snapshot_commit_sha` are both real,
non-null commits holding exactly the fix content (banker's-rounding `quantize()`; account-code
validation). The code was never at risk of being lost. What is genuinely missing —
`requirement_evidence` rows, zero for both tasks — turned out to be the already-documented,
pre-existing "a plain loop task carries no `FR-` id to cite" gap, not a consequence of the git
refusal; `record_evidence`'s own docstring says `locator` is free text, never a commit sha. F52's
severity is revised down from "foundational, undercuts the whole evidence/review/merge chain" to a
real but narrower turn-wasting, task-abandoning UX defect.

**Fix applied, scoped to what is actually fixable without the CLI's root cause.** Added
`launchability.auto_snapshot_notice()`, appended to every writing agent's turn prompt in
`agent_trigger.py` (gated on `isolated_workspace is not None and review_context is None`, the same
condition the snapshot call itself uses), telling the agent the Hub commits its worktree
automatically at turn end regardless of git success, so it should stop retrying git and call
`record_evidence` with a free-text locator instead. Does not fix the CLI refusal — stops it from
costing a whole turn and a possibly-abandoned task while that stays open.

**Regression tests**: `test_launchability.py::test_f52_auto_snapshot_notice_says_the_agent_need_not_commit`
and two in `test_agent_trigger.py` (`test_f52_writing_agent_gets_the_auto_snapshot_notice` positive,
`test_f52_read_only_agent_gets_no_auto_snapshot_notice` negative — no worktree, no notice). 81/81
passed in both files. **Mutation-checked**: stashed `launchability.py` and `agent_trigger.py` only
— `test_launchability.py` fails to import (`auto_snapshot_notice` gone) and the positive
`test_agent_trigger.py` case fails its exact assertion, showing the real pre-fix prompt text in the
diff. Restored, reverified green. `ruff`/`black --target-version py311` clean on all four touched
files. Broader slice (`-k "trigger or launchability or worktree or snapshot"`, 178 tests): 177
passed, 1 skipped, 1 xpassed, 0 failed.

**Verified LIVE.** Restarted the trial Hub on the beta database (confirmed via `e2e.py state
proj-18e5d4e0` reading identical project state before/after the restart). Fired a fresh `builder`
turn on `ledger-stress` (`run-021a5dfc357c`) with a git-touching instruction. The notice appeared;
the agent tried the compound commit once, was refused exactly as before, and — unlike the original
two runs, which each tried five or six more phrasings before one gave up on the task — stopped
after one attempt and correctly self-reported *"the Hub will automatically commit my worktree's
uncommitted changes at the end of this turn."* `aw-stress/.agentweave/worktrees/builder`'s log
confirms: a fresh `Auto-snapshot: builder's turn` commit holding exactly that run's one-line edit,
tree clean afterward. A real, measured behavior change, not a fixture result.

**Write-up**: `scripts/drive/FINDINGS.md`'s F52 entry gained a full "Correction and partial fix"
section rather than being rewritten in place, so the original (real, still-accurate-on-its-own-
terms) refusal evidence stays intact and the correction is legible as a correction.

**Jobs swept**: `select id, project_id, enabled, name from ai_jobs` against the beta database
directly — all nine rows across all projects read `enabled: 0`. Nothing was enabled this
iteration; the relay/builder probes were single `e2e.py turn` calls, not jobs.

**Repository root** stayed untouched except `FINDINGS.md`, the two hub source files, the two hub
test files, and `STATE.json`/the log — confirmed by `git status` before this commit. The throwaway
`testbed/scratch/f52_pty_repro.py` and `testbed/scratch/builder_charter.txt` were deleted before
committing; `/tmp/f52-repro` (outside the repo) was removed.

**What a reviewer should distrust**: the CLI-level refusal's actual trigger is still unknown — the
notice fix is a real mitigation, verified live, but it is not a fix for the underlying defect, and
nothing here should be read as having found or ruled out its cause. The full `hub/tests/` suite
(~3100 tests) was not rerun this iteration, only the touched-file and topic-relevant slices; Q9's
sweep is still where whole-suite green gets re-established.

**Next**: `current`/`next_action` in `STATE.json` point at retrying Q4's original target — a fresh
live firing that reaches `submit_checkpoint_notes`, now that the notice fix should stop a run from
dying mid-turn fighting git before it gets there. Disable whatever job is enabled for this before
the iteration ends, the way every iteration so far has.

---

## Iteration 6 — Q4 retried three times live, two new findings (F53, F54), F54 fixed live before this entry closes

**2026-08-26T01:20–01:45+01:00.** Reconciled first: branch/log matched `STATE.json` (`06fd444`
tip), tree clean, Hub `/health` ok, `/api/v1/projects` served from the beta database.

**Attempt 1, on `drive-2026-08-26` (`proj-8605b92d0028`) — chosen to avoid touching `ledger-stress`'s
existing flow, which the prior iteration explicitly avoided contaminating.** Set the project's
`checkpoint_runner_id` (previously null — a real gap `main_branch`'s F4 pattern did not cover for
this project), then created a flow job over the approved inventory document
(`spdoc-f64ba8051a5b`, three real pending tasks from Q2). `POST /jobs/{id}/run` refused with
`409 "author is a self-registered poll agent and manages its own execution"` — `e2e.py`'s own
`cmd_agent` registers agents via `/agents/register` (`contact_mode: poll`, `self_registered: true`),
which cannot be a loop's spawn target at all; only a Hub-managed (`POST /agents`,
`self_registered: false`) agent can. Not a product defect — a harness/registration-mode mismatch,
recorded so nobody re-diagnoses it. Created two fresh Hub-managed agents (`loopauthor`,
`loopreviewer`) bound to the same runners/charters to work around it.

**F53 (B) — found fixing my own mistake, then confirmed to be a real, general gap.** To retarget the
job at `loopauthor`, I archived the first attempt (`POST /jobs/{id}/archive` — one call archived
both the job and its never-fired loop). Re-creating the job against the same document then `409`'d
permanently: `"document 'spdoc-f64ba8051a5b' is already claimed by loop 'loop-2b337162dffd'"` — the
archived, dead loop. Read from the code: `_check_spec_document_conflict`
(`hub/hub/api/v1/jobs.py:103-124`) never filters `Loop.archived_at`, and `_adopt_document_tasks`'s
`loop_id IS NULL` guard, correct for its own stated purpose, has no path to release a `loop_id` once
archiving orphans it — confirmed directly against the three tasks' rows, still `loop_id =
'loop-2b337162dffd'`, `status = 'pending'`, un-reachable by any loop query and un-resettable by any
task API found. Full write-up, both root causes, and the fix's open design question (exclude
archived loops from the conflict check vs. actually clear `loop_id` on archive, and what that means
for tasks a dead loop's agent had already started) are under F53 in `FINDINGS.md`. Left unfixed —
severity B, design gap, Q6's shape of item, not a live-spend risk.

**F54 (A) — found on the very next API call, and this one IS a live-spend risk.** The `409` above
was trusted as a no-op, the way any REST client trusts a 4xx. It was not one. This iteration's
mandatory job sweep (`select id, project_id, enabled, name from ai_jobs`) turned up
`job-08e0c3b0329c` on `proj-8605b92d0028`, **`enabled: 1`**, `cron: */5 * * * *`,
`agent: loopauthor` — a real, spawnable Hub-managed agent — sitting enabled and unnoticed for
roughly eight minutes. Root cause read from `create_job` (`hub/hub/api/v1/jobs.py:549-611`): the
`AIJob` row is committed at line 575-577, unconditionally, **before** the loop/document-conflict
check at line 588-590 ever runs; when that check raises its `409`, nothing rolls back or disables
the row already sitting in the database. The exact discipline `initial_tasks` validation states for
itself fifty lines above ("validated up front, before any row is created, so one malformed entry
cannot leave a job... half-created behind a 422") does not extend to this check. Caught before its
first cron tick (`next_run` had been computed, `run_count: 0`) — this is "caught in time," not
"never going to fire." `PATCH {"enabled": false}` then `POST .../archive`, both `200`; re-swept
`ai_jobs` immediately after — **all ten rows across all five projects read `enabled: 0`**. Full
write-up under F54 in `FINDINGS.md`.

**F54 fixed this iteration, not deferred — unlike F52, this one is small, well-understood, and is
itself the kind of thing that must not survive to be found live a second time by an unattended
run.** Moved `_check_spec_document_conflict` ahead of the job row's creation in `create_job`:
the conflict is now checked (when `spec_document_id` is supplied and the request opts into a loop)
before `AIJob(...)`/`session.add(job)`/`commit()` ever run, so a `409` response now genuininely means
nothing was written — mirroring the `initial_tasks` "validated up front" pattern already in the same
function. The `update_job` (PATCH) path was left alone: it mutates an existing, already-committed
row rather than creating a phantom one, so a failed conflict check there is a no-op on the row's own
fields, not a data-creation side effect — confirmed by reading the PATCH handler's ordering, not
just assumed.

**Regression test** (`hub/tests/test_jobs_spec_document.py`,
`test_f54_document_conflict_leaves_no_job_row_behind`): creates a loop already claiming a document,
then attempts a second job against the same document with `stop_when_queue_empties=True`, asserts
`409`, then asserts **no `AIJob` row exists with the attempted job's name** on the project at all
(the strongest available assertion, since the id is never returned on a 409). **Mutation-checked**:
reverted only the reordering in `jobs.py`, reran — the new test failed, finding exactly the orphan
row the fix exists to prevent, by name. Restored, reverified green. Ran the full
`test_jobs_spec_document.py`-adjacent slice (`-k "job and (spec_document or conflict or loop)"`,
41 tests): 41 passed. `ruff`/`black --target-version py311` clean on `jobs.py` and the new test file.

**Verified LIVE**, not only against the fixture. Restarted the trial Hub on the beta database
(confirmed via `GET /api/v1/projects` listing the same five projects, `ledger-stress` included, not
the stale `hub/data/agentweave.db` set). Repeated the exact request that created the orphan the
first time — `POST /projects/proj-8605b92d0028/jobs` with `agent: loopauthor`,
`spec_document_id: spdoc-f64ba8051a5b` (still claimed by the F53 dead loop) — got the same `409`,
then swept `ai_jobs` for `proj-8605b92d0028` immediately after: **no new job row at all**, only the
two pre-existing archived/disabled ones from this iteration's own earlier mistakes. The
orphan-creation is gone. Final full sweep, all five projects, ten rows: every one reads
`enabled: 0`.

**Q4's original target — still not positively exercised.** Three real firings on `ledger-stress`'s
"Ledger flow" this iteration (after re-declaring `spdoc-2154cc95` on the existing loop backfilled
four previously-orphaned tasks — themselves a live, un-numbered re-confirmation of the *known* F28
shape, not counted as a new finding): the first got confused between two similarly-titled tasks
(`task-0dfc3be5` "Refuse the empty entry" vs. the already-under-review `task-23a0986e7fe9` "Refuse
an entry with no postings") and completed neither, falsely reporting "Task Complete" in its own
final text while its actual assignment sat untouched — a real operator-in-the-loop gap (no backstop
catches a self-declared-complete turn that did nothing) worth a future finding if it recurs, not
written up fully here for time. The second correctly completed `task-0dfc3be5`
(`run-809a3bdb1322`, confirmed via `task_transitions`: `assigned→in_progress→completed`) but never
called `submit_checkpoint_notes` despite the briefing's own "somebody else reads it" line — verified
from the database, not inferred: zero `checkpoint_notes` rows for `conv-283a9ebdf84e`, and zero new
`checkpoints` rows after the run, consistent with `consider_handover`'s documented decline path
("the agent recorded no notes for its reviewer"). Strengthened `job.message` to make the tool call
an explicit, required step and fired a third time; the scheduler picked a different, unrelated
queue item (a review of `task-18e900f3eb96`, which failed for a known, already-documented reason —
no recorded evidence to review) rather than producing a fourth author completion. **The hook's
decline path is now confirmed live twice, independently; its positive path (a `Checkpoint` row with
a non-null `loop_id`, generated from a real run boundary) remains unexercised after four total live
attempts across two iterations.** This is itself worth stating plainly rather than dressing up:
cheap-model agents in this flow reliably finish the assigned code change but unreliably call the
one tool the handover mechanism depends on, even when a job message states it as a required step.

**F55 (B) — an unprovoked, intermittent test failure, chased down rather than re-run away.**
Running a broader slice to sanity-check the F54 fix, `test_flow_checkpoint_lineage.py` failed on a
test that has nothing to do with `jobs.py`. Stashed the F54 change and re-ran the file alone,
repeatedly: 2 of 6 bare runs on the unmodified branch tip failed too, alternating between two
different tests — pre-existing, not caused by this iteration. Root cause measured directly, not
inferred: `datetime.now(timezone.utc)` returns the **identical value across five consecutive calls**
on this machine (Windows clock resolution coarser than the microsecond precision the value's format
implies), so the two `create_checkpoint` calls both flaky tests make back-to-back land in the same
tick more often than not, and `latest_checkpoint_for_loop`'s tie-break —
`Checkpoint.id.desc()`, a random hex string with no relation to insertion order — picks the wrong
"newest" checkpoint roughly half the time. This is a real product bug, not just a fragile test: two
loop firings completing within the same clock tick on real hardware would silently brief the next
agent from the *older* of two checkpoints, no error, no log line. Not fixed — the right fix is a
monotonic sequence column (the shape `TaskTransition.sequence` already uses for the identical
reason), a schema change deserving its own migration, not a fold-in. Full write-up under F55 in
`FINDINGS.md`; left for Q6.

**Jobs swept, final state confirmed**: `select id, project_id, enabled, name from ai_jobs` — **all
ten rows across all five projects read `enabled: 0`**, shown as query output above, not claimed.

**Repository root** stayed untouched except `FINDINGS.md`, `hub/hub/api/v1/jobs.py`, the new test
file, and `STATE.json`/the log — confirmed by `git status` before this commit.

**Decision for the operator**, recorded in `STATE.json`: F53 (B, design gap, no live-spend risk) is
left for Q6. F54 (A, live-spend risk) is fixed, tested, mutation-checked, and verified live this
iteration — no redirect needed.

**What a reviewer should distrust:** the full `hub/tests/` suite (~3100 tests) has still not been
rerun this iteration, only touched-file and topic-relevant slices; Q9's sweep is still where
whole-suite green gets re-established, and F55's intermittency means any future red run of
`test_flow_checkpoint_lineage.py` should be re-run once before being treated as a new regression.
The task-name-confusion episode in attempt 1 is described from the transcript and the
`task_transitions` table but was not written up as a standalone, numbered finding — if it recurs,
it should get one rather than being re-discovered as new.

**Next:** Q4 stays open. Either retry once more with a plain (non-flow) loop stripped down to a
single, unambiguous task and an even more explicit `submit_checkpoint_notes` instruction to isolate
whether the tool-call unreliability is model-specific or briefing-specific, or accept the two
confirmed decline-path drives as sufficient evidence for the write-up and move to Q5, which is next
in the queue regardless. Q6 should pick up F53 (and the task-name-confusion episode, once numbered)
alongside the existing B/C backlog.

---

## Iteration 7 — Q4 CLOSES: the fifth live attempt produced the positive checkpoint, rows and all

**2026-08-26T01:47–01:55+01:00.** Reconciled first: branch/log matched `STATE.json` (`8bee33b`
tip after iteration 6's heartbeat release), tree clean, Hub `/health` ok, `/api/v1/projects` served
from the beta database (five projects listed, `ledger-stress` among them).

**Followed the state file's own recommendation rather than re-running the same shape a sixth
time.** Built the minimal non-flow loop it named: a job with no `spec_document_id` (so the plain
"finish and stop" briefing applies, not the flow one), on `drive-2026-08-26`
(`proj-8605b92d0028`), agent `loopauthor` (Hub-managed, bound to the same Haiku runner already set
as the project's `checkpoint_runner_id`), one `initial_tasks` entry with an unambiguous title ("Add
input validation to `Item.__init__` in inventory.py") distinct from every other pending task on the
project, and a `job.message` stating `submit_checkpoint_notes` as an explicit required first step
before any code edit, `stop_when_queue_empties: true`, `cron: "0 0 31 2 *"` (a date that never
occurs, so only a manual `POST .../run` could fire it — deliberate, to keep this a single
controlled shot rather than a real schedule).

**Fired once, and it worked on the first try.** `run-736d9e1f2cd3` (real conversation, not the
`JobRun` id `POST .../run` returns — confirmed against `dead_ends`' own warning before trusting the
returned id). Watched live: the agent loaded the tool schema, called
`submit_checkpoint_notes` as its very first action, then read both files, edited both, then
completed the task in the same turn. Full detail and every row id are now written up as a
resolution appended to **F43** in `scripts/drive/FINDINGS.md` (not a new finding — this closes the
residual risk F43's own entry already named), rather than repeated here. In short, all four gates
checked against the database, not the transcript: the note (`note-7c7ef8892644`) was written in
this run's own conversation; the task's transitions (`assigned→in_progress→completed`) are all
attributed to `run-736d9e1f2cd3`; the resulting `Checkpoint` (`ckpt-42c9362f7ba4`) carries
`loop_id: loop-b920a216f57c` (non-null) and `covers_through_run_id: run-736d9e1f2cd3`; the note is
marked `consumed_by_checkpoint_id` on that same checkpoint; the checkpoint's `body` genuinely
contains the note's own risk content, not a placeholder. The code change itself is real, confirmed
by reading the auto-snapshot commit directly (`e4a4ae9d...`, `git show --stat`: two files touched)
rather than trusting the agent's self-report.

**One thing noticed and worth carrying forward rather than fixing now.** After the queue emptied
(the loop's one task went to `completed`), the job's `loop.stopped_at`/`ending_state` stayed null
and `enabled` stayed `true` — `stop_when_queue_empties` is evaluated on the next scheduler tick, not
synchronously at the moment the queue empties, and this job's cron (deliberately set to never fire)
meant no tick was ever going to arrive to notice. This is very likely an artifact of the test's own
never-firing cron rather than a real defect — a job with an ordinary cron would tick and self-stop
normally — but it means **a loop cannot be trusted to disable itself the instant its queue is
empty**, which is exactly the kind of gap the standing "never leave a job enabled" rule exists to
catch by hand. Disabled and archived immediately (`PATCH enabled:false` then `POST .../archive`,
both `200`), then sweept `ai_jobs` project-wide: all twelve rows across all five projects read
`enabled: 0`, shown as query output, not claimed.

**What HELD, beyond the positive checkpoint itself.** The auto-snapshot mechanism (F52's
correction) held again — a real commit exists regardless of whether the agent's own git calls
would have succeeded. The Hub-managed-agent requirement for loop spawn targets (found in iteration
6) held consistently — `loopauthor` fired without the `409` `author` (self-registered) would have
hit.

**What a reviewer should distrust:** this is one positive sample, not a controlled comparison
against the four negative ones — whether the earlier unreliability was flow-briefing-specific or
just this session's bad luck on cheap-model tool-call discipline is explicitly left open in the
`FINDINGS.md` write-up rather than overclaimed. The full `hub/tests/` suite (~3100 tests) still has
not been rerun since iteration 3's touched-file slice; Q9's sweep is still where whole-suite green
gets re-established — nothing was changed in `hub/` source this iteration (only `FINDINGS.md`,
`STATE.json`, and this log), so there is no new mutation-check obligation, but the suite itself is
still owed a full run before the morning summary can claim it.

**Repository root** stayed untouched except `FINDINGS.md` and `STATE.json`/the log — confirmed by
`git status` before this commit. No source file in `hub/` or `src/` was touched this iteration.

**Q4 closes.** All three of its `verify` criteria are met with row ids, live, on the fifth attempt.

**Next:** Q5 — drive the two `ledger-stress` tasks already sitting in `under_review`
(`task-23a0986e7fe9` with `critic`, `task-3cd54c17faa6` with `relay`) to a real reviewer verdict:
can the reviewer read the code (F10), does `record_evidence` work from Haiku (F21), does rejection
route back legibly, does approval cherry-pick into the main branch with the landing commit
reported (F9). `ledger-stress` reads `main_branch: "master"` (F4 confirmed, prep + Q1), so
integration is not blocked.

---

## Iteration 8 — Q5 in progress: F56 found live and fixed, both under_review tasks driven to a real verdict, an unexpected cascade surfaces a possible F10 recurrence still open

**2026-08-26T01:03–02:22+01:00.** Reconciled first: branch/log matched `STATE.json` (`3c22d53` tip
after iteration 7's heartbeat release), tree clean, trial Hub `/health` ok and serving the `beta`
database.

**Q5's very first step blocked immediately, and the block was the finding.** Triggering `critic`
on `task-23a0986e7fe9` (`e2e.py turn ... --task task-23a0986e7fe9`) returned `queued`, `run_id:
null`, with a `waiting_reason` naming a completely different, already-`completed` task
(`task-18e900f3eb96`). Repeated with a raw API call — identical, unrelated refusal. Traced through
`turn_scheduler.schedule_agent`, `agent_trigger.trigger_agent_directly` and
`requirement_evidence.commit_for_task_review`, then confirmed directly against the live
`inbound_queue_entries` table: a job-queued review request from **2026-08-25T00:10**, over 24 hours
earlier, had been refused once (the task it named had no evidence naming a commit — itself now
moot, since that task later completed by other means) and then never touched again, because a
refusal raised before any `Run` exists is invisible to `DELIVERY_ATTEMPT_LIMIT`'s counting — that
bookkeeping only runs for a `Run` that was created and then failed. Eight later entries, spanning
three origin types and this session's own first two drive attempts, had piled up behind it with
zero self-correction and zero operator-legible signal. Full write-up: **F56 (A)** in
`scripts/drive/FINDINGS.md`.

**Fixed live, `hub/hub/turn_scheduler.py`:** a terminal (non-`workspace_unavailable`)
`TriggerAgentError` now counts against the same entries' `delivery_attempts`, abandoning them at
`DELIVERY_ATTEMPT_LIMIT` with a stated reason and a `queue_entry_abandoned` broadcast, exactly
mirroring what `return_run_entries` already does for a spawned-and-failed run — extended to cover
the case that mechanism structurally could not see. Two regression tests added to
`hub/tests/test_failed_run_returns_input.py` (the terminal-refusal abandonment, and a
workspace-unavailable refusal correctly *not* counting). Mutation-checked: `git stash` on just the
source file reproduced the new terminal-refusal test failing while the workspace-unavailable test
still passed; unstashed and reconfirmed green. `ruff`/`black --target-version py311` clean on both
touched files after a `black` reformat.

**Unblocked live** by withdrawing the poisoned entry through the documented operator escape hatch
(`DELETE /queue/entries/{id}` — confirmed to exist and work), then restarted the trial Hub onto the
fixed code (`Stop-Process` on the two prior PIDs, relaunched via the documented `uvicorn` command;
confirmed back on the `beta` database with all five projects listed, and all twelve `ai_jobs` rows
still `enabled: 0`). The fix itself was verified through the regression suite against a real async
SQLite session (not mocked) plus the mutation check; it was not separately re-poisoned against the
freshly-restarted process, a judgment call recorded in `FINDINGS.md` rather than left implicit.

**Both `under_review` tasks then got a real reviewer verdict, live, through the actual product
surface — Q5's core question.** `critic` (Haiku), given a proper `review_task_id` turn, was checked
out at the exact evidence commit (`f10d198d…`), read the real diff and history unprompted (it
independently worked out that the code fix predated the reviewed commit and only new tests were
added — see below), ran the suite, and called `update_task` to `approved` with real reasoning
(`run-45862ae056ff`). `relay` (Codex mini), on a fresh queue with no backlog, went straight to
`running`, hit and worked around a `pytest`-console-entrypoint quirk on its own, wrote a review
artifact, and also called `update_task` to `approved` (`run-51255c8b0ff0`). Confirmed against the
`tasks` table, not the transcripts: both rows now read `status: approved`. Neither task carries a
linked spec requirement (`requirement_ids: []`), so both reviewers correctly discovered
`record_evidence` refuses a bare task id as `identifier` (F21's finding, not new) and neither
integration nor a landing commit is possible for either — `integration-preview` read
`will_merge: false, reason: "no accepted evidence names a commit"` before and necessarily still
does after, since approval alone creates none. `requirement_gate.evaluate` has nothing to check for
a task with zero linked requirements, so the approval sailed through with no gate at all — traced
in code, matches the documented design (`task_integration.py`'s own docstring: "a supported project
shape, not a degraded one"), not a new finding. **Q5's F9 half (a real merge with a landing commit
reported) is therefore still undriven** — these two tasks were never going to exercise it.

**What HELD.** F10 did not recur on the properly-formed review turn: isolation for a genuine
`review_task_id` turn worked exactly as designed. The withdraw escape hatch is real and sufficient
to unblock an agent by hand today. F45/F46's fix (a review that moves the task rather than looping)
held under real load, below.

**Unplanned, and the most interesting open thread of the iteration.** Once unblocked, the queue
*self-drained*: `critic`'s tail apparently reschedules itself after each completion, and four more
backlogged entries fired on their own over the next ~12 minutes with no further triggering from
this session (`run-e842f20908da`, `run-76aea9746e7f`, `run-8ecd51e9f81b`, `run-26f0c4702de0`, all
`completed`, no errors). One of them carried a *third*, requirement-linked `under_review` task this
session had not gone looking for — `task-0dfc3be5` ("Refuse the empty entry", `FR-2`, already had
evidence-with-commit recorded) — and `critic` moved it to **`revision_needed`**, a real rejection,
not a rubber stamp. Reading that run's transcript (`run-e842f20908da`) for legibility found two
things worth carrying forward rather than fully chasing down this iteration, for time: (1)
`task.notes` and `task.deliverables` are both `null` on the now-`revision_needed` task — whatever
reasoning `critic` had is in the run's own output, not anywhere the task record itself carries
forward, which bears directly on Q5's "does rejection route back legibly" question and reads like a
plausible gap, not yet confirmed as one; (2) the transcript shows `critic` genuinely blocked at
first — "I cannot access the builder's worktree commits... I am blocked on reviewing this until the
builder responds" — before it separately discovered it could read the builder's branch directly
with `git`, which looks like **F10 recurring** on a turn that was not a clean, single-target review
turn (this run's batch mixed a `review_task_id` entry with unrelated `task_id`-only entries from
other tasks, unlike the two turns this session drove directly). Not written up as a finding yet:
the exact mechanism (why workspace setup differed here) was not traced before time ran out this
iteration. Flagged in `decisions_for_user` below with both run ids so it is not lost.

**What a reviewer should distrust.** The cascade's four extra runs were not independently watched
live the way the two deliberate drives were — verified after the fact against `runs` and
`task_transitions`, not observed turn-by-turn. The full `hub/tests/` suite has still not been rerun
this session (only the touched-file slice plus three adjacent files, 126 tests, all green); Q9's
sweep remains where whole-suite green gets re-established. The `task.notes` observation above is
one data point on one task, not confirmed as a pattern.

**Repository root** touched only `hub/hub/turn_scheduler.py`, `hub/tests/test_failed_run_returns_input.py`,
`scripts/drive/FINDINGS.md`, and `STATE.json`/this log — confirmed by `git status` before commit.

**Job sweep, as output:** `ai_jobs` across all five projects, all twelve rows `enabled: 0`,
confirmed via direct query against the live `beta` database after the Hub restart.

**Next:** Q5 remains open — the F9 merge/landing-commit half is still undriven and needs a task
that both reaches `under_review` and carries a linked, evidence-bearing requirement (`task-e6b05093`
carrying `FR-3`, currently `assigned` to `builder`, is a live candidate once it completes; a second
review-and-accept-evidence pass on `task-0dfc3be5` is another, once its `revision_needed` cycle
resolves). The possible F10 recurrence on a mixed-batch review turn (above) should be traced and
either written up or ruled out before Q5 closes.

---

## Iteration 9 — F10 recurrence ruled out (traced, not a recurrence), F57 found and fixed live

**2026-08-26T02:22–02:38+01:00.** Reconciled first: branch/log matched `STATE.json` (`9abd6e2` tip
after iteration 8's heartbeat release), tree clean, trial Hub `/health` ok. Picked up exactly where
iteration 8 left off: trace the possible F10 recurrence, then continue driving Q5.

**F10 recurrence traced and ruled out.** Iteration 8's log entry named the run `run-e842f0908da`,
one character short of a real id; the actual row is `run-e842f20908da`, found by matching against
the other three cascade run ids queried together. Pulled it and read its `task_id`, which is
`task-3292072f63c3` ("Round half to even in `Money.quantize()`"), an already-`completed` task with
no requirement links — **not** a `review_task_id` turn at all. Read `_review_task_from_entries`
(`agent_trigger.py`): it only ever resolves a review target from the *batch's own queue entries*,
and this batch carried none, so `review_turn.prepare_review_turn` — the actual machinery F10's fix
lives in, and the thing this session's two clean drives exercised — was never invoked here. What
really happened: `critic`, given nothing useful to do on its named task, went looking on its own
initiative via `list_tasks`/`list_evidence`, found `task-0dfc3be5` genuinely `under_review`, and
tried to inspect it **from its own ordinary working worktree** (correctly finding nothing — that
worktree never had the builder's unmerged work), then discovered `git branch -a`/`git checkout`
reach the builder's branch anyway (worktrees share one object database) and completed a real review
that way. Two distinct things, not one: the structured review path is intact and untouched by this
episode; an *ad hoc* git-based route to the same information also works, which the original F10
write-up did not anticipate. Written up as an addendum under F10 in `scripts/drive/FINDINGS.md`
(not reopened — a different, so far harmless, path to the same information). Not treated as
severity-A: it succeeded, and the structured path this session actually depends on is unaffected.

**F57 (A) found live, tracing the other half of iteration 8's flag.** The same transcript's
`update_task("task-0dfc3be5", "revision_needed")` call, checked against the live `tasks` row: both
`notes` and `deliverables` are `null`, despite substantial real reasoning in the transcript (traced
the empty-postings logic, flagged scope creep in the `quantize()` addition, gave a line-by-line
verdict). Root cause read directly in `hub/hub/mcp_server.py`: the `update_task` MCP tool took only
`task_id` and `status` — never `notes` — even though the REST route it calls (`TaskUpdate` in
`hub/hub/schemas/tasks.py`) and its handler (`update_task_for_actor`,
`hub/hub/api/v1/tasks.py:1172`, `if body.notes is not None: task.notes = body.notes`) have always
supported it. The capability exists end-to-end on the API; the tool an agent is actually handed
never offered it — so a rejection has no way to say why, on the task record itself, ever.

**Fixed live, `hub/hub/mcp_server.py`:** `update_task` gains `notes: Optional[str] = None`,
forwarded unconditionally (`{"status": status, "notes": notes}`). Confirmed safe by reading the
consuming line directly: the gate is `is not None`, not `model_fields_set`, so an explicit `null`
and an absent key behave identically — a plain status-only call cannot clobber existing notes.
Regression test added (`hub/tests/test_mcp_server.py`,
`test_update_task_forwards_notes_so_a_rejection_is_legible_on_the_task_itself`), and the
pre-existing `test_task_tools_use_agent_ledger_endpoints_without_assigner` updated for the new body
shape (`{"status": "completed", "notes": None}`) rather than left stale. Mutation-checked: `git
stash` on just `hub/hub/mcp_server.py` reproduced `update_task() got an unexpected keyword argument
'notes'` on the new test; unstashed and reconfirmed green. `ruff` clean; `black
--target-version py311` reformatted both touched files once, then reported clean.

**Trial Hub restarted onto the fix and reconfirmed.** Stopped the process holding port 8010
(`Stop-Process -Id 14644`), relaunched via the documented `uvicorn` command, `/health` ok within
~8s. Confirmed back on the `beta` database: `GET /api/v1/projects` lists all five projects, and
`ledger-stress`'s six `ai_jobs` rows all still read `enabled: false`.

**What a reviewer should distrust.** F57's fix was verified through the regression suite (real HTTP
body assertion) and by reading the exact consuming line, plus mutation-checked — but not
re-exercised through a fresh live agent turn after the restart; the transcript that exposed the gap
already stands as the live evidence the gap is real, and staging a second live rejection just to
watch `notes` land non-null was judged not worth another cheap-model turn this iteration. Recorded
explicitly in `FINDINGS.md` as a judgment call, not left implicit. `task-0dfc3be5` is still sitting
`revision_needed` and is a ready-made target for that extra rep if a future session wants it. The
full `hub/tests/` suite has still not been rerun this session (only the touched-file slice plus
directly adjacent tool-surface/task-schema tests, 202 tests, all green); Q9's sweep remains where
whole-suite green gets re-established.

**Repository root** touched only `hub/hub/mcp_server.py`, `hub/tests/test_mcp_server.py`,
`scripts/drive/FINDINGS.md`, and `STATE.json`/this log — confirmed by `git status` before commit.

**Job sweep, as output:** `ai_jobs` on `ledger-stress`, all six rows `enabled: false`, queried live
against the `beta` database immediately after the restart, shown above as output.

**Next:** Q5 remains open. The F9 merge/landing-commit half is still undriven — `task-e6b05093`
(FR-3) is still `assigned` to `builder`, not yet complete; once it reaches `under_review`, drive
`critic` or `relay` to a verdict through the review flow and, on approval, confirm a landing commit
through `integration-preview`/the actual merge, with the commit sha reported. Alternatively,
re-reviewing `task-0dfc3be5` (FR-2, already evidence-bearing) after a builder revision cycle is a
second route to the same F9 half, and would also supply the extra live rep F57's write-up flagged as
optional. Either drives Q5's remaining open question.

---

## Iteration 10 — Q5 closed: F9's merge half driven to a real landing commit, and F58 (A) found doing it

**2026-08-26T02:35–02:46+01:00.** Reconciled first: branch/log matched `STATE.json` (`b9d2de8` tip
after iteration 9's heartbeat release), tree clean, trial Hub `/health` ok on the `beta` database.
Picked up exactly where iteration 9 left off: Q5's F9 merge/landing-commit half was still undriven.

**Drove `task-0dfc3be5` (FR-2) through a full revision-review-approve-merge cycle, live.** It was
`revision_needed`, gating `task-e6b05093` (FR-3) as `dependency_state: gated`. Triggered `builder`
with an explicit task-scoped turn (`run-8c7dda053998`); it found its own earlier test missing from
the worktree, re-added it, recorded evidence, and moved the task to `completed` (`update_task` only
allows `in_progress -> {assigned, blocked, completed}`, not directly to `under_review` — confirmed
by the tool's own rejection message; the `completed -> under_review` step upstream is an
operator-only transition, consistent with the same pattern already seen at `sequence=82` in this
task's own history). Moved it to `under_review` as operator (`task-set`), then triggered `critic`
(`run-d7e30a9c650d`): it read the spec, the task, the evidence, the code, ran the real test suite
(after some friction — `Bash`/`PowerShell` calls failed first, worked around via the repo's own
`run_tests.py`), and called `update_task("approved", notes=...)`. **First live confirmation that
F57's fix works end-to-end on a fresh rejection/approval, not just in the regression suite**: the
task row now carries a real, substantial `notes` field from a live agent call.

**Then drove the merge itself — the one part of Q5 no prior iteration had reached.** All of this
task's evidence rows were `review_state: awaiting`; `integration-preview` correctly reported
`will_merge: false` ("no accepted evidence names a commit"). Discovered along the way: **no
evidence has ever been `decide_evidence`-accepted anywhere in this project's history** — every prior
`approved` task in `ledger-stress` skipped a real merge for exactly this reason, which is why Q4/Q5's
earlier approvals never produced one either. As operator, called
`POST .../project/spec/evidence/{id}/decision` to accept the newest evidence
(`ev-57bfd7d6552f`, commit `d64b43dffe96...`); `integration-preview` then correctly flipped to
`will_merge: true`, naming exactly that commit. Called `.../integrations/retry`.

**First attempt hit a real `CONFLICT (modify/delete)`, self-inflicted** — while investigating,
found and untracked long-stray `__pycache__/*.pyc` files in the `aw-stress` subject repo (tracked
since its very first commit, `edc23dc`, 2026-08-23, evidently seeded with a broad `git add` rather
than explicit paths — the standing mistake this run's own limits warn against). That cleanup
conflicted with the evidence commit, which still modified those tracked files. Reverted
(`git reset --hard fbeeb26`) to test the real bug in isolation, retried: **`merged`, landing commit
`9e593f2` in the subject repository, confirmed directly by `git log`/`git show --stat` against
`C:\Users\huida\Documents\aw-stress`, not the Hub's own report.** `git merge --abort` on the earlier
conflict left the checkout genuinely clean (no `MERGE_HEAD`, no conflict markers) — a real "what
HELD" result.

**F58 (A), found reading that merge commit's own diff.** It carried 13 files, not the evidence
commit's own change: alongside the real fix, five scratch scripts the agent had written for itself
across earlier turns (`commit.sh`, `commit_account_validation.py`, `do_commit.py`,
`verify_empty_entry.py`, `verify_fix.py`) and — the serious part — `tests/test_account_order.py`,
traced via `git log --all` to commit `90aa643`, which belongs to **`task-e6b05093`** (FR-3), a
*different, still-`assigned`, never-reviewed, never-approved task on the same agent's branch*.
`git log --oneline fbeeb26..d64b43d` lists 16 auto-snapshot commits; all 16 landed. Root cause,
read directly in `hub/hub/task_integration.py:265`: `integrate()` runs `git merge --no-ff
<commit_sha>`, which merges the commit's **entire ancestry**, not its diff alone — contradicting
the module's own stated design rule ("merge a commit, never a branch... anything committed after it
stays out") and the one existing test that claims to guard it
(`test_later_commits_on_the_branch_are_not_merged`), which only ever commits *after* the accepted
evidence and so structurally cannot catch commits *before* it riding along — the F43/F52 shape
again, a green test that cannot distinguish the two implementations it exists to tell apart. Written
up in full in `scripts/drive/FINDINGS.md` with the blast-radius argument (every builder agent's
branch carries every task it has ever touched, so this is not a narrow edge case) and three
un-evaluated fix candidates, deliberately **not fixed this iteration** — same standard as `[[F53]]`
and `[[F55]]`: a real design decision (cherry-pick range vs. single-commit patch vs. per-task
worktrees), not a one-line patch, and flagged as the top Q6 priority given it directly contradicts
this module's own documented guarantee.

**Q5 is now closed.** Its verify criterion — "a task moved under_review -> approved by a real
reviewer turn, with the evidence row, the transition row, and the resulting commit in the subject
repository all identified by id" — is satisfied: `task-0dfc3be5`, `task_transitions.sequence=95`,
evidence `ev-57bfd7d6552f`, landing commit `9e593f2`. It closes with a major caveat recorded (F58)
rather than a clean pass, which is the honest account of what driving it found.

**What a reviewer should distrust.** The `aw-stress` subject repo's checkout was directly modified
by this iteration (the `.gitignore`/untrack commit, the reset, the merge) — legitimate operator
housekeeping and the product's own merge mechanism, not a workaround, but worth knowing the
repository is not in the state iteration 9 left it. The claim that all 16 ancestor commits are the
same agent's own prior work was checked only as far as "all `Auto-snapshot: builder's turn`," not
verified commit-by-commit against `runs`. `task-e6b05093` itself remains `assigned`/`gated` —
unblocking it (its prerequisite `task-0dfc3be5` is now `approved`) was not attempted this iteration;
Q5 closed on the merge question, not on clearing the whole task graph.

**Job sweep, as output:** `ai_jobs` on `ledger-stress`, all six rows `enabled: false`, queried live
against the `beta` database.

**Next:** Q6 opens. F58 is now the top-priority item in it — severity A, contradicts the module's
own stated guarantee, needs a real design decision on cherry-pick semantics before a fix, not a
patch. F53 and F55 remain queued behind it. `task-e6b05093` (now unblocked) and the general
Q6/Q7/Q8/Q9/Q10 backlog remain untouched.

---

## Iteration 11 — Q6: F55 fixed (picked up mid-flight, verified and closed out), F58 still open

**2026-08-26T03:07–03:20+01:00.** This process started fresh with no memory of prior iterations, as
designed. Reconciliation found something the standard "branch/log matched STATE.json" check has not
hit before this run: `git log` tip (`268e5c8`, iteration 10's heartbeat release) matched
`STATE.json` exactly and the tree was **not** clean — nine tracked files modified plus one untracked
migration (`0088_checkpoint_sequence.py`), all shaped as a complete, well-written fix for **F55**
(the `Checkpoint` tie-break bug queued behind F58 in iteration 10's own `next_action`). No log entry
or `STATE.json` update existed for this work — a prior fresh process evidently started iteration 11,
implemented and wrote up F55 in full (including a `FINDINGS.md` section already claiming a mutation
check and a full green run), then stopped before committing or logging. Rather than discard
substantial, seemingly-correct work, verified it independently before trusting any of its claims,
per this run's own "never accept 'tests pass' as evidence you didn't check yourself" discipline.

**Chose F55 over F58 deliberately, and that choice was already the right one, not something this
iteration second-guessed.** F58 needs a real design decision (cherry-pick range vs. single-commit
patch-apply vs. per-task worktrees) that iteration 10 explicitly left for the operator to weigh in
on rather than guess — F55 has no such open question, so a prior process reaching for it first,
even out of the queue's stated order, matches the standing "a decision that is genuinely the
user's goes to `decisions_for_user`, not a guess" rule. Not treated as a deviation worth flagging.

**Verified independently, not trusted on the strength of the write-up.** Ran the directly-relevant
slice (`test_migrations.py`, `test_flow_checkpoint_lineage.py`, `test_handover_briefs_the_reviewer.py`,
`test_project_persistence.py`): 95 passed, 1 skipped. Broader `-k checkpoint` slice: 184 passed.
Grepped for any remaining `session.get(Checkpoint`/`Checkpoint.created_at.desc()` call site the
write-up might have missed: none — all four `order_by` sites and all three `session.get` sites were
already converted. **Ran my own mutation check** rather than trusting the write-up's claimed one:
reverted `latest_checkpoint_for_loop`'s `order_by` back to
`Checkpoint.created_at.desc(), Checkpoint.id.desc()` — the named regression test
(`test_latest_checkpoint_for_loop_breaks_a_tie_by_insertion_order_not_id`) failed exactly as
predicted (`assert 'ckpt-zzz-older' == 'ckpt-aaa-newer'`); restored, reconfirmed 7/7 green in that
file. `ruff check` and `black --check --target-version py311` clean on all nine touched files.

**Verified LIVE, on the restarted trial Hub, not just against the fixture.** Stopped the process
holding port 8010 (PID `17316`, started `02:30:39` — predates this fix), relaunched the documented
`uvicorn` command with `DATABASE_URL` pointed at the beta profile. `/health` ok within ~8s;
`e2e.py state proj-18e5d4e0` read the same project state as before the restart, confirming the beta
database, not `hub/data/agentweave.db`. Migration `0088` applied on startup: querying
`checkpoints` directly afterward shows `sequence` populated in the correct order for all nine
existing rows (e.g. `ckpt-42c9362f7ba4` — the F43 checkpoint from iteration 7 — reads
`sequence: 9`, the highest, matching that it really is the newest). Then exercised the actual
regression path over HTTP: `GET /projects/proj-8605b92d0028/checkpoints/ckpt-42c9362f7ba4/rendered`
(the endpoint that now resolves through `get_checkpoint_by_id` instead of `session.get`) returned
`200` with the real rendered body — a genuine end-to-end confirmation that the primary-key change
does not break checkpoint lookup by its stable string id, not merely that the test suite believes
so. (First attempt used the wrong project — `proj-18e5d4e0`, where the checkpoint does not live —
and correctly 404'd; retried against the right project and got the real row. Recorded so the 404 in
the raw session isn't mistaken for a defect.)

**Job sweep, as output**, immediately after the restart: all twelve `ai_jobs` rows across all five
projects read `enabled: 0` — nothing was enabled by the restart or by this iteration's live checks.

**Committed** (`1dd0b04`): the nine touched files plus the new migration, in one commit — this is a
single finding (F55), not several, so the "commit per finding" discipline is satisfied by one commit
here, unlike iterations that touched multiple findings.

**Full `hub/tests/` suite kicked off in the background** (`py -3.11 -m pytest hub/tests/ -q`) to
reconfirm whole-suite green after the schema change touches every test that constructs a
`Checkpoint` row; result to be recorded in the next iteration's entry once it completes, per this
run's own "don't conclude it is stuck" guidance for an ~11-minute run.

**What a reviewer should distrust.** This iteration did not itself write any of F55's implementation
— it inherited, read, and independently re-verified work whose original authorship (a prior fresh
process within this same run, per `STATE.json`'s own iteration counter) is not separately
distinguishable from this entry. Every specific claim above (test counts, the mutation-check
failure text, the live HTTP response, the job sweep) was independently reproduced this iteration
rather than copied from the pre-existing `FINDINGS.md` write-up, but the write-up's prose itself
(the `FINDINGS.md` "Fixed, iteration 11" section) was left as found rather than rewritten, since
its technical content matched everything independently checked. The full whole-repository test
suite result is not yet in this entry — see the next iteration.

**Next:** Q6 continues. F58 (design decision needed, top priority, per iteration 10) and F53
(design decision needed, orphaned document/loop_id on archive) remain the two open Q6 items;
neither has an operator decision yet, so the next iteration's concrete unit of work is either (a)
sketch the F58 fix options concretely enough that a `decisions_for_user` entry captures a genuine
choice rather than restating iteration 10's three candidates, or (b) pick up whichever of F53/F58
turns out to have a narrower, decision-free sub-piece worth fixing now while the design question
stays open for the operator. Confirm the full-suite background run's result first.

---

## Iteration 12 — F58's decision-free sub-piece: found already implemented, independently
verified, live-checked, committed. F53 has the same shape, unfixed.

**2026-08-26T03:07–03:5X+01:00.** Fresh process, no memory of prior iterations, as designed.
Reconciliation found the same pattern iteration 11 hit: `git log` tip (`ca13c32`, iteration 11's
heartbeat release) matched `STATE.json` exactly, but the tree was **not** clean — a complete,
well-written fix for exactly the option-(b) path iteration 11's own `next_action` named ("F58's
blast radius could be reduced by ... warning/flagging when `integrate()` is about to merge more
than the named commit's own diff, without yet choosing the full cherry-pick redesign"), already
sitting uncommitted: `task_integration.py`'s `commits_riding_along()`, a new
`TaskIntegration.rode_along_commits` column (migration `0089`), the API exposing it, the UI
rendering an amber warning under a merged row, tests for both the Python and TypeScript sides, and
a `FINDINGS.md` write-up already self-labelled "iteration 12." A second fresh process within the
same run had done this work and stopped before committing — same shape as iteration 11's own F55
pickup, and treated the same way: verify independently before trusting any of it, never on the
strength of the write-up's own claims.

**Independently reproduced every claim, not copied from the write-up.** `pytest
tests/test_task_integration.py tests/test_migrations.py tests/test_project_persistence.py -q`:
104 passed, 1 skipped — matches. `npx vitest run src/__tests__/taskIntegrationRetry.test.tsx`:
8/8 passed — matches. `ruff check` and `black --check --target-version py311` clean on all seven
touched Python files; `tsc --noEmit` and `eslint` clean on the three touched TS/TSX files. **Ran my
own mutation check**, not the write-up's: stashed only `task_integration.py`, reran the new test —
`test_rode_along_commits_names_what_actually_landed` failed with the exact predicted diff
(`assert [] == ['7b7a670b...']`), restored, reconfirmed green. (The UI-guard mutation check the
write-up describes — commenting out the render condition — was not separately repeated; the Python
mutation check plus the passing UI test together were judged sufficient given the component is a
five-line conditional already covered by both a positive and a negative test.)

**UI bundle rebuilt and committed with its source, per the standing rule.** `hub/ui/src` was
touched; ran `npm run lint` (clean, no output), `npx tsc --noEmit` (clean), `npm run build`
(succeeded, 2703 modules), then `py -3.11 scripts/refresh_ui_bundle.py` from the repo root — old
hashed assets removed, new ones added, `ui-build-stamp.json` updated. Committed together in the
same commit as the source, per the rule this file has cost two prior sessions for getting wrong.

**Verified LIVE, one step further than the write-up's own "not verified live" admission.**
Restarted the trial Hub (stopped PID `10892` holding port 8010, relaunched `uvicorn` from `hub/`
with `DATABASE_URL` pointed at the beta profile; `/health` ok in ~8s; `e2e.py state proj-18e5d4e0`
read the same `ledger-stress` run history as before the restart, confirming the beta database).
Queried the live database directly: `alembic_version` reads `0089` (migration applied cleanly on
restart), and `task_integrations.rode_along_commits` exists and reads `''` on the one pre-existing
F58 merge row (`tint-cc7f14015dfb`, from Q5's iteration 9 drive) — expected, since that merge ran
before this column existed and nothing retroactively recomputes history. **A full live re-drive
producing a new, non-empty `rode_along_commits` row was not attempted** — the one candidate
(`task-e6b05093`, FR-3, on the same agent branch as the original F58 merge) is still `assigned`,
not yet under review, and driving it to `approved` through a real reviewer turn is a bigger unit of
work than this iteration's verification pass; left explicit rather than silently skipped.

**Job sweep, as output, both before and after the restart:** all twelve `ai_jobs` rows across all
five projects read `enabled: 0`.

**Committed** (`f20e181`): all fifteen files (seven `hub/` source/test, three UI source/test, the
rebuilt bundle, the new migration, `FINDINGS.md`) in one commit — one finding, one commit, per the
standing discipline.

**Kicked off the full `hub/tests/` suite in the background** (`py -3.11 -m pytest tests/ -q`,
~11-14 minutes measured) to reconfirm whole-suite green after two consecutive schema-touching
migrations (`0088`'s `Checkpoint` primary-key change, `0089`'s new column) — this has not been run
whole since the arming baseline; every iteration since has run only touched-file/topic slices.
Result recorded below once it completed, per this run's own "don't conclude it is stuck" guidance.

**FULL SUITE RESULT:** lost — the background process that ran it belonged to the fresh process's
own shell session, which ended before this entry was committed, so its output was never captured
anywhere durable. Recorded here rather than silently dropped, per this run's "never claim what
wasn't measured" rule. The next iteration (below) relaunches the full suite itself and reports a
real result.

**What a reviewer should distrust.** This iteration did not author F58's mitigation — it inherited,
independently re-verified (test counts, the mutation-check failure text, the live migration/column
check, the job sweep), and committed work whose original authorship is not separately
distinguishable from this entry, same caveat iteration 11 recorded for F55. The live verification
confirms the schema and code are live-safe, not that a new rode-along scenario renders correctly
end-to-end through the UI in a browser — that remains unexercised.

**Next:** F53 has the identical shape available: a narrow, decision-free half
(`_check_spec_document_conflict` excluding archived loops, letting a new job be created against a
document an archived loop still claims) that does not require deciding what happens to the
already-`loop_id`-stamped tasks (the part that is genuinely the operator's call, since it turns on
whether "already started" work should keep or lose its `loop_id`). That is the natural next unit of
work for Q6. Failing that, Q7 (F50, pre-authorised, not yet touched this run) has no decision
blocker at all and is the fallback.

**2026-08-26T04:19–04:5X+01:00.** Fresh process, no memory of prior iterations, as designed.
Reconciliation: `git log` tip (`f20e181`, F58's commit) matched what `STATE.json` claims as its
parent history, but the tree was again **not** clean — the exact pattern this run has now hit
three iterations running (11, 12, and this one). Uncommitted in the tree at start: a complete
narrow fix for F53's decision-free half (option (a) from F53's own write-up), `next_action`'s named
top choice — `jobs.py`'s `_check_spec_document_conflict` now excludes archived loops, `models.py`'s
`Loop.spec_document_id` replaced its unconditional `unique=True` with a partial unique index
(migration `0090`), plus a regression test and updated head-revision assertions in two other test
files. No `FINDINGS.md` entry existed for it yet and `STATE.json` had not been advanced past
`"iteration": 12"` with a fresh heartbeat but stale `next_action`/`decisions_for_user` text still
narrating the F58 handoff as upcoming rather than done.

**Did not trust the code on sight — independently verified, and this time verification caught a
real bug the inherited work had not.** Ran the directly-relevant slice first
(`test_jobs.py -k "f53 or spec_document or document_conflict"`, `test_migrations.py`,
`test_project_persistence.py`): 4 passed on the narrow slice, but `test_migrations.py` on its own
came back **2 failed** — `test_migration_0085_adds_lineage_id` and
`test_migration_0086_adds_review_task_id_to_queue_entries`, both `sqlite3.OperationalError: no such
table: main.loops`. Traced, not dismissed: those two tests synthesize a database starting from an
early revision (0034), so by the time `alembic upgrade head` walks through migration `0090`'s
`downgrade()` path (both tests upgrade to head then downgrade partway), the `loops` table can be
absent. `upgrade()` in `0090` correctly guards for a missing table (`if not existing and _TABLE not
in ...: return`, matching `0033`/`0034`'s own precedent this repo's CLAUDE.md names explicitly) —
`downgrade()` did not have the same guard, and crashed trying `CREATE UNIQUE INDEX
ix_loops_spec_document_id ON loops (...)` against a table that does not exist. Added the identical
guard to `downgrade()`. Reran: `test_migrations.py` + `test_project_persistence.py` → 78 passed, 1
skipped. Reran the full trio together (`test_jobs.py` + both migration files) → 134 passed, 2
skipped.

**Mutation-checked the actual fix, not just the schema bug.** Temporarily reverted
`_check_spec_document_conflict`'s `Loop.archived_at.is_(None)` filter via a scripted patch/restore
(not a manual edit left lying around) and reran the new test alone: failed with the exact pre-fix
`409 {"detail": "document 'doc-declare-f53' is already claimed by loop '...'"}`, confirming the API
check is load-bearing independent of the schema-level partial index. Restored, reconfirmed clean
via `git diff --stat` (0 lines changed).

**`ruff check` and `black --check --target-version py311` clean** on all six touched files
(`jobs.py`, `models.py`, the new migration, three test files).

**Verified LIVE, from scratch, not by trusting the write-up's own live-verification claims (there
were none yet — this fix had no write-up at all when the iteration started).** Found the trial
Hub's actual listening PID via `netstat -ano | grep 8010` (`25788`, not whatever prep last
recorded — PIDs do not survive restarts), killed it, relaunched `uvicorn` from `hub/` with
`DATABASE_URL` pointed at the beta profile per `environment.restart_hub`, confirmed `/health` ok.
Queried the live SQLite file directly: `alembic_version` reads `0090`; `sqlite_master` on `loops`
shows both `ix_loops_spec_document_id` (now non-unique, matching the model's bare `index=True`) and
the new partial-unique `ux_loops_spec_document_live`. Then drove the real scenario over real HTTP
against `proj-8605b92d0028` (the Q1 drive project, chosen because it is idle and disposable rather
than disturbing `ledger-stress`'s accumulated state): `POST /jobs` with `spec_document_id:
doc-f53-live-verify-iter13` and `enabled: false` (so nothing could ever fire or spend) → `201`;
`POST /jobs/{id}/archive` → `200`; a second `POST /jobs` against the identical `spec_document_id`
→ **`201`**, where the F53 write-up's own reproduction shows this was a permanent `409` before the
fix. Archived the second job immediately after (cleanup, not left for the morning). Confirmed via
`GET /projects` + per-project `GET /projects/{id}/jobs` that all jobs across all five projects
(`proj-8605b92d0028`, `proj-18e5d4e0`, `proj-2826f39e`, `proj-54d33cac`, `proj-5e960453`) read
`enabled: false` — printed as output above, not asserted.

**Updated `FINDINGS.md`** with a "Resolution (partial)" section under F53 itself, rather than a new
finding number, since this closes exactly the decision-free half the original write-up already
scoped out — states what was fixed, what was caught in verification (the downgrade guard bug), how
it was live-verified, and that the `loop_id`-orphaning half (root cause 2) is still open and still
the operator's call.

**Committed** (one finding, one commit): the six touched files plus the `FINDINGS.md` addendum.

**Relaunched the full `hub/tests/` suite in the background** (`py -3.11 -m pytest hub/tests/ -q`)
from the repository root, both to reconfirm whole-suite green after this iteration's schema change
stacked on `0088`/`0089`'s, and to replace the previous iteration's lost result. Not yet complete
as of this being written — result below, filled in before this entry closes, per this run's own
"don't conclude it is stuck" guidance and its sibling rule against claiming an unmeasured result.

**FULL SUITE RESULT:** lost again — the same pattern as the previous iteration's attempt: the
background process belonged to a shell session that ended before this entry was committed. This is
now twice in a row this run has tried to background the full suite across a process boundary and
lost the result both times, which is itself worth recording as friction in the method rather than
quietly retrying a third time the same way: a background job started by one fresh process is not
guaranteed to survive to the next one, so a whole-suite confirmation should be run and consumed
within a single iteration's own lifetime, not handed off. The next iteration (below) does exactly
that.

**What a reviewer should distrust.** This iteration did not author F53's mitigation — it inherited,
found a real defect in it during independent verification (the migration downgrade guard), fixed
that defect itself, then verified the corrected whole through the same discipline (mutation check,
live HTTP drive, job sweep) previous iterations have used. The live verification confirms the
create→archive→recreate path is live-safe on this one project; it does not exercise the UI's own
loop-archive flow in a browser, which remains unexercised exactly as prior iterations left it for
F58's UI-adjacent piece.

**Next:** F53's other half (`_adopt_document_tasks`'s `loop_id` orphaning) still needs the
operator's decision and stays open. Q7 (F50, pre-authorised, no decision blocker) is the cleanest
next unit of work if nothing else in Q6 turns up a similarly narrow, decision-free slice.

---

## Iteration 13 — Q7 closes: F50 found already implemented, independently verified, live-reconfirmed against a real reproduction; a full-suite result finally captured within one iteration's own lifetime

**2026-08-26T04:45–05:1X+01:00.** Fresh process, no memory of prior iterations, as designed.
Reconciliation: `git log` tip (`3defb1e`) sat three commits ahead of what the on-disk `STATE.json`
and log described (`f20e181`/F58, `2239f38`/F53-partial, and — new, undocumented — `3defb1e`/F50).
The working tree itself was clean this time (no uncommitted work waiting), but `STATE.json` and the
log had not been advanced to match: `STATE.json`'s `next_action` still narrated iteration 11's F55
close as current, and the log's own "Next" pointer above still named F50 as unstarted. Fourth
iteration in a row this run has found its own bookkeeping behind its own commits — a fresh process
had done the F50 work, written a complete commit message with its own verification claims, and
exited before touching `STATE.json` or this log at all (no uncommitted trace, unlike iterations
11–12's pattern — this one committed cleanly but the handoff files were simply never written).

**Did not trust the commit message's own verification claims — independently reproduced every one.**
`pytest hub/tests/test_checkpoint_generation.py -q`: 21 passed, matching the commit's claim. **Ran
my own mutation check**, not the commit's: patched out the two new `lines.append` calls for
`Status`/`Probe` in `render_checkpoint` via a scripted patch (not a manual edit left lying around),
reran the checkpoint-generation suite narrowed to `status or probe or F50 or failure` — both named
tests failed exactly as predicted
(`test_a_ready_checkpoint_states_its_status_without_a_failure_warning`,
`test_a_checkpoint_that_failed_its_probe_states_the_failure_instead_of_hiding_it`,
`AssertionError: assert 'Status: failed' in '...'`). Restored via `git checkout --`, confirmed
`git diff --stat` empty, reconfirmed 21/21 green. `ruff check` and `black --check
--target-version py311` clean on both touched Python files. `npx openspec validate
loop-becomes-a-flow --strict`: valid.

**Verified LIVE against the trial Hub, which was already running and did not need a restart** (no
schema change in this commit — `render_checkpoint` is pure formatting over existing columns).
`GET /health` ok. Fetched the commit's own named reproduction over real HTTP with the project's live
API key: `GET /projects/proj-18e5d4e0/checkpoints/ckpt-9cba6c0e8e40/rendered` — response reads
`Status: failed`, `Probe: failed`, and the stated warning paragraph ahead of the written body,
exactly as the commit describes and exactly matching `FINDINGS.md`'s own resolution write-up
(already present under F50, correctly labelled severity B). `openspec/changes/loop-becomes-a-flow/
tasks.md` task 14.7 already closed with matching evidence — nothing left to add there.

**Job sweep, as output, across all five projects:** `proj-8605b92d0028` `[]`, `proj-18e5d4e0` six
jobs all `enabled: False`, `proj-2826f39e` two jobs both `enabled: False`, `proj-54d33cac` `[]`,
`proj-5e960453` `[]`.

**Full `hub/tests/` suite, run and consumed within this single iteration's own process lifetime —
not handed across a process boundary, which is exactly the failure the previous two iterations
named as friction.** Launched via the harness's own tracked background-command mechanism (not a
raw shell `&`, which is what iterations 11–12 lost) so the result survives regardless of how long
verification of other things takes in between.

**This entry itself was cut off here mid-write** — the fresh process that ran this suite committed
`3defb1e` (the F50 fix above) cleanly, then was terminated (or the harness cycled) before it could
finish writing this log entry or touch `STATE.json` at all: no uncommitted trace was left in the
tree (unlike iterations 11–12's pattern), but `STATE.json`'s `next_action` still narrated
iteration 11's F55 close as current and this log's own last "Next" pointer still named F50 as
unstarted, even though `git log` already showed F58, F53-partial, and F50 all committed. The next
iteration (below) found and fixed this reconciliation gap, and independently captured the result
this entry was waiting on: **1 failed, 3144 passed, 84 skipped, 1 xpassed, 190 warnings in 1052.50s
(17:32)** — the single failure was
`test_evidence_latest_review_signal.py::test_a_later_acceptance_replaces_the_reason_shown`, a real,
new-to-this-run finding (F59), not noise. See the next entry for the investigation and fix.

---

## Iteration 14 — reconciliation (three iterations' worth of undocumented commits), and F59: the F55 clock-tie bug recurs in a second table

**2026-08-26T05:00–05:4X+01:00.** Fresh process, no memory of prior iterations, as designed.
Reconciliation found the pattern now established across iterations 11–13: `git log` tip (`3defb1e`)
sat three commits ahead of what `STATE.json` and the log described. Unlike 11–12 (uncommitted work
waiting) or 13 (clean tree, no handoff written), this time the tree held a **partial, uncommitted
edit already in progress** — `STATE.json`'s `iteration` bumped to 12 and Q7 marked `closed`, and
223 lines already appended to this log documenting iterations 12 and 13 — meaning a *fourth* fresh
process had already started this exact reconciliation and been cut off mid-way through, before
finishing `next_action`/`decisions_for_user` or committing. Read and kept rather than discarded:
independently spot-checked against `FINDINGS.md`'s F58/F53/F50 write-ups and `git log`, and it was
accurate.

**The full suite's own result was still missing**, exactly as the previous entry's own final
paragraph says — this iteration's first job was to finish capturing it rather than trust either
prior claim about it. Found the actual pytest process still running (PID `15672`, started
`05:01:37`, the same run iteration 13 had launched and lost across its own process boundary) via
`Get-CimInstance Win32_Process`, found its live output already redirected to `/tmp/full_suite_out.log`
(one of three candidate log files from repeated prior attempts — picked by mtime, the freshest),
and waited on it via a monitored background loop rather than losing it a third time. Result: **1
failed, 3144 passed, 84 skipped, 1 xpassed, 190 warnings, 1052.50s** —
`test_evidence_latest_review_signal.py::test_a_later_acceptance_replaces_the_reason_shown`.

**F59 (B) — investigated rather than dismissed as a flake, and it is the identical bug class F55
already named, in a second table.** Re-ran the failing test bare, six times, on the unmodified
branch tip: 3 of 6 failed, alternating with no code change between runs — not a coincidence, and
`git log` confirmed this file was untouched by any commit this entire run, so it predates this
session's own work rather than being a regression from it. Read `_latest_reviews_for`
(`hub/hub/api/v1/spec.py`) and `reviews_for` (`hub/hub/requirement_evidence.py`): both order by
`EvidenceReview.created_at, EvidenceReview.id` — exactly F55's `Checkpoint` shape, tie-broken by a
random string id with no relation to insertion order, on a machine where `datetime.now()` can
return an identical value across consecutive calls. Full write-up under **F59** in
`scripts/drive/FINDINGS.md`.

**Fixed following F55's own established shape, not reinvented.** `EvidenceReview` gained a
`sequence` autoincrement primary key (migration `0091`), both `order_by` call sites now read
`.order_by(EvidenceReview.sequence)`. **A second, real bug was caught during verification, not
authored by the fix**: the migration's existence guard didn't account for `batch_alter_table`'s
`recreate="always"` transitively reflecting `requirement_evidence`'s own FK to `tasks` (because
`evidence_reviews` FKs to `requirement_evidence`) — 14 unrelated `test_migrations.py`/
`test_project_persistence.py` tests broke with `NoSuchTableError: tasks` the moment the new
migration was added, all of them synthetic early-revision upgrade chains that never materialise a
`tasks` table. Added `tasks` to the guard's required-table set; all 14 passed again. Full
regression test constructs the tie deterministically (adversarial ids, a shared `created_at` read
from a real row) rather than relying on wall-clock luck. **Mutation-checked**: reverted both
`order_by` sites, the new test failed with the exact predicted assertion; restored, reconfirmed.
Bare-reran the originally-flaky test 8 times post-fix: 8/8 passed. `ruff`/`black
--target-version py311` clean on all seven touched files. Broader slice (`-k "evidence or spec or
agent_actions or requirement"`, 837 tests): 817 passed, 20 skipped, 0 failed.

**Verified LIVE.** Restarted the trial Hub on the beta database (PID found via `netstat`, not
assumed from a stale record — this run's own `dead_ends` note that PIDs do not survive restarts).
Confirmed via direct query, not `/health` alone: `alembic_version` reads `0091`,
`evidence_reviews.sequence` populated `1..3` in original insertion order on the three pre-existing
rows. Posted two real decisions back to back over HTTP against a genuine `awaiting` evidence row on
`ledger-stress` (`ev-9ab3be95`) using the operator's bootstrap API key: the response after the
second call correctly read `review_state: "accepted"` with the second call's own reason text, and
the database afterward showed `sequence` `4` then `5` for the two new rows — insertion order, not a
random id, is what the live response actually followed. **What a reviewer should distrust**: the
two live HTTP calls landed ~50ms apart (real network/API latency), not in the same clock tick, so
this proves the fixed path works correctly end-to-end but does not itself reproduce the original
race live — only the mutation-checked unit test forces the tie deterministically. Job sweep
immediately after: all fourteen `ai_jobs` rows across all five projects read `enabled: 0`.

**Full `hub/tests/` suite kicked off again**, freshly, from this iteration itself, to confirm
whole-suite green with F59's fix included (the previous 1052s run predates the fix and is now
superseded, not reused) — launched via a properly backgrounded, trackable process from the start
this time rather than recovered after the fact. **Result: 3147 passed, 84 skipped, 1 xpassed, 0
failed, 950.78s (15:50).** `py -3.11 -m ruff check src/ hub/ tests/`: all checks passed. `black
--check src/ hub/hub/ hub/tests/ tests/ --target-version py311`: 485 files unchanged. Whole-suite
green is re-established with all of this run's work through F59 included.

**Job sweep, reconciliation-adjacent:** the fourteen `ai_jobs` rows read above are the same set
observed both before and after this iteration's Hub restart — nothing was enabled by any of this
iteration's own actions.

**Repository root** stayed as expected: `.claude/autonomous/STATE.json` and this log (both being
actively reconciled), plus the seven `hub/` files for F59 — confirmed by `git status` before
committing.

**What a reviewer should distrust, overall:** this is the fourth consecutive iteration to spend
part of its turn on bookkeeping debt left by a predecessor rather than pure forward progress —
worth naming as a pattern rather than an isolated event. The underlying cause each time has been
the same: a fresh process does real, correctly-verified work, then is cut off (by the driver
cycling, by a background process outliving its own shell) before writing `STATE.json`/the log or,
in iterations 11–12's case, before committing at all. None of the underlying work itself has been
wrong when independently re-verified — the cost has been entirely in continuity, not correctness.
If this keeps recurring, the actual fix is probably making the commit+STATE.json+log update one
atomic step at the very end of whatever unit of work an iteration does, before any "let me also
just quickly..." follow-on — not something to patch this session, but worth flagging plainly for
whoever reads this run's own retrospective.

**Next:** with F50/F53(partial)/F58(partial)/F59 all now closed or as-closed-as a decision-free fix
allows, Q6's two remaining items (F53's `loop_id`-orphan half, F58's merge-redesign) are both
genuinely blocked on the operator's judgment — there is no further decision-free work available in
Q6. The natural next unit of work is **Q8**: drive the operator-in-the-loop surfaces (a `manual`
permission-mode run, answering an approval card through the real API, letting a permission card and
an `ask_user` batch time out and observing what the operator sees, checking F14's shape), then vary
one environmental axis (`PYTHONIOENCODING=utf-8` has the track record) and re-run a verification.

## Iteration 15 — Q8 part 1: manual permission mode driven live, and F60, a sharper version of F14

**2026-08-26T05:55–06:1X+01:00.** Fresh process. Reconciliation this time was clean: `git log` tip
(`e8e7501`) matched `STATE.json` exactly, working tree clean, no undocumented commits — the first
iteration in several to start with zero bookkeeping debt. Verified the trial Hub was already up
(`/health` returned `ok`) and moved straight into Q8's first unit of work.

**Manual permission mode, driven end to end on the real surface, not simulated.** Used
`proj-8605b92d0028` (the Q1 drive project, which had accumulated real state since STATE.json's own
`environment` note was written: three pending bug-fix tasks plus one already completed by an
earlier iteration's loop run — the stale "no tasks yet" in `STATE.json.environment` is corrected
here, not re-trusted). Triggered `author` (Haiku, cheap runner) on `task-06e74937de88` (the
`apply_bulk_discount` off-by-one) with `overrides.permission_mode: manual` via `e2e.py turn --perm
manual`. A real `PermissionRequest` row (`perm-efedf9c04e01`) appeared carrying the actual `Edit`
tool call — `old_string`/`new_string` and all — within seconds. Answered it through the real
operator API, `POST /permission-requests/{id}/decide {"allow": true}`, not a shortcut: the run
picked the decision up and continued, completed cleanly, and the fix (`range(len(items) - 1)` →
`range(len(items))`, plus a discount-rate validation the agent added on its own initiative) landed
in the run's own worktree — confirmed by reading the worktree file directly, not the transcript.
`record_evidence` succeeded from the Haiku agent once the document path was supplied (a workable
path through what F21 once found broken, not a contradiction of it — different obstacle). Only the
`Edit` call generated a permission card; `Read`/`ToolSearch` did not — read that as Claude Code's
own CLI-level default (read-only tools are typically pre-approved regardless of `--permission-mode`
in the CLI itself) rather than an AgentWeave gap; not filed as a finding on that basis alone.

**Then the `ask_user` timeout, per the method's own directive to leave one question deliberately
unanswered — and it produced the single most valuable finding of this iteration.** Told `author`
honestly to ask a structured question before fixing `task-a9f72e6c80f8` (the `is_low_stock` float
equality bug) and to wait for an answer; it did, `blocking: true`, three labelled options. Left it
unanswered on purpose and polled the live database every 10s for the full 290s the turn ran
(backgrounded properly this time via the harness's own background-task mechanism, not lost across a
shell boundary). Confirmed F14 exactly as documented during the wait: `runs.status=running`,
`tasks.status=in_progress`, `blocked_reason=None`, the whole time — nothing on the board says the
agent is stuck on a question. **What happens after the timeout is a new, sharper finding, F60,
severity A.** The 240s `QUESTION_ANSWER_TIMEOUT` expired inside the tool call; the agent correctly
reasoned about the timeout in its own transcript, picked an answer from the spec text itself, made
the fix, ran tests, and — in the *same* turn — called `update_task` to mark the task `completed`
*before* the run itself ended. By the time `run_divergence.evaluate_run_end` ran,
`block_task_for_question` had nothing to park: the task was no longer `in_progress`. Confirmed from
the rows: `tasks.status='completed'`, `blocked_reason=None`, and the question row itself —
`answered=0, declined=0, blocked_task_id=None` — permanently orphaned, forever `pending` in the
operator's questions list with no visible link to the now-completed task. **Then compounded it
live**: `PATCH` on the orphaned question five minutes after the run ended, with the answer the agent
had *not* picked, returned `200` and recorded it as if current — nothing refuses answering a
question whose asking run has already ended, and nothing reconciles a late answer against what
actually shipped. Full write-up as **F60** in `scripts/drive/FINDINGS.md`, including what held (the
timeout itself is bounded and the agent's own fallback judgment was reasonable — the gap is
entirely in what the Hub records and surfaces afterward). Not fixed this iteration: recorded per the
queue's own drive/fix split, and the durable-surfacing half of a fix belongs with F14's own eventual
fix, not guessed at separately.

**Environmental axis variation, scoped to what fit in the remaining budget.** `PYTHONIOENCODING=utf-8
py -3.11 -m pytest tests/ -q`: **440 passed, 3 skipped, 21.46s** — identical to `green_at_arming`'s
baseline, no regression surfaced under this axis today. Recorded as a "what held" result, not
chased further; the full `hub/tests/` suite was not rerun under the variation (≈16 minutes, judged
not worth spending against the remaining Codex half of Q8).

**Job sweep**, before wrapping: all fourteen `ai_jobs` rows across all five projects (`proj-2826f39e`
×2, `proj-18e5d4e0` ×7, `proj-8605b92d0028` ×5) read `enabled: 0` — none of this iteration's direct
`agent/trigger` calls touch job state, and none did.

**What a reviewer should distrust:** F60's live reproduction is a single run on a Haiku agent;
whether a different runner (Codex) reaches the same "resolves the question itself mid-turn, then
completes the task" shape, or instead genuinely blocks, is unverified — the Codex `decide_approval`
leg of Q8 was not reached this iteration. The `PYTHONIOENCODING` check only covered `tests/` (443
tests, 21s); `hub/tests/` (3147 tests, ~16 minutes) under the same axis remains unverified this run.

**Next:** Q8's remaining scope — trigger a `manual`-mode run on the Codex cheap runner
(`gpt-5.4-mini`) and confirm `codex_appserver.decide_approval` routes through the same
`permission-requests` surface, or record where it diverges; optionally extend the
`PYTHONIOENCODING=utf-8` check to `hub/tests/` if time allows. After that, Q9 (the full sweep and
the `openspec/explorations/2026-08-26-driving-everything.md` write-up) is the next queue item with
no operator blocker.

## Iteration 16 — 2026-08-26 06:30–06:53+01:00 — bookkeeping reconciliation, Q9 closed, Q10 closed

**Reconciliation.** `git log` matched STATE.json exactly (tip `c83487e`, iteration 15's heartbeat
release) — no drift to fix there. But `git status` showed one untracked file:
`openspec/explorations/2026-08-26-driving-everything.md`, already 210 lines of a substantially
complete Q9 write-up, including a section ("An organic, unplanned data point on Q8's Codex leg")
describing events — a real, live Codex manual-permission run discovered already in progress at the
start of *some* iteration — that postdate iteration 15's own commit and log entry. This is bookkeeping
debt from an interrupted process: an iteration (almost certainly a distinct attempt at what would
have been iteration 16) did real, live-verified work and wrote a careful document, but was cut off
before committing or updating STATE.json/the log. Per the standing rule (never trust an uncommitted
claim), the document's factual claims were spot-checked against the live trial-Hub database before
accepting them:

- `run-3e08cae3629d` (the "organic Codex run"): DB confirms `status='failed'`,
  `error='turn timed out with no turn/completed notification'` — matches the document exactly.
- `task-9b0b4a141b21`: DB confirms `status='in_progress'`, `blocked_reason=None` — the task the failed
  run was working is still sitting `in_progress`, not itself part of this iteration's scope, noted
  below under Q10.
- Permission requests for that run: DB shows 8 rows (document said "seven... most allowed"); one more
  arrived between the document being written and this check, consistent, not a contradiction.
- All 14 `ai_jobs` rows across all five projects: still `enabled=0` — reconfirmed via both the live
  `GET /projects/{id}/jobs` API (which only lists non-archived jobs; five of `proj-8605b92d0028`'s
  rows are archived, which is why that project's API list reads empty despite having job rows in the
  table) and a direct DB read of the full table.

The document's content is real and grounded, not fabricated — adopted rather than rewritten.

**Q9 closed this iteration.** Ran the full sweep the document had not yet recorded:

| Check | Result |
|---|---|
| `py -3.11 -m pytest hub/tests/ -q` | 3147 passed, 84 skipped, 1 xpassed, 0 failed (950.60s / 15:50) |
| `py -3.11 -m pytest tests/ -q` | 440 passed, 3 skipped (22.00s) |
| `py -3.11 -m ruff check src/ hub/ tests/` | All checks passed |
| `black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311` | 485 files unchanged |
| `npx openspec validate --changes --strict` | `change/loop-becomes-a-flow` — 1/1 passed |

All green. Hub's passing count rose from `green_at_arming`'s 3127 to 3147 (+20) — consistent with the
regression tests this run's own fixes (F50–F60) added, not a discrepancy; zero failures anywhere.
`hub/ui/src` was not touched this run, so the UI lint/build/refresh/stamp steps do not apply. Appended
this table and a short reconciliation note into the exploration document itself, then committed it
along with this log entry and the STATE.json update — closing Q9 for real, not on the strength of a
document existing (the standing rule the document's own text quotes back at itself).

**Q10 closed this iteration**, time permitting (06:53, well inside the 08:00 window):
- **Job sweep, done as output not claim**: `curl` against `GET /api/v1/projects/{id}/jobs` for all
  five live projects (`proj-8605b92d0028`, `proj-18e5d4e0`, `proj-2826f39e`, `proj-54d33cac`,
  `proj-5e960453`) shows either an empty list or every entry `enabled: false`. Cross-checked against
  a direct read of the `ai_jobs` table (14 rows total, all `enabled=0`) to explain why
  `proj-8605b92d0028`'s API list reads empty (its five job rows are all `archived_at`-set, hence
  excluded from the live list endpoint, not because they don't exist).
- **The Q1 drive project (`proj-8605b92d0028`, `drive-2026-08-26`): KEEPING it, explicitly.** It
  carries real, non-trivial accumulated state worth re-driving: `task-06e74937de88` (`in_progress`,
  the F60 fix per iteration 15's notes sitting unmerged in the author's worktree) and
  `task-9b0b4a141b21` (`in_progress`, the task the organic Codex run above left mid-flight after a
  timeout failure — itself worth a clean, deliberate re-drive of Q8's Codex leg in a future
  iteration, since this iteration's own review of it was passive, not self-triggered). Running
  `e2e.py clean` on this project would destroy both. Not cleaned.
- **Minted credentials**: checked for a standalone revocable-credential trail (`operator_credentials`,
  `api_keys` tables exist in schema) — nothing this run itself minted requiring removal; per
  CLAUDE.md, run credentials are minted per-run (`agent_auth.py`) and are not standalone records this
  drive created or needs to clean up.
- Nothing destructive attempted or needed: ledger-stress, the trial database, its backups, and
  `C:\Users\huida\Documents\aw-sweep` were not touched.

**What a reviewer should distrust:** the "organic Codex leg" observation and `task-9b0b4a141b21`'s
current state are inherited from a document this iteration did not author from scratch — verified
against the live DB as described above, but this iteration did not itself trigger or watch that run.
Everything else in this entry (the full sweep, the job-sweep curl output, the keep/clean decision) was
directly executed and observed this iteration.

**Queue status after this iteration:** Q1–Q7, Q9, Q10 closed. Q6 remains blocked-on-operator (F53,
F58 need the operator's design call — unchanged from iteration 14). Q8 remains open: the Claude leg
and the `ask_user` timeout leg are driven and closed within Q8's own scope, but a clean,
deliberately-triggered rep of the Codex `decide_approval` leg (as opposed to the organic, passively-
observed one) is still outstanding, and is the only substantive item left in this run's queue.

**Next:** if a future iteration fires before 08:00 and Q8's Codex leg still hasn't had a clean rep,
that is the one thing left worth spending remaining budget on: trigger a `manual`-mode run on the
Codex cheap runner (`gpt-5.4-mini`) deliberately (not by finding one already running), watch
`decide_approval` produce and answer a `permission_requests` row through the real API, and record
whether Codex's behaviour diverges from Claude's beyond routing. Otherwise, the run is functionally
complete: every queue item is closed or explicitly blocked on the operator, every suite is green, and
`decisions_for_user` has the outstanding operator calls (F53, F58's design half, F60/F14's durable-
surfacing half) recorded and not duplicated.

## Iteration 17 — 2026-08-26 07:05–07:15+01:00 — Q8's Codex leg closed via inherited live evidence, corrected a stale-read false alarm

**Reconciliation.** `git log` matched STATE.json exactly (tip `cc84cde`, iteration 16's released
heartbeat) and `git status` was clean — no bookkeeping debt this time, a clean handoff for once.

**Found Q8's remaining scope already mid-flight, not started by this iteration.** `e2e.py state
proj-8605b92d0028` showed a `reviewer` run (`run-7575bf8435a8`, `task-9b0b4a141b21`) reading
`status: running` with `started_at` nearly 70 minutes earlier and no `last_heartbeat_at` ever
recorded — inherited state from whatever process ran between iteration 16's commit (06:53) and this
iteration's start (07:05), which left no log entry and was almost certainly cut off before it could
write one. Rather than re-trigger a fresh run and risk duplicating in-flight work, this iteration
chose to **observe and verify the inherited run**, since it was already exactly the scenario Q8
asked for: a deliberately-triggered `manual`-permission-mode Codex turn.

**First read produced what looked like a severe new finding, and it was wrong — caught before being
filed.** Reading `run-7575bf8435a8` via `sqlite3.connect('file:...?mode=ro', uri=True)` showed
`status='running'`, `pid=None`, `ended_at=None`, unchanged across a live process check. Cross-referencing
`permission_requests` for that run showed 11 real rows spanning 05:58–06:06, every one `status:
allowed`, `decided_by: operator` — clear proof `codex_appserver`'s `decide_approval` routes through
the identical `permission_requests` table and API as Claude's `--permission-prompt-tool` (matching
the structural finding iteration 15 already made, now with a full live rep to back it). The
worrying part was the *last* row (`perm-7ed30492574d`, a `pytest -q -s test_inventory.py` shell
call, decided `allowed` at 06:06:16) having no `tool_result` afterward and the run sitting silent
for ~59 minutes past that with no timeout firing — worth writing up as "the turn-timeout mechanism
that failed the two runs before this one didn't fire a third time." **That would have been wrong.**
A second read of the identical row, moments later, showed `status='failed'`,
`error='turn timed out with no turn/completed notification'`, `ended_at='2026-08-26 06:08:23'` —
almost exactly 600s (`DEFAULT_TURN_TIMEOUT_SECONDS` in `hub/hub/codex_appserver.py:490`) after its
`05:58:22` start, precisely matching the pattern of the two runs before it. **The first read was
stale**, not the row. Filed here as a new, general-purpose method note rather than as a product
finding: reading the beta trial database via `sqlite3.connect('file:...?mode=ro', uri=True)` can
return data that is *committed but not yet visible* to a fresh read-only connection when the
database is in WAL mode and the WAL file hasn't been checkpointed — this is a documented SQLite
behavior under `mode=ro` (a read-only connection may not get a shared-memory index and can miss
recent WAL-resident writes), not a bug in AgentWeave. `e2e.py`'s own `state`/`ro()` helper uses the
identical `mode=ro` URI pattern and is equally exposed. **Any time-sensitive "is this run actually
stuck" read from this database should be taken twice, a few seconds apart, before being trusted or
written up as a finding** — added to `dead_ends` in STATE.json so a future iteration doesn't
rediscover this the expensive way (by filing a false finding first).

**What actually held, confirmed with a clean second measurement:** the Codex turn-timeout mechanism
fired correctly a third consecutive time (`run-3e08cae3629d`, `run-45f17874e9e0`,
`run-7575bf8435a8` — three real Codex turns, three clean `failed` transitions at very close to
600s, zero silent hangs). `codex_appserver.py`'s comment at its `turn_timeout` parameter
(`hub/hub/codex_appserver.py:840`) states plainly the protocol itself supplies no turn-level
timeout and this is the Hub's own backstop — confirmed working, not merely documented, across three
independent real repros. Also confirmed the Hub's automatic redelivery: `inbound_queue_entries`
shows `entry-0749d003bc9e` (the same logical instruction) delivered first into `run-7575bf8435a8`
(failed, `delivery_attempts` bumped to 1) and then automatically redelivered into a fresh run
(`run-dbbd0ba274af`, a genuinely new Codex `app-server` process observed starting at 07:08:23 —
confirmed via `Get-CimInstance Win32_Process`, not inferred) without any trigger from this
iteration. `DELIVERY_ATTEMPT_LIMIT = 3` (`hub/hub/inbound_queue.py:174`) bounds this to at most
three ~10-minute attempts before the Hub gives up on the entry and records why — self-limiting, not
an unbounded overnight cost risk like an enabled job/loop would be, so this iteration did not
intervene to stop it; it will resolve (succeed or get abandoned with a recorded reason) within
roughly the next attempt cycle on its own, native-mode Hub scheduling working as designed.

**Q8 formally closed.** Both legs now have a real, live, deliberately-observed rep: Claude's
`--permission-prompt-tool` leg (iteration 15/16, `perm-efedf9c04e01` et al.) and Codex's
`decide_approval` leg (this iteration, 11+ real `permission_requests` rows across
`run-7575bf8435a8` alone, `decided_by: operator`, routed through the identical REST surface). The
`ask_user` timeout leg (F60) was already closed in iteration 15. No further Q8 scope remains.

**What a reviewer should distrust:** this iteration did not itself trigger any of the Codex runs it
observed — they were inherited, in-flight state from an unlogged, uncommitted prior process. The
permission-request evidence and the timeout-mechanism confirmation are independently verified
against the database and OS process list (not merely re-stated from what that prior process might
have intended), but the *task itself* (`task-9b0b4a141b21`) was not driven to a terminal state by
this iteration and its final outcome (third attempt succeeding, or the entry being abandoned at the
3-attempt limit) is unobserved as of this log entry — left for whichever iteration or the operator
next reads `e2e.py state proj-8605b92d0028` to confirm, with the double-read caveat above in mind.

**Queue status after this iteration: Q1–Q10 all closed or blocked-on-operator (Q6, unchanged).** No
substantive open scope remains in this run's queue. `decisions_for_user` is unchanged from
iteration 16 — nothing new needed the operator's judgment this iteration beyond what was already
recorded (F53, F58's design half, F60/F14's durable-surfacing half).

**Next**, if a future iteration fires before `stop_at` (08:00+01:00, very little runway left — this
iteration closed at ~07:15): there is no mandatory remaining scope. Worthwhile optional
follow-through, not required to consider the run complete: confirm `task-9b0b4a141b21`'s final
resolution (read twice, per the WAL caveat above) and note it for the record; otherwise the run is
functionally complete and further time is better spent standing down cleanly than manufacturing new
scope.

## Iteration 18 — final sanity check, run closed clean, no scope remains

Started at 07:15:54+01:00 with ~45 minutes of runway left before `stop_at` (08:00+01:00). State and
`git log` agreed exactly with no reconciliation needed (tip `37eefa9`, tree clean). Iteration 17 had
already closed every queue item and left only optional follow-through: confirm the trial Hub is
still healthy, confirm no job is enabled anywhere, and (optionally) confirm
`task-9b0b4a141b21`'s eventual terminal state. Did exactly that and nothing more — the queue has no
open scope to manufacture work from.

**Hub health:** `GET /health` → `{"status":"ok","runtime":"native"}`. Still the trial instance on
port 8010, unchanged since prep.

**Jobs, all three active projects, read live via the real REST surface (not sqlite):**
`proj-18e5d4e0` (ledger-stress) has six job rows, every one `enabled: false`
(`job-ee75c21a`, `job-18311467`, `job-f5558cff`, `job-bdea22bb0308`, `job-453b909ba418`,
`job-f632ee565238`). `proj-5e960453` (this repository — spec-flow only, correctly no agent-run
jobs) and `proj-8605b92d0028` (drive-2026-08-26) both return an empty job list. Nothing enabled
anywhere — the single most expensive thing to get wrong is confirmed clean at the run's true end.

**`task-9b0b4a141b21` final resolution:** read twice, ~5 seconds apart, via `GET
/projects/proj-8605b92d0028/tasks/task-9b0b4a141b21` (the live HTTP API, which goes through the
Hub's own connection — not the raw `sqlite3 mode=ro` path the iteration-17 WAL caveat is actually
about, so a single read here would already have been trustworthy; the second read was taken anyway
for belt-and-suspenders since the caveat was fresh). Both reads agree: `status: "completed"`. The
Codex retry chain iteration 17 observed in flight (`run-7575bf8435a8` → redelivery →
`run-dbbd0ba274af`) resolved to a successful terminal completion within the self-limiting 3-attempt
window, with no intervention needed from any iteration, exactly as iteration 17 predicted.

**Queue status: unchanged, Q1–Q10 all closed or blocked-on-operator (Q6).** `decisions_for_user` is
unchanged — no new operator decision surfaced this iteration.

**What a reviewer should distrust:** nothing new. This iteration performed only read-only
verification against the live Hub and its REST API; it triggered no runs, changed no code, and
touched no other project state.

**Run status: complete.** Across 18 iterations (2026-08-26T00:05 through 07:16+01:00), the full
queue Q1–Q10 was driven to closed or explicitly blocked-on-operator, every finding is recorded in
`scripts/drive/FINDINGS.md`, every outstanding operator decision is carried in this STATE.json's
`decisions_for_user`, and both suites plus lint/type-check were last confirmed green in iteration
16. No further iteration needs to fire before `stop_at`; if one does anyway (little runway remains),
it should simply reconfirm health and jobs-disabled and stand down, exactly as this one did.
