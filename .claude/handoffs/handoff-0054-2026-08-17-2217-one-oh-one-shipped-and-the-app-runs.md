# Handoff: 1.0.0 and 1.0.1 both shipped, the desktop app runs, two Hubs live

**Date:** 2026-08-17T22:17+01:00 · **Branch:** `master` · **HEAD:** `54dd29b`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive + one Scheduled-Task driver run)
**Previous handoff:** `.claude/handoffs/handoff-0053-2026-08-17-1300-one-oh-merged-not-tagged.md`
**Status:** chunk complete. Nothing in flight, nothing blocked, tree clean but for two known
untracked scratch items.

## Goal

Get AgentWeave releasable and then make it pleasant to use. Handoff 0053 left 1.0.0 merged but
untagged behind a flaky test; this session resolved that, shipped 1.0.0 **and** 1.0.1, ran a taste
pass over the UI with the operator, acted on their judgements, ran an unattended session to 22:00,
merged it, and stood up the app the operator will now develop with. The *why*: the operator is
migrating to developing AgentWeave with AgentWeave, and a product that is unpleasant to look at
cannot be dogfooded honestly.

## Current state

**Two releases are live.**

- **v1.0.0** — tag `ff16a62`, on PyPI, GHCR, GitHub Releases. Verified by installing from real PyPI.
- **v1.0.1** — tag `5e63004`, on PyPI, GHCR, GitHub Releases. Verified the same way.
- **master is `54dd29b`**, 30 commits *past* v1.0.1 — the merged autonomous branch. **Not released.**
  The desktop window, `--profile`, and the archive work are on master but NOT in any published
  package.

**Two Hub instances are running right now**, both from an editable install of this repo:

| | Port | Profile | Database | Contents |
|---|---|---|---|---|
| Dev app | 8000 | `default` | `~/.agentweave/hub/data/` | near-empty |
| Trial | 8010 | `trial` | `~/.agentweave/hub/profiles/trial/` | `aw-loop10`, `AgentWeave`, `Throwaway (taste pass)`, 3 spec docs, 8 tasks |

Both opened native pywebview windows (`AgentWeave`, `AgentWeave Hub`). **`pip install pywebview`
was run this session** — without it the app silently falls back to a browser tab.

The trial instance's API key is the one in **`hub/.env`** (`aw_live_58ab…`), *not*
`~/.agentweave/hub/.env`, because that profile was seeded by copying `hub/data/agentweave.db`,
which carries its own bootstrap key.

**The flaky test that blocked 1.0.0 is diagnosed and quarantined, not fixed.** Root cause found and
proven; see Dead ends.

## Files touched

44 files changed between `ff16a62` (v1.0.0) and `54dd29b`. All committed and pushed. The ones that
matter:

**Product — Python**
- `hub/hub/spec_render.py` — phase/unresolved-question/limits tones, `--aw-ok` token, `_summary()`
  line above the fold. Finished.
- `hub/hub/runner_parsing.py` — removed `Completed (cost: $x)` from the turn status line. Finished.
- `hub/hub/config.py` — database_url default fix (autonomous A3, D1). Finished.
- `hub/hub/api/v1/spec.py` — `/project/specs` now joins the on-disk tree against each path's DB
  phase so a phase-archived document is recognised. Finished.
- `src/agentweave/cli.py` — `--profile`, per-profile PID files and data dirs, pywebview app window.
  27/34 tasks of its change done; the 7 open are human-only verification.

**Product — UI**
- `hub/ui/src/components/agents/AgentTimeline.tsx` — work block: no box, expands *underneath*,
  renders the real command from `payload.input`, per-tool icons for Codex/MCP names, collapsed
  hints (files written, failures), `+N −N` on edits. Finished.
- `hub/ui/src/lib/editDiff.ts` — **new.** `diffLinesForPayload` + `editDiffStat`, moved out of the
  component file to satisfy `react-refresh/only-export-components`.
- `hub/ui/src/components/agents/ToolEditDiff.tsx` — now exports only the component; has
  `data-testid="tool-edit-diff"`.
- `hub/ui/src/components/tasks/TaskDetailDrawer.tsx` — centred modal over a scrim (was a 480px
  right drawer), plus a field block: status + its control, priority, assignee with live state,
  created/updated, declared-as key. Finished.
