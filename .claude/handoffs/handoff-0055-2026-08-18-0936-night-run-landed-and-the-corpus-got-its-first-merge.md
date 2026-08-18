# Handoff: the night run landed, three UX corrections shipped, and the corpus got its first real merge

**Date:** 2026-08-18T09:36:29+01:00 · **Branch:** `autonomous/2026-08-18-the-app-feels-alive` · **HEAD:** `70a333b`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive + a Windows Scheduled Task driver run)
**Previous handoff:** `.claude/handoffs/handoff-0054-2026-08-17-2217-one-oh-one-shipped-and-the-app-runs.md`
**Status:** chunk complete. Nothing blocked. One piece of asked-for work not started (see Next steps 1).

## Goal

Make AgentWeave pleasant enough to dogfood, then start answering the questions that actually gate the
openspec→AgentWeave migration. The operator gave a ten-item queue for an overnight run, the run
executed it, and the morning was spent driving the real app and correcting what the run got wrong —
then diving into the two research documents it produced.

The *why*: the operator is migrating to developing AgentWeave with AgentWeave. A product that
interrupts you with console windows, hides its "Open project" behind a 15px icon, and cannot tell you
an agent is alive cannot be dogfooded honestly.

## Current state

**The overnight run completed in full.** 29 iterations, 65 commits, last iteration 07:56, stopped
itself at 08:00 as designed. The Scheduled Task driver is **unregistered** (verified by query).

All ten operator items were addressed: six app fixes shipped, two decide-nothing explorations
written, the dogfood translation started, and 18 iterations of Tier 2/3 roadmap work.

**Then the operator drove the real app and found three things the run got wrong**, all now fixed and
pushed:

1. **Console windows persisted.** Diagnosed as a stale process: the Hub on 8000 was PID 30868 started
   2026-08-17 21:55, four hours *before* the console fix landed at 01:53. Python loads modules at
   import; an editable install does not hot-reload a running server. **Restarting 8000 fixed it —
   operator confirmed "The cmds are fixed."**
2. **The working indicator was in the wrong place** (composer, not where the answer appears), and
   then **lingered** after the answer arrived. Both fixed.
3. **Two project-entry buttons** were the wrong model. Now one.

**Then: the research dive.** The operator read both explorations, made four decisions, and the
archiving one was executed live — producing this project's **first ever capability merge** and three
new defects. Those are written up in
`openspec/explorations/2026-08-18-the-first-real-capability-merge.md`.

**Both Hubs are running right now:**

| | Port | Database | Contents |
|---|---|---|---|
| Dev app | 8000 | `~/.agentweave/hub/data/agentweave.db` | `proj-8f100b95 AgentWeaveWebsite`, 4 agents, 4 exploring docs — **real operator work on another project, do not modify** |
| Trial | 8010 | `<repo>/hub/data/agentweave.db` | `proj-5e960453 AgentWeave`, `proj-b44fac0c Throwaway (taste pass)`, `proj-ff695d96 aw-loop10` |

Both were restarted by me this session via detached `Win32_Process.Create` from `hub/`, each with an
explicit `DATABASE_URL`. 8000's key is in `~/.agentweave/hub/.env`; 8010's is in `hub/.env`. They are
different keys and not interchangeable. Auth is `Authorization: Bearer <key>` — **not** `X-API-Key`.
`GET /api/v1/projects` returns a **bare JSON array**, not `{projects: [...]}`.

## Files touched

**This morning's interactive work** (4 commits: `9db0713`, `d94b6ee`, `8898155`, `70a333b`):

- `hub/ui/src/components/agents/AgentTimeline.tsx` — working indicator moved here from the composer;
  `runVisiblyActive` gate; `TERMINAL_STATUSES` set; `data-turn-boundary` marker on each turn root;
  per-turn "Worked for Xs" line via `durationLine`. Finished.
- `hub/ui/src/lib/agentTimelineModel.ts` — **new function** `runDurationsByRunId()`, computing
  per-run duration from lifecycle-event timestamps. Finished.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — `tailSpacer` state + layout effect;
  `scrollToNewest()` converted to `useCallback` and taught to pin the newest turn to the top;
  `TAIL_TOP_PADDING_PX`/`TAIL_BOTTOM_GAP_PX` constants; spacer div rendered before `bottomRef`.
  Finished.
- `hub/ui/src/components/agents/Composer.tsx` — indicator block and `useElapsedSeconds` import
  **removed** (moved to the timeline). Finished.
- `hub/ui/src/components/layout/Sidebar.tsx` — two project buttons collapsed to one `add-project`;
  `onOpenExisting`/`onCreateProject` props replaced by a single `onAddProject`, in both the expanded
  and collapsed rails. Finished.
