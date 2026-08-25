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