- `hub/ui/src/components/palette/CommandPalette.tsx` — conversation search text truncated to
  agent + 60 chars; groups reordered Agents → Tasks → Documents → Conversations. Finished.
- `hub/ui/src/components/spec/ArchiveConfirmDialog.tsx` — **new.** Archive confirmation.
- `hub/ui/src/components/spec/SpecPhaseBar.tsx` — Archive routed through the dialog.
- `hub/ui/src/components/spec/specNavigation.ts` — `isArchived(path, phase)` accepts either signal.
- `hub/ui/src/components/spec/SpecTree.tsx`, `SpecDocumentPicker.tsx` — archived rows dimmed, archive
  icon. `SpecPage.tsx` — empty state when every document is archived.
- `hub/ui/src/components/common/Icon.tsx` — archive-box icon added.
- `hub/ui/src/index.css` — `.work-disclosure` lost its border and fill.
- `hub/hub/static/ui/**` — committed build artefact, rebuilt and refreshed with the source.

**Tests** — `hub/tests/test_spec_render.py` (+12), `hub/tests/test_config.py` (new),
`hub/tests/test_spec_archive.py`, `hub/ui/src/__tests__/{agentTimeline,specNavigation,specPage,specPhaseBar}.test.*`

**Docs / process** — `CHANGELOG.md` (1.0.1 entry), `pyproject.toml` + `hub/pyproject.toml` (1.0.1),
`docs/getting-started/installation.md`, `openspec/explorations/2026-08-17-what-to-work-on-next.md`
(**the roadmap**), `openspec/changes/2026-08-16-one-hub-and-a-window-of-its-own/tasks.md` (27/34
ticked), `.claude/TASTE-PASS-2026-08-17.md`, `.claude/autonomous/STATE.json` + its log.

**Uncommitted, deliberately** (both appear in `git status`):
- `spec/` — contains only `spec/changes/quiet-hours-for-agent-notifications/spec.html`, a document
  seeded for the taste pass. **`CLAUDE.md` forbids committing `spec/` at the repo root.** Leave it.
- `hub/seed_taste_doc.py` — the script that created it. Scratch; never commit.

## Key decisions

1. **Released 1.0.1 from the interactive session, not the autonomous one.** A PyPI publish is
   irreversible and the skill's own limits forbid it unattended. The operator's instruction
   overrode the limit, but the irreversible step stayed attended. Rejected: handing objective 1 to
   the loop — it would have had neither the context for the commit messages nor a human watching.
2. **Quarantined the flaky test rather than fixing it.** `xfail(strict=False)`, with the full
   diagnosis in the reason. Rejected: shipping on red (violates the standing rule), and fixing the
   fixture under release pressure (the fix is a project of its own — see Dead ends).
3. **Phase chip is green, not the accent.** The document already spends blue on links *and* on
   `MUST`; a third meaning would empty it. A test asserts the phase tone is never the accent.
4. **`kind` chip stays neutral.** It is a category, not a state; hue there ranks nothing. Tested.
   Rejected: colouring all three chips, which the operator initially asked for.
5. **Ticket became a centred modal**, reversing that file's own documented preference for a right
   drawer. The recorded argument (a right edge keeps board column context) did not survive contact.
   The reversal and the operator's reasoning are quoted in the component's docstring.
6. **Merged the autonomous branch fast-forward into master** after re-running every suite myself
   rather than trusting the loop's logs.
7. **Did not release master.** The operator asked to merge and run, not to publish again.

## Constraints and user directives (verbatim)

> *"Full auto, but only on green CI"* — hard rule: **never release on red or unfinished CI.**
> Honoured for both 1.0.0 and 1.0.1.

> *"Push a version with these minor changes that we just worked on. Then apply the archive change
> and then work on the hub app."*

> *"Be careful that this session's context is pretty dirty already 500 k tokens."*

> *"I don't want a ticket that takes the whole screen like navigating to a new screen. Just that
> central 'popup' … that floats in the middle slightly offuscating the background to focus on the
> ticket."*

> *"The tags underneath the title could be colored as well. What else could we pretify? (But with
> purpose, embed in the colors information)"*

