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
