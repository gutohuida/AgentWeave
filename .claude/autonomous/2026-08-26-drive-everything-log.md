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