- `hub/ui/src/App.tsx` — `onAddProject={() => setProjectManagerMode('open')}`. Finished.
- `hub/ui/src/components/projects/ProjectManagerModal.tsx` — title/button/copy for the single action.
  Finished. **Note:** `mode='create'` code still exists but is now unreachable from the rail.
- `hub/ui/src/__tests__/workingIndicator.test.tsx` — **new**, 15 tests. Replaces
  `composerWorkingIndicator.test.tsx`, which was **deleted**.
- `hub/ui/src/__tests__/conversationControls.test.tsx` — 2 new tests for the tail spacer.
- `hub/ui/src/__tests__/{projectRail,conversationTree,recencyView,rowMenus}.test.tsx` — updated for
  the single `onAddProject` prop.
- `hub/hub/static/ui/**` — committed build artefact, rebuilt and re-stamped twice.
- `openspec/explorations/2026-08-18-the-first-real-capability-merge.md` — **new**, the merge trial
  findings.

**From the overnight run** (61 commits, `41c8bd3`..`cfaea8d`) — the ones that matter:

- `hub/hub/subprocess_windows.py` — **new**, `no_console_kwargs()`; applied to 10 spawn sites
  (`codex_appserver`, `conversation_titles`, `launchability`, `main`, `native_dialog`, `pty_runner`,
  `requirement_evidence`, `task_integration`, `worker`, `workspace_paths`, `worktrees`).
- `src/agentweave/cli.py` (+50) and `src/agentweave/assets/icon.ico` — **new** 18 KB multi-size icon.
- `tests/conftest.py` — **new**, autouse fixture making `webview` unimportable. This is what stopped
  the CLI suite hanging forever.
