# Handoff: eight changes closed, a browser suite built, and the backlog down to two

**Date:** 2026-08-18T20:51:40+01:00 · **Branch:** `master` · **HEAD:** `be26142`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0057-2026-08-18-1602-the-explore-that-overturned-the-unattended-design.md`
**Status:** chunk complete. Nothing blocked. **Two PRs merged this session; working tree clean but for one untracked file.**

## Goal

Close out the accumulated openspec backlog. Handoff 0057 left ten changes in
`openspec/changes/`, seven of them finished except for "Human-only verification" sections —
taste calls no agent may make. The *why*: those sections mix two different claims in one
checkbox ("a plain job's card shows no loop block" is objective; "does it read as a second
competing concept" is not), and the objective halves had been parked for weeks alongside the
subjective ones. Automate the first kind, get the operator to judge the second, and archive.

## Current state

**`openspec/changes/` went from 10 in-flight to 2.** Eighty-eight changes are archived. The
capability corpus is 32, all validating strict.

**Everything that remains to implement is these two changes, and neither has been started:**

| Change | Open | Done |
|---|---|---|
| `openspec/changes/2026-08-18-a-loop-writes-its-own-queue` | 95 | 0 |
| `openspec/changes/2026-08-18-one-shell-three-panels` | 37 | 0 |

**132 tasks, zero implemented.** That is the whole backlog. Nothing else is pending in
openspec, and nothing is mid-flight on the trial Hub (`spec/` holds two `current` capability
documents and one `archived` change-spec; nothing in `proposed` or `exploring`).

**`hub/tests/browser/` exists and works** — 33 Playwright checks, 33 passed against a live
Hub, and the package is invisible to CI (see Verification for the important nuance).

**The trial Hub is running right now** on `:8010`, PID **12496**, serving
`hub/data/agentweave.db`. It is an **orphaned `uvicorn`** — its parent CLI and pywebview
window were killed and the server survived. It will not restart itself if killed.

## Files touched

**Committed and merged** (`7657c42`, `4cb07c4`, `11b28ca`, `8650cc5`, merged as `be26142`):

- `hub/tests/browser/conftest.py` — **new.** Fixtures: `hub_url`, `api_key`, `project_id`,
  `api` (stdlib-only JSON client), `hub_is_live`, `browser`, `page`, `goto`, `goto_settings`.
  Holds `FORBIDDEN_PROJECT_IDS = {"proj-ff695d96"}` as an executable guard on "never touch
  aw-loop10". Finished.
- `hub/tests/browser/test_job_loop_block.py` — **new.** 4 tests, `many-named-loops` 8.1. Finished.
- `hub/tests/browser/test_capability_phase_bar.py` — **new.** 8 tests, `corpus` 10.2. Finished.
- `hub/tests/browser/test_command_palette.py` — **new.** 8 tests, `conversation-formatting` 6.4. Finished.
- `hub/tests/browser/test_delete_project.py` — **new.** 5 tests, `delete-project` 6.1 + 6.2. Finished.
- `hub/tests/browser/test_coverage_rejected_state.py` — **new.** 3 tests, `spec-legibility` 7.5a. Finished.
- `hub/tests/browser/test_spec_surface_styling.py` — **new.** 5 tests, `spec-legibility` 7.2a
  and `board` 5.2a. Finished.
- Seven `openspec/changes/*/tasks.md` — human-only sections ticked, three unrunnable checks
  annotated with why. All seven now under `openspec/changes/archive/2026-08-18-*`.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 48 open → 5; reconciliation
  audit table added at the top; 12.2 marked superseded; 16.2 carries the delta-to-successor
  mapping. Now at `openspec/changes/archive/2026-08-18-2026-07-30-hub-native-experience/`.
- `openspec/specs/` — 31 → 32. `agent-loops/spec.md` **new**; updates to
  `task-lifecycle-governance`, `spec-document-authority`, `local-project-workspace`,
  `agent-conversation-workspace`, `hub-workspace-shell`, `app-lifecycle`.

**Untracked, deliberately left:** `hub/seed_taste_doc.py` — the only dirty path. `ruff` fails
on it (`I001` at line 18) and it is invisible to CI only because it is untracked. Do **not**
commit it where it sits.

**Not in git** (screenshots, `testbed/scratch/` is its own repo):
`testbed/scratch/shots/` — `delete-project-dialog-{light,dark}.png`,
`live-turn-{light,dark}.png`, `jobs-expanded.png`, `root-light.png`.

## Key decisions

1. **`hub-native-experience` archived with `--skip-specs`.** Eight of its ten delta specs
   would have entered the corpus as *new* capabilities duplicating behaviour already held
   under successor names — `spec-traceability` is `requirement-traceability` near 1:1;
   `hub-native-runtime` is spread across `app-lifecycle`, `runtime-diagnostics`,
   `usage-accounting`, `agent-run-sandboxing`. Corpus would have gone 32 → 40 with ~32
   duplicated requirements. *Rejected:* plain `openspec archive`, which would have made
   coverage ambiguous; and a selective per-requirement merge, which the operator did not ask
   for. The full mapping table is in the archived `tasks.md` under 16.2.
2. **Three checks left unticked rather than closed on a substitute.** `conversation-formatting`
   6.5 (no conversation on this machine predates 2026-08-16), `one-hub` 6.4 (needs WebView2
   genuinely absent), `one-hub` 6.1's Docker third (no daemon). Each carries its reason in the
   archived file. *Rejected:* ticking them because the operator said "they all pass" — they
   could not have been exercised.
3. **12.2 recorded as superseded, not done.** It asked for composer controls collapsing into
   an overflow menu; `design.md` Decision 5 rejected that and `Composer.tsx` says why:
   *"Nothing leaves the row at any width; a control that disappears when the pane narrows is
   one the operator cannot find."* Ticked so the archive is reachable, annotated so it is not
   re-implemented later as an oversight.
4. **The browser suite is opt-in via `AW_HUB_URL`, never a gate.** A suite needing a live Hub
   and a hand-seeded database is a tool, not a CI check. *Rejected:* running it in CI, which
   would need a Hub, a browser and fixtures in the runner.
5. **Every assertion written so it cannot pass vacuously.** Three earlier drafts went green
   while proving nothing (see Dead ends). Helpers now assert their own preconditions.
6. **Tests assert the factual half and hand the taste half to the operator**, saying so in
   each docstring. `board` 5.2 gets a printed property diff rather than a verdict.

## Constraints and user directives (verbatim)

> *"I want you first to clean the branches on the environment"*

> *"they all pass for now."* — the operator's judgement on the parked human-only tasks.

> *"--skip-specs then"*

> *"Do not call the AgentTool unless the user requested it"* · *"Do not use workflows or
> deep-research unless the user requested it"*

Still binding from `CLAUDE.md` and earlier sessions: **"Full auto, but only on green CI"** —
never merge or release on red or unfinished CI. **Never point the Hub you are editing at this
repo.** Use openspec, never the `aw-*` skills. **Stage paths explicitly, never `git add -A`.**
Always `py -3.11`. T3 source in `testbed/scratch/t3ref/` is **design reference only — study,
never copy, never commit.** **Do not touch `aw-loop10` (`proj-ff695d96`)** — now enforced in
code by `FORBIDDEN_PROJECT_IDS` in `hub/tests/browser/conftest.py`. `.agentweave/` and `spec/`
at the repo root are the migration's, not stray output. Never commit `kimichanges.md`,
`kimiwork.md`.

## Dead ends

- **`page-jobs`, `page-tasks`, `page-spec` do not exist in the running app.** They are mocks
  inside `hub/ui/src/__tests__/App-mount.test.tsx`. Grepping `hub/ui/src` without excluding
  `__tests__` reports 104 test ids; production markup has **71**. Built the whole navigation
  fixture on them and lost a full run. It also produced a false "the UI bundle is stale"
  alarm — the bundle is current.
- **`count()` does not auto-wait, and neither do conditional guards.** Two separate false
  greens from this: clicks landing before React hydrated so no card ever opened (making
  "plain job has no loop block" pass on a page with *zero* loop blocks), and
  `if toggle.count(): click()` silently skipping so a **light** screenshot was written to a
  file named `dark`. Use `expect(...)` before acting, and assert the post-condition.
- **PowerShell here-strings (`@'...'@`) are a syntax error in the Bash tool.** Used one for a
  commit message; bash executed the body line by line and produced a commit whose subject was
  a bare `@`. Had to amend. Write the message to a file and use `git commit -F`.
- **`Remove-Item` with a *variable* path is blocked by a guard** ("Remove-Item on system path
  '/' is blocked"), regardless of what the variable holds. Literal paths work. Cost two failed
  cleanup attempts.
- **`$(pwd)` in Git Bash yields `/c/Users/...`, which aiosqlite cannot open.** `CLAUDE.md`'s
  documented trial-Hub start command fails in this shell with "unable to open database file".
  Use the Windows path form.
- **Launching `agentweave` from a directory containing `hub/` silently produces no server.**
  `CLAUDE.md`'s documented shadowing trap, hit live: parent alive, nothing on the port, zero
  log output. Launch from a neutral cwd (`C:\Users\huida`).
- **The first live agent turn read nothing.** A writing agent gets an isolated git worktree, so
  **untracked files in the project directory are invisible to it**. The files staged for it
  were untracked. The agent handled it correctly and asked what to do.

## Verification

**Ran and passed, this session:**

- `py -3.11 -m pytest tests/ -q` → **385 passed, 3 skipped** (19.41s).
- Browser suite with a live Hub → **33 passed** (17.04s). Without `AW_HUB_URL` → **33 skipped**
  (0.08s).
- `npx openspec validate --changes --strict` → **2 passed, 0 failed**.
  `--specs --strict` → **32 passed, 0 failed**.
- `py -3.11 -m black --check src/ hub/hub/ hub/tests/ tests/` → **403 files unchanged**.
- `py -3.11 -m ruff check src/ hub/ tests/` → 1 error, **only** in untracked
  `hub/seed_taste_doc.py`.
- **PR #3 merged** (`ae7cb3a`) on 9/9 green. **PR #4 merged** (`be26142`) on 9/9 green;
  `hub-test` 6m26s reported **2335 passed, 17 skipped, 1 xfailed**.
- **CLI checks driven for real:** `one-hub` 6.7 (exit 1, legible message naming both flags),
  6.6 (dual-profile isolation; `reset --profile awtest` deleted only that profile —
  `beta`/`dev`/`trial`, default data and `.env` all survived), 6.1 native-from-two-directories
  and direct-`uvicorn` both reaching the same database, 6.3 (the pywebview-free `.venv` starts
  the Hub and **returns** instead of blocking).
- **Two live Haiku runs on the trial Hub**, ~$0.08 total — the first ever driven there,
  outstanding since handoff 0055. Second produced `Read, Read, Read, Bash, Edit`.

**NOT tested / not done:**

- **CI does not actually skip the browser suite item-by-item — it never collects it.**
  `pytest.importorskip` in the conftest drops the whole directory at collection when Playwright
  is absent. There is no `tests/browser` line in the `hub-test` log at all, and the 17 skips
  are all pre-existing. **Consequence: a syntax error in `hub/tests/browser/` would also vanish
  silently rather than fail CI.** Verified by reading the job log, not assumed.
- **Neither of the two remaining changes has one line implemented.** 132 tasks, 0 done.
- `mypy` was not run. `ci.yml` does not gate on it.
- **`conversation-formatting` 6.5, `one-hub` 6.4 and 6.1's Docker third were never exercised** —
  see Key decision 2.
- **`hub-native-experience` archived carrying 5 open tasks**: section 14's three partials
  (14.5, 14.13, 14.18) and 15.3, whose approval/permission card was read in source but **never
  driven live**.
- The full `hub/tests/` suite was not re-run locally after the final markdown-only commits; CI
  ran it.

## Git state

- **Branch:** `master`, **HEAD `be26142`**, tracking `origin/master`, **0 unpushed**.
- **Dirty:** one untracked path only — `hub/seed_taste_doc.py`. Deliberate.
- **Both PRs merged and their branches deleted**, local and remote:
  `autonomous/2026-08-18-loops-and-side-panels` (PR #3, merge commit `ae7cb3a`) and
  `verification/2026-08-18-browser-suite-and-human-checks` (PR #4, merge commit `be26142`,
  merged 19:50:49Z). Both verified 0-commits-ahead before local deletion.
- **Branches now: `master` only**, local and remote — plus `agentweave/q2verify`, which is
  **product state, not cruft**: the AgentWeave Hub recreated it during the live agent run. Its
  worktree is `testbed/throwaway-taste-project/.agentweave/worktrees/q2verify` at `819abe6`
  ("Auto-snapshot: q2verify's turn"), holding the agent's README edit.
- **Branch cleanup earlier in the session: 9 deleted** — `agentweave-1-0` (was `21aeea0`, one
  file `spec/agentweave-1.0-spec.html`, 3,980 lines, **recoverable ~30 days** via
  `git branch agentweave-1-0 21aeea0`), `agentweave/q2verify` (since recreated by the product),
  and 6 identical-to-`main` branches in `testbed/two-codex-agents/workspace`.
- **~370 MB reclaimed**: `.venv-linux/` (a WSL venv, unusable from Windows), both mypy caches,
  4 stale `hub/data/agentweave.db.{bak,old}-*` snapshots, 3 dead PID files, build/dist/caches.
  `hub/data/agentweave.db` and `instance_identity.json` untouched.

## Next steps

1. **Start the panel shell — `openspec/changes/2026-08-18-one-shell-three-panels/tasks.md`
   section 1.1.** Create the per-project tab store: which tabs are open, their order, which is
   visible, whether the shell is open; keyed by project id; persisted to `localStorage` under a
   **versioned** key. New file, suggested `hub/ui/src/store/panelTabsStore.ts`, following the
   Zustand pattern in `hub/ui/src/store/configStore.ts`. The file states 1 → 2 → 3 ordering is
   load-bearing and says why; the loop change's B5/B6 depend on this landing first.
2. **Decide `hub/seed_taste_doc.py`** — leave untracked, or `git mv` it to `testbed/scratch/`.
   Do **not** commit it where it is: `ruff` fails and CI goes red.
3. **Consider an import-check for `hub/tests/browser/`** so CI catches a syntax error there —
   currently it cannot (see Verification).
4. **Fix `agentweave status`/`stop` misclassifying a native uvicorn as Docker.** Reproduced:
   `status --port <p>` reports `running (docker)` for a directly-launched
   `python -m uvicorn hub.main:app`; `stop` then fails against the Docker API and **leaves the
   process running**. Root cause: a direct uvicorn writes no PID file, so the CLI falls back to
   assuming Docker. Not yet filed as a change.

## Open questions for the user

- **The D15 name-reuse hole** — a new agent taking an archived agent's name inherits its
  creator privilege. Open since handoff 0056; should close before control delegation is relied on.
- **Whether an agent should be able to archive a bare job at all**, even behind an approval
  card. Loop-change D18 settles that the path always asks; it deliberately does not settle
  whether the path should exist.
- **Two explorations from today that never became a change** —
  `openspec/explorations/2026-08-18-candidate-names.md` and
  `openspec/explorations/2026-08-18-does-the-name-still-fit.md`. If these are a live question
  about renaming the product, it is worth settling **before** building 132 tasks of UI on the
  current name.
- **Two things the panel change refuses to invent**: the `files` tab's minimum width and
  tab-strip overflow behaviour. Both need measuring against a running shell (tasks 5.5, 6.1).

## Read on resume

- `openspec/changes/2026-08-18-one-shell-three-panels/tasks.md` — **read first.** Where
  implementation starts; the 1 → 2 → 3 ordering is load-bearing and the file says why.
- `openspec/changes/2026-08-18-one-shell-three-panels/design.md` — D1–D12. **D6 is a withdrawal
  notice, not a decision.**
- `openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md` — the design
  conversation that overturned six unattended decisions; §0 is the table.
- `hub/tests/browser/conftest.py` — how to run the browser suite, why it is opt-in, and the
  two hydration traps documented in `goto`.
- `hub/ui/src/store/configStore.ts` — the Zustand + persistence pattern next step 1 should follow.
- `hub/ui/src/components/agents/ConversationView.tsx` — `:34-38` the derived breakpoint,
  `:150-291` the hosting block that becomes the shell.
