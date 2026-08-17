# Autonomous run — one version, one product (AgentWeave 1.0.0)

Newest entry at the **bottom**. Written for someone who was not here.

**Branch:** `autonomous/2026-08-17-one-version-one-product`
**Parent:** `hub-native-experience` @ `e45b014`
**Window:** 2026-08-17T10:14+01:00 → 15:00+01:00
**Brief:** `.claude/autonomous/STATE.json` — 12 items, R1…R12, prepared by `/autonomous-prep` with
the operator awake.

**Goal:** one clean AgentWeave **1.0.0** on `master`, published to GitHub, with the documentation
and README describing the product that actually exists. AgentWeave becomes one product with one
version: the separate `agentweave-hub` version line and the `hub-v*` tag scheme retire.

## Limits in force this run

These **invert** the previous run's standing rule, deliberately — this run exists to publish.

1. Outward-facing actions **are** authorised, in R11/R12 order: push, PR, merge to master, tag,
   GitHub release. Still forbidden: force-push, history rewriting on a shared branch, and touching
   any tag or release that already exists.
2. **Never release on a red or still-running CI.** Every job green *and finished* before the PR
   merges; merge green before the tag exists.
3. **PyPI is irreversible.** A version number, once uploaded, can never be reused. Read both
   `pyproject.toml` version lines against `release_shape.version` before creating the tag. Anything
   that looks wrong at that moment is a stop, not a judgement call.
4. Version is **1.0.0** for both distributions; tag is **`v1.0.0`**; no `hub-v1.0.0`.
5. No new runtime dependencies beyond the one this run exists to add (`agentweave-hub` as a
   dependency of `agentweave-ai`). **pywebview remains unauthorised.**
6. Out of scope, chosen by the operator against the alternatives: driving the UI; Q6's desktop
   shell; archiving the finished openspec changes. If R12 finishes early, **stop** — do not start
   them.
7. Never mark work complete on the strength of a plan existing. Every claim measured, or labelled
   unverified.

## Driver

**OS Scheduled Task** (`AgentWeaveAutonomousSession`) running `run-iteration.ps1`, which invokes a
fresh headless `claude -p` per firing. Installed as a **backup** to the interactive session, not
instead of it: the script stands down while `last_heartbeat` is under 25 minutes old, so the two
never hold the branch at once.

Cost, stated up front: the driver runs with `--permission-mode bypassPermissions`, and its own
docstring says not to point it at a branch that matters. R11 and R12 touch `master` and PyPI. The
only guard there is the explicit precondition written into R12 and limit 2 above. If the
interactive session is alive at that point, it does R11/R12 itself.

---

## Iteration 0 — 10:14 — branch cut, driver armed

Cut `autonomous/2026-08-17-one-version-one-product` from `hub-native-experience` @ `e45b014`, tree
clean. No work done yet; this entry exists so a firing that arrives before iteration 1 has
something to read.

`STATE.json` was prepared before the run and is not re-derived here. Its `parent_sha` was corrected
from `c6aec88` to `9343a31`→`e45b014` — the prep commit itself would otherwise have been outside the
branch, which would have lost the brief.

**Time check:** PowerShell reports 10:14+01:00. Git Bash `date` reports the same instant as
`10:03 GMTST`; the skill records that Git Bash on this machine prints UTC while labelling it +0100,
so **every timestamp in this log is stamped from PowerShell**. A heartbeat written from Git Bash
would land an hour in the future and stall the driver until real time caught up.