- `hub/ui/src/hooks/useElapsedSeconds.ts` — **new**.
- `hub/ui/src/components/agents/ComposerSpecControl.tsx` — the reopen-an-existing-spec control.
- `openspec/explorations/2026-08-18-{what-archiving-a-spec-means,does-the-name-still-fit,claude-md-trial-hub-section-is-stale}.md`
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` (+777) — the reconciliation audit.
- `.claude/autonomous/STATE.json`, `.claude/autonomous/2026-08-18-the-app-feels-alive-log.md`.

**Untracked and deliberate** (both in `git status`, leave alone):
- `spec/` — now contains **real fixture content**: `capabilities/quiet-hours/spec.html` (7
  requirements after the merge), `capabilities/project-instructions/spec.html` (3 requirements),
  `changes/quiet-hours-for-agent-notifications/spec.html`. `CLAUDE.md` forbids committing `spec/` at
  the repo root.
- `hub/seed_taste_doc.py` — scratch from the previous session.
- `testbed/scratch/*.py` — gitignored. This session added `console_probe.py`,
  `_console_probe_worker.py`, `console_watch.py`, `db_probe.py`, `advance_state.py`,
  `run_first_merge.py`, `rigor_merge_experiment.py`, `rigor_traceback.py`.

## Key decisions

1. **Restarted the Hub rather than patching more subprocess sites.** Two console-window theories had
   already failed (the `hub/hub/` sweep; a measured `DETACHED_PROCESS` vs `CREATE_NO_WINDOW` A/B that
   produced **zero** visible windows in both arms). Checking the running process's start time found it
   predated the fix. Rejected: guessing a third time and shipping a speculative patch.
2. **Working indicator gated on lifecycle events + the streamed status line, not `agent.status`.**
   `isRunning` is a *polled* roster field. Rejected: hiding the indicator whenever text appears —
   wrong, because an agent legitimately keeps working after speaking. Two tests pull against each
   other to enforce exactly that.
3. **"Worked for Xs" computed from persisted event timestamps, not the live counter.** The counter
   measures how long *this tab* watched a run, so it is null for any turn that finished before load.
4. **One "Add project" button.** Both buttons opened the same modal onto the same folder picker;
   `open_existing` already resolves a known path, a marked directory, or a plain folder it
   initialises. Rejected: a split button, and a larger recent-projects rework (both offered, both
   declined by the operator).
5. **Tail spacer sized from the newest turn's own height**, so it shrinks to 0 as the response grows
   and bottom-following resumes with no jump. Rejected: a fixed `60vh` spacer — leaves a permanent
   void under short conversations and has to be torn out visibly.
6. **Ran the real merge (Model A) instead of reasoning further.** Operator's choice. It found three
   defects in under an hour.
7. **Left the merge fixture in place, including its damage** — 1 orphan `spec_edit_proposals` row and
   2 bogus `spec_document_merges` rows from the 500s. A populated capability document is more useful
   than a clean slate.

## Constraints and user directives (verbatim)

> *"Full auto, but only on green CI"* — carried forward from handoff 0054. **Never release on red or
> unfinished CI.**

> *"I'm going to sleep. You can handle the rest"* — the authority under which the overnight driver was
> armed.

> *"Depth over breadth"* — the operator explicitly declined breadth across all ten items. Items 1–6
> were the objective; 7 and 9 explorations only; 8 and 10 runway.

> *"Write an exploration each, decide nothing"* — for items 7 (spec archiving) and 9 (rename).

> *"Is 2 buttons the right call? Shouldn't this be decided differently? What the best UI/UX
> approach?"*

> *"I think the working should be on the composer screen not the chat box. Right where the agent is
> supposed to answer. After answering it could just look like worked for Xs and then the response
> underneath."*

> *"When we send a message the screen to scroll up and leave a big space for the response."* and
> *"Basically the message that I just sent to look like the first message."*

> *"The cmds are fixed. But the working text not. It still linger a little bit."*

> **Live agent turns:** *"cheap model, a few short turns"* — the operator's stated spend ceiling. Not
> used this session; no live agent turn was ever driven.

> **Do not touch `aw-loop10`** (`proj-ff695d96`).

From `CLAUDE.md`, still binding: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo
root; use `openspec/`, never the `aw-*` skills; stage paths explicitly; commit `hub/hub/static/ui`
together with `hub/ui/src`.

## Dead ends

- **Console windows — two theories dead before the right one.** (a) The `hub/hub/` subprocess sweep
  did not stop them. (b) `DETACHED_PROCESS` → `CREATE_NO_WINDOW` on the Hub spawn: A/B tested with a
  real `winpty` ConPTY under both flags, counting visible `ConsoleWindowClass` windows —
  **0 in both arms.** The actual cause was a stale Hub process. **Check process start times against
  fix commit times before theorising about code.**
- **Bare `python` is the wrong interpreter.** PATH `python` is
  `C:\Users\huida\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` and has no `agentweave`;
  `python -m pytest tests/` fails collection with 16 `ModuleNotFoundError`s that look exactly like a
  broken tree. **Always `py -3.11`.**
- **PowerShell must not write `STATE.json`.** `Set-Content -Encoding utf8` writes a UTF-8 BOM that
  makes `json.load()` fail outright, and `ConvertTo-Json` escapes every apostrophe to `\u0027` and
  reflows the file. Use Python (`encoding='utf-8'`); read with `utf-8-sig` if a BOM may be present.
- **Bash `cd` persists between tool calls.** Twice, a `cd hub/ui` leaked into the next command and
  made it run in the wrong directory. Use absolute paths or re-`cd` each time.
- **Complex `python -c` with nested quotes hangs the shell.** One attempt blocked for 2 minutes. Write
  a file in `testbed/scratch/` instead.
- **jsdom reports `offsetHeight === 0`.** The tail spacer initially reserved a viewport-sized void for
  an unmeasured element; the pre-existing autoscroll test caught it. Now guarded and tested.
- **`pytest tests/` hung forever before `tests/conftest.py` existed** — `webview.start()` opens a real
  window. Fixed overnight; do not remove that fixture.

## Verification

**Ran and passed, by me, this morning on `70a333b`:**
- `cd hub/ui && npm test -- --run` → **987 passed, 100 files**
- `cd hub/ui && npm run lint` → clean (`--max-warnings 0`); `npx tsc --noEmit` → clean
- `npm run build` + `py -3.11 scripts/refresh_ui_bundle.py` → bundle rebuilt and stamped; verified the
  Hub serves the same asset hash that is on disk
- `py -3.11 -m pytest hub/tests/ -q` → **2337 passed, 11 skipped, 1 xpassed** (759s)
- `py -3.11 -m pytest tests/ -q` → **385 passed, 3 skipped, 1 failed**

**The one CLI failure is pre-existing and not from this work.**
`tests/test_packaging.py::test_wheel_ships_skill_reference_docs` asserts
`agentweave/templates/skills/references/html-spec-conventions.md`, which commit `a44c8a8`
(2026-08-12) deliberately deleted. It only ever passed because a stale, gitignored `build/lib/`
directory kept resurrecting deleted files into locally-built wheels; the overnight run's `rm -rf
build` unmasked it. **I verified the published wheel is unaffected:** downloaded
`agentweave-ai==1.0.1` from PyPI, 56 entries, no `transport/git.py`, no `transport/local.py`, no
watchdog/messaging/runner. CI builds from a clean checkout.

**Mutation-checked:** reverting `runVisiblyActive` to `isRunning` in `AgentTimeline.tsx` fails exactly
one named test and nothing else.

**NOT tested:**
- **No live agent turn was ever driven this session.** The working indicator, "Worked for Xs", the
  scroll pinning and the end-of-turn message removal have **never been watched against a real run** —
  only unit tests and the operator's own eyeballing of earlier versions.
- **CI has never run on this branch**, nor on `master` at `1e0d08e`.
- The taskbar icon has never been seen on a real taskbar.
- The taste pass: **18 items still unjudged.**
- Nothing from the overnight run was independently re-derived beyond re-running its suites.

## Git state

- **Branch:** `autonomous/2026-08-18-the-app-feels-alive`, **HEAD:** `70a333b`, up to date with
  origin. **No unpushed commits.**
- **Dirty:** two untracked paths only — `spec/` and `hub/seed_taste_doc.py`. Both deliberate.
- **69 commits ahead of `master`** (`1e0d08e`). **Not merged.**
- Tags unchanged: `v1.0.0` → `ff16a62`, `v1.0.1` → `5e63004`.
- Driver `AgentWeaveAutonomousSession`: **unregistered**, verified.

## Next steps

1. **Explore candidate names — the one piece of asked-for work not started.** The operator chose
   *"Explore names, decide nothing yet"*: generate and pressure-test candidates for both the product
   name and the "hub" term, with metaphor implications spelled out, so they choose between concrete
   options. Ground it in `openspec/explorations/2026-08-18-does-the-name-still-fit.md` (already
   written — §1 has the architectural evidence, §3 the six-surface cost table) and
   `2026-08-15-where-agentweave-fits.md`. Write to
   `openspec/explorations/2026-08-18-candidate-names.md`. **Recommend nothing.**
2. **Fix the merge 500.** `hub/hub/api/v1/spec.py:1190` does
   `return {**_document_view(document), "blocking": result.blocking, ...}` — but `save_document()`
   returns a `ProposeResult` (no `.blocking`) whenever the document's rigor is `contract`/`gate`, and
   `await session.commit()` on line 1186 runs *first*, so the proposal is durably written and then the
   request 500s. Branch on the result type. Add the `rigor` cases to `hub/tests/test_spec_merge.py`,
   which currently has zero references to it.
3. **Decide what to do about `requirement_without_task` on capability documents** — see Open questions.
4. **Drive one real agent turn** on the trial Hub (cheap model) to actually watch the indicator, the
   scroll pinning and the silent turn end. Everything in step-1..3's neighbourhood is currently
   verified only by unit tests.
5. **Decide the branch.** 69 commits, unmerged, CI never run on it.

## Open questions for the user

- **`requirement_without_task` on capability documents.** Every requirement in a `current`-phase
  document is permanently blocking, because the rule asks what implements it and shipped behaviour has
  nothing left to implement it. Exempt capability documents, replace it with a merge-provenance rule
  ("every requirement traces to a cited source change"), or accept blocking as cosmetic for `current`?
- **The rigor coupling.** The *behaviour* (review a gated merge requirement-by-requirement) is
  defensible; the *implementation* 500s. Fix the implementation and keep the behaviour, or make merges
  ignore rigor entirely?
- **The orphan fixture damage.** `proj-5e960453` holds 1 stranded `spec_edit_proposals` row and 2
  bogus `spec_document_merges` rows from the crashed requests. Clean them, or keep them as a
  regression fixture?
- **D2/D3/D4 from handoff 0054 remain open** — taste-pass live turns, retro-covering 1.0.1, and the
  `agentweave-hub>=1.0.0` pin. Operator answered "None yet" on 2026-08-18.
- **N3:** `CLAUDE.md`'s Specifications section is **factually wrong** — it says AgentWeave has "no
  archive phase and no concept of a current-behaviour specification", but five phases shipped
  2026-08-16. A corrected section is proposed in
  `openspec/explorations/2026-08-18-claude-md-trial-hub-section-is-stale.md`, deliberately not applied.

## Read on resume

- `openspec/explorations/2026-08-18-the-first-real-capability-merge.md` — the three defects the merge
  trial found, with the measured before/after. Next steps 2 and 3 both come from it.
- `openspec/explorations/2026-08-18-what-archiving-a-spec-means.md` — answers the operator's three
  archiving questions with code evidence; §1 is the sharpest part.
- `openspec/explorations/2026-08-18-does-the-name-still-fit.md` — the input for next step 1.
- `.claude/autonomous/2026-08-18-the-app-feels-alive-log.md` — 29 iterations, oldest first. Each entry
  has a "what a reviewer should distrust" section.
- `.claude/autonomous/STATE.json` — 12 queue items (11 done), 13 limits, 6 decisions, `known_debts`.
- `hub/hub/api/v1/spec.py:1127-1190` — the merge endpoint; line 1190 is the 500 in next step 2.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — tail spacer and scroll logic, the file most
  likely to need adjustment once a real turn is watched.
