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

---

## Iteration 1 — 10:20 — R1: the CI job that has been red since July

**Done.** `.github/workflows/ci.yml`, two jobs touched.

`hub-test` sets `working-directory: hub` as a job default and only ever installed the Hub, so the
four Hub tests that import `agentweave` — `test_agent_output_stream.py`, `test_session_sync.py`,
`test_task_transitions.py`, `test_agent_tool_surface_phase7.py` — died with
`ModuleNotFoundError: No module named 'agentweave'`. That is the exact failure sitting on master
since 2026-07-29. It passes on this machine only because the CLI is installed editable
machine-wide, which is a property of the machine and not of the repository. Added a step with an
explicit `working-directory: .` that installs the root package.

**Found while doing it — a chicken-and-egg R1 had to absorb.** R4 will make `agentweave-ai` depend
on `agentweave-hub`. Once it does, `pip install -e ".[dev]"` at the root asks PyPI for
`agentweave-hub>=1.0.0`, which will not exist until this very commit is released — so CI would need
the release and the release would need CI. Both jobs now install the Hub **from this checkout
first**, which satisfies the requirement before pip ever looks outward. In `hub-test` that meant
putting the CLI install *after* the Hub install, not before, which is the opposite of the order I
first wrote.

**Checked, not assumed:**

- The CLI suite does not need the Hub installed. `tests/test_hub_commands.py:437` stubs
  `sys.modules["hub.main"]` *deliberately*, and its docstring explains why: this repo's `hub/`
  directory has no top-level `__init__.py`, so a bare `import hub` from the repo root can resolve
  to it as an implicit namespace package instead of the installed `agentweave-hub`. The stub is
  independent of what is installed, so adding the Hub to that job cannot disturb it.
- The `build` job is unaffected: `python -m build` reads metadata and does not resolve runtime
  dependencies.
- The workflow still parses, and step order is right — verified by loading it with `yaml.safe_load`
  and printing each job's steps with their effective working directory, rather than by reading it.

**Distrust this until R11.** GitHub Actions cannot be run locally. Everything above is reasoning
over the workflow file; the first real evidence is the PR run. R1 is the one queue item whose
verification is deferred by construction.

---

## Iteration 2 — 10:28 — R2: docs build green, 34 warnings to zero

**Done, and verified by running it.** `mkdocs build --strict` now completes with **zero warnings**
in 0.47s. It has been red since 2026-07-29.

The 34 warnings had four causes, not thirty-four:

- **29 — the legacy archive.** `docs/archive/legacy-multi-runtime/` was moved wholesale at some
  point and its relative links were never rewritten, so every `../reference/foo.md` inside it now
  resolves to `archive/reference/foo.md`. 28 broken links plus one "pages not in nav" listing the
  same tree. **Excluded the tree from the built site** via `exclude_docs` and dropped its nav entry.
  The files stay in git — `git ls-files` still lists all 21 — they are simply no longer published.
  Repairing 28 links would have made a deleted product's manual navigable: it documents the
  watchdog, both dead transports, the role subsystem and the multi-runtime CLI, none of which exist.
- **3 — `docs/guides/aw-spec-workflow.md`.** Deleted, with its `mkdocs.yml` nav entry. The skill it
  documents is gone (`src/agentweave/templates/skills/` has no `aw-spec-workflow`) and so is the
  `references/` directory it linked into.
- **1 — `docs/contributing/development.md:87`**, linking `../guides/adding-new-agents.md`. Replaced
  the sentence rather than the link: agents are created in the app now, so there is no file to add
  one to, and the useful pointer is to the runner/MCP-tool/UI-component recipes in `CLAUDE.md`.
- **1 — `docs/reference/hub-api.md:149`**, linking `../guides/ai-jobs.md`. Same treatment; replaced
  with a sentence saying where jobs are managed and noting that a job carrying a purpose and a stop
  condition *is* a loop, which is the shape N3 shipped.

**Checked, not assumed:** the two archive sections that were NOT excluded — `2026-q2-hardening` and
`autonomous-dev-loop` — still build into `site/archive/`, and `site/archive/legacy-multi-runtime`
does not exist. `site/` is gitignored (`.gitignore:50`), so the build leaves no residue.