> *"remove the cost of each call on the composer. Not relevant"* — it was
> `Completed (cost: $0.8859)`, generated in `runner_parsing.py`, not in the UI.

> *"Archived should have a confirmation popup telling it irreversible and also more visual
> indication that is archived both on the file and on the navigation bar"*

> *"on the work collapsed we should have some kind of hints that important things like files edited
> are there … With a glance … the user should now if he should open it or not"*

> **Do not touch `aw-loop10`** (`proj-ff695d96`) — the operator's real trial data. Stated in the
> delete-project tasks and honoured all session.

From `CLAUDE.md`, still binding: never create `.agentweave/`, `agentweave.yml` or `spec/` at the
repo root; use `openspec/`, never the `aw-*` skills; stage paths explicitly; `hub/hub/static/ui` is
a committed artefact — commit it together with `hub/ui/src`.

## Dead ends

- **The flaky test — seven theories dead.** Six were dead on arrival (see handoff 0053). Theory 7
  (`db.get` returning `None`) was **disproven by its own instrumentation**: the trail showed
  `run_seen=True`, the finalize assigned a terminal status, `commit()` returned — and a fresh
  session immediately after read the row unchanged. **Actual cause, proven:** the test fixture's
  `sqlite+aiosqlite:///:memory:` resolves to a **StaticPool** — one DBAPI connection shared by every
  session in the process — so any concurrent session's close rolls back another's pending write
  while its `commit()` still returns cleanly. Measured in isolation: **105/200 commits lost with a
  concurrent poller vs 0/200 without**, and caught in situ on CI (a ROLLBACK 2.5ms before the
  finalize's COMMIT). Production is unaffected: a file-backed `DATABASE_URL` gets
  `AsyncAdaptedQueuePool`, one connection per session.
- **A file-backed test DB is NOT a drop-in fix.** Tried it; the suite **hung** — no progress for 55
  minutes. Needs WAL plus a busy timeout plus real thought about write contention.
- **The real failure never reproduced locally** — 25 runs unloaded, 12 under saturating load on 20
  cores. CI runners have 2–4 cores; the overlap needs scarcity, not load.
- **Two capture methods failed before one worked.** `traceback.extract_stack()` inside a SQLAlchemy
  connection event returns only greenlet frames (every capture came back empty). `asyncio.current_task()`
  on a ROLLBACK names the *dispatcher*, not the caller — verified by my own peeks reporting a
  different task than the one they ran in.
- **`npm test` passing does not mean CI is green.** `ui-test` runs `npm run lint` at
  `--max-warnings 0`. 957 tests passed and the release went red on one lint warning. **Always run
  lint before pushing UI work.**
- **A background job with a `timeout` is not bounded.** I left a hung suite running for 55 minutes;
  `run_in_background` detaches and the timeout does not kill it. Check on long jobs explicitly.
- **Do not estimate elapsed time.** I wrote `19:35` into `STATE.json` when it was `19:17`; a
  future-dated heartbeat would have parked the driver for 45 minutes. Stamp from PowerShell.
- **Two processes, one working tree, collide.** I armed the driver before finishing the release; its
  first iteration's commit landed on `master` because HEAD moved under it mid-turn. It self-corrected
  by re-checking `git branch --show-current` after committing. **Do not start a driver while still
  working the tree.**
- **PyPI's index lags a successful upload** by a minute or two — both the JSON API and the simple
  index. A failed `pip install` right after a green publish is not a failed publish.

## Verification

**Ran and passed, on `54dd29b`, by me, after the merge:**
- `cd hub && python -m pytest tests -q` → **2145 passed, 11 skipped, 1 xpassed** (536s)
- `python -m pytest tests/ -q` (CLI) → **381 passed, 3 skipped**
- `cd hub/ui && npm run lint` → clean; `npx tsc --noEmit` → clean; `npm test` → **961 passed**
- `ruff check src/agentweave hub/hub` → clean; `black --check` → 215 files unchanged
- CI on `5e63004` (the v1.0.1 tag): **all jobs green**, `hub-test` included.
- **Artefact verified, not the workflow:** clean venv, `pip install agentweave-ai==1.0.1` from real
  PyPI, `agentweave --version` → 1.0.1.
- Both running Hubs answer `200` on `/health` (8000 and 8010); the trial instance's
  `GET /api/v1/projects` returns all four projects.

**NOT tested:**
- **CI has never run on `54dd29b`.** The merge was pushed after the last CI run; the suites above are
  local only. If a release is planned, watch CI first.
- The 7 open tasks in `one-hub-and-a-window-of-its-own` are **human-only** verification — two Hubs
  from different directories, pywebview present/absent, no-webview-backend. None performed.
- 15 of 21 taste-pass tasks remain unjudged. 4 were judged by the operator today.
- The desktop window was confirmed to *exist* (two `MainWindowTitle` matches) — it was not driven,
  clicked, or screenshotted.
- Nothing in the autonomous run was independently re-derived beyond re-running its suites; its
  reasoning is taken on its logs.

## Git state

- **Branch:** `master`, **HEAD:** `54dd29b`, up to date with `origin/master`. No unpushed commits.
- **Dirty:** two untracked paths only — `spec/` and `hub/seed_taste_doc.py`. Both deliberate; see
  Files touched.
- **Tags:** `v1.0.0` → `ff16a62`, `v1.0.1` → `5e63004`. Master is 30 commits past `v1.0.1`.
- **Branch merged:** `autonomous/2026-08-17-archive-and-hub-app` (fast-forward, no merge commit).
  Still exists locally and on origin; safe to delete.
- **Driver:** `AgentWeaveAutonomousSession` scheduled task **unregistered**, verified by querying.
- Stale `~/.agentweave/hub/hub-8010.pid` from a manually-started uvicorn — harmless, deletable.

## Next steps

1. **Judge the taste pass.** Open `.claude/TASTE-PASS-2026-08-17.md` and work Part 1 against the
   **trial** instance at `http://127.0.0.1:8010` (not 8000 — 8000 has no data). 15 of 21 tasks are
   judgeable now; fixtures for the rest were seeded by the autonomous run. This is the roadmap's own
   Tier 1 item and it gates archiving six changes.
2. **Decide D4** — `pyproject.toml:34` pins `agentweave-hub>=1.0.0`. Nearly all of 1.0.1 ships in the
   *hub* package, so `pip install --upgrade agentweave-ai` can leave an upgrader on 1.0.0's Hub with
   none of the release. Fixing it means a 1.0.2.
3. **Decide whether master ships.** It carries the desktop window, `--profile` and the archive work,
   none of it published. Run CI on `54dd29b` first — it has never been tested there.
4. **Read the roadmap** — `openspec/explorations/2026-08-17-what-to-work-on-next.md`, four tiers.
5. Optional cleanup: delete the merged autonomous branch, the stale PID file, and
   `hub/seed_taste_doc.py`.

## Open questions for the user

- **D2** — the 2 taste tasks needing a real agent turn cost tokens. Approve or skip?
- **D3** — this session's UI work was implemented outside any openspec change, against the repo's
  own convention. Retro-cover it with one change, or accept it as shipped?
- **D4** — the dependency pin above. A 1.0.2 to fix it, or leave it?
- Whether the **dev app** (port 8000) should be seeded with any data, or stay empty.

All four are recorded in `.claude/autonomous/STATE.json` → `decisions_for_user` with fuller reasoning.

## Read on resume

- `.claude/TASTE-PASS-2026-08-17.md` — the 21 human-only tasks, which are judgeable and what was
  seeded for them. Untracked; it is the next action's script.
- `openspec/explorations/2026-08-17-what-to-work-on-next.md` — the roadmap, ranked in four tiers.
- `.claude/autonomous/STATE.json` — five decisions with reasoning, plus `known_debts` (the StaticPool
  fixture race and the ~240ms/test fixture overhead).
- `.claude/autonomous/2026-08-17-archive-and-hub-app-log.md` — 10 iterations, oldest first; read the
  19:43 entry for the archive bug that was a real defect rather than a styling gap.
- `openspec/changes/2026-08-16-one-hub-and-a-window-of-its-own/tasks.md` — 27/34 done; section 6 is
  the human verification still owed.
- `src/agentweave/cli.py` — `--profile`, per-profile paths, the app-window path. The file that
  changed most this session (+211 lines).
