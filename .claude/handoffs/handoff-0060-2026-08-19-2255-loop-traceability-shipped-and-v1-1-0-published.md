# Handoff: loop traceability shipped, both changes archived, v1.1.0 published

**Date:** 2026-08-19T22:55:55+01:00 · **Branch:** `master` · **HEAD:** `8c26610`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0059-2026-08-19-1951-both-changes-done-but-two-and-a-loop-marker-queued.md`
**Status:** chunk complete, nothing blocked, nothing in flight. **Working tree clean, nothing
unpushed, no active openspec changes.** One live user-facing question: the operator's own install
of AgentWeave is **not finished** (see Open questions).

## Goal

Finish the three-part loop-traceability plan approved in handoff 0059, close the two human-only
checks, then get everything out as a release. The *why*: a loop firing opens a **new conversation
every time** (task 8.1 refuses `session_mode="resume"` for a loop), so an agent's conversation list
silently fills with threads nobody typed. Measured on the trial Hub: one agent, 20 conversations,
11 of them firings across 5 loops, interleaved by recency with the 9 the operator started.

That is all done. The operator then asked to archive, merge, release, and update the docs — also
done, and `v1.1.0` is live on PyPI and GHCR.

## Current state

**Everything from this session is shipped.** `master` is at `8c26610` with green CI, the working
tree is clean, and there are **no active openspec changes** — `openspec list --json` returns `[]`.

**v1.1.0 is published and independently verified**, not merely reported green by the workflow:

- PyPI `agentweave-ai` **1.1.0** and `agentweave-hub` **1.1.0**
- GHCR `ghcr.io/gutohuida/agentweave-hub` tagged **1.1.0** and **latest**
- GitHub release: https://github.com/gutohuida/AgentWeave/releases/tag/v1.1.0
- Verified by `pip install agentweave-ai==1.1.0` into a clean venv from **real PyPI**: both
  packages resolved to 1.1.0 (confirming the corrected `>=1.1.0` floor), `agentweave --version`
  printed `agentweave 1.1.0`, and the UI bundle was present inside the installed `hub` package.

**Both openspec changes are archived** into `openspec/changes/archive/2026-08-19-*`, with their
deltas synced into `openspec/specs/` first. `openspec validate --specs --strict` → **33 passed**.

**What was built this session** (all four items of the plan, plus two bug fixes found by driving
it):

1. **B9.1/B9.2 — the loop marker.** `ConversationResponse` carries `loop: {id, label} | null`.
2. **B9.3 — the pending-edit indicator** on `LoopTab`, which unblocked A6.1.
3. **B9.4/B9.6 — timestamps** read as the instants they are, app-wide.
4. **B9.5 — grouping** consecutive firings into one expandable row.
5. **The context-fill bug** the operator reported mid-session.

## Files touched

**Working tree is clean and everything is pushed.** 15 commits this session (`6174f68..8c26610`),
**65 files, +4,141 / −796** excluding the committed UI bundle and the archived change directories.
`dist/` holds locally built 1.1.0 wheels and is **gitignored** — not at risk, not tracked.

**Hub (Python):**

- `hub/hub/api/v1/agent_chat.py` — added `ConversationLoop` schema, `loop` and `context_usage`
  fields on `ConversationResponse`, `_loops_by_conversation` (batched `JobRun → AIJob → Loop`,
  inner join), `_context_by_conversation` (batched `context_warning` lookup). **Finished.**
- `hub/hub/context_readings.py` — **new.** `usable_context_reading`, moved out of `agents.py` so
  the agent roster and a conversation share one definition. **Finished.**
- `hub/hub/api/v1/agents.py` — helper removed, re-exported as `_usable_context_reading` so every
  existing call site and test kept working. **Finished.**
- `hub/tests/test_conversation_loop_marker.py` — **new**, 5 tests. **Finished.**
- `hub/tests/test_conversation_context_usage.py` — **new**, 5 tests. **Finished.**

**Hub UI (TypeScript):**

- `hub/ui/src/lib/hubTime.ts` — **new.** `hubDate()`. **Finished.**
- `hub/ui/src/lib/loopGrouping.ts` — **new.** `groupConsecutiveFirings`, `capRows`. **Finished.**
- `hub/ui/src/components/layout/LoopFiringGroup.tsx` — **new.** The collapsed-run row. **Finished.**
- `hub/ui/src/components/layout/ConversationRow.tsx` — loop marker (sibling button, `min-w-0`,
  40% cap), `showLoopMarker` prop. **Finished.**
- `hub/ui/src/components/layout/AgentTree.tsx`, `RecencyView.tsx` — grouping wired in, cap now
  bounds rows. **Finished.**
- `hub/ui/src/components/spec/LoopTab.tsx` — `PendingEdit` panel, `stagedFields`, `hubDate`.
  **Finished.**
- `hub/ui/src/components/agents/ConversationControls.tsx` — takes `contextUsage` as an explicit
  prop; the unused `agent` prop was removed. **Finished.**
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — passes `currentConversation?.context_usage`.
  **Finished.**
- `hub/ui/src/api/{agentChat,jobs,agents}.ts` — `ConversationLoop`, `LoopPendingEdit`,
  `context_usage`, `control`, `pending_edit` types. **Finished.**
- **12 more components** routed through `hubDate`: `activity/EventRow`, `agents/AgentActivityTab`,
  `agents/AgentCard`, `agents/AgentSettingsPage`, `agents/AgentTimeline`, `jobs/JobCard`,
  `logs/LogLine`, `messages/MessageCard`, `overview/OverviewPage`, `quality/QualityHealthPanel`,
  `questions/QuestionInterruptCard`, `questions/QuestionsPanel`, `tasks/TaskCard`,
  `tasks/TaskDetailDrawer`, `api/agents.ts`. **Finished.**
- `hub/ui/src/components/jobs/JobForm.tsx`, `logs/LogsView.tsx` — **deliberately still parse raw**;
  each carries an inline comment saying why. **Finished, do not "fix".**
- **6 UI test files** added/updated: `conversationLoopMarker`, `loopPendingEdit`, `loopGrouping`,
  `loopFiringGroup`, `hubTime`, `conversationControls`. **Finished.**

**Specs and docs:**

- `openspec/specs/conversation-side-panel/spec.md` — **new capability**, 14 requirements.
- `openspec/specs/agent-loops/spec.md` — 5 → **25** requirements.
- `openspec/specs/spec-chat-session/spec.md`, `task-lifecycle-governance/spec.md` — updated.
- `docs/reference/mcp-tools.md` — `create_loop` added.
- `docs/guides/dashboard.md` — side panel and loops documented; deleted subsystems removed.
- `CHANGELOG.md` — `[1.1.0]` entry.
- `pyproject.toml`, `hub/pyproject.toml` — `1.1.0`; CLI floor `agentweave-hub>=1.1.0`.

## Key decisions

1. **The loop join to `Loop` is INNER, deliberately.** A plain scheduled job has the same
   `origin == "job"` and no loop, so it falls out with `null`. *Rejected:* deriving the marker
   from `origin` — it cannot make this distinction and would mislabel every plain job as a loop.
2. **The marker is a sibling button, not a child of the row button.** Nested buttons are invalid
   HTML. It is deliberately **not** `.row-action` (which hides until hover) — that is right for an
   action and wrong for the fact distinguishing a firing from a typed thread.
3. **Marker sizing is `min-w-0` + 40% cap, not `shrink-0` + 96px.** The fixed width truncated real
   titles to `taste…`, losing what the row is *for* to what merely qualifies it.
4. **Grouping is strictly consecutive, never global.** In a list sorted by recency the order *is*
   information. *Rejected:* grouping every firing of a loop wherever it appears — that reorders the
   list. A run of one stays a plain row.
5. **Grouping runs before capping; caps bound rows, "Show N more" counts conversations.** A cap
   could otherwise fall inside a run and split it; but "Show 1 more" hiding five is a lie.
6. **The inline "in force now" hints on the live purpose/stop condition were REMOVED**, on the
   operator's judgement — the panel renders directly above both.
7. **`hubDate` is the consumer-side fix only.** *Rejected for now:* fixing at the Hub's
   serialisation boundary (~100 column declarations, every API response, test assertions would
   move). The two compose — `hubDate` leaves an already-labelled string untouched.
8. **A conversation with no context reading shows nothing**, never falling back to the agent's —
   that fallback *is* the bug. A test pins it.
9. **`agentweave-hub` floor bumped to `>=1.1.0`.** It had been left at `1.0.0` and was not touched
   at 1.0.1, while the release process describes it as tracking the current version.
10. **13.2 was scoped to the mechanism, not the prose**, on the operator's instruction. The 4,000-char
    cap and D5's composition order were **not** judged and stay revisitable.

## Constraints and user directives (verbatim)

> *"I just want to know if the mechanism works. If it works you can consider it done"* — 13.2.

> *"Yes it's clear enough."* — A6.1's verdict.

> *"nothing there is mine. you can kill it and wipe it if you want."* — on the trial Hub fixtures,
> when asked about restarting it.

> *"archive and update the PR. We have a lot of changes should we prepare a release as well? And
> ujpdate the documentation?"* — all four done.

> *"do both"* — explicit authorization to publish v1.1.0 **and** build local wheels.

> *"forget about 4 you misunderstood me"* — staging `job.message` as a pending edit. **Dropped. Do
> not reopen.**

> *"only the endpoint for now is enough"* — A6.3, delegation stays API-only.

Still binding from `CLAUDE.md` and earlier sessions: **"Full auto, but only on green CI."** **Never
point the Hub you are editing at this repo** as an orchestrator. **Use openspec, never the `aw-*`
skills.** **Stage paths explicitly, never `git add -A`.** **Always `py -3.11`.** T3 source in
`testbed/scratch/t3ref/` is **design reference only — study, never copy, never commit.** **Do not
touch `aw-loop10` (`proj-ff695d96`).** **Do not delete `proj-5e960453`** (the browser suite's
fixture). **Never create `.agentweave/`, `agentweave.yml` or `spec/` as new artefacts at the repo
root.** **Never commit `kimichanges.md`/`kimiwork.md`.** **Do not tick human-only tasks** — though
note the operator gave verdicts on both this session and asked that they be recorded.

## Dead ends

- **`DATABASE_URL="sqlite+aiosqlite:///$(pwd)/..."` from Git Bash is WRONG on Windows.** `$(pwd)`
  yields a POSIX path; SQLAlchemy resolved it to `C:\c\Users\...`, so the Hub came up on a brand-new
  empty database and ran all 81 migrations into it. **The real database was untouched** and the
  stray tree was removed. **CLAUDE.md's documented start command has this bug** — it only works
  from a shell where `$(pwd)` yields a Windows path. Restart the trial Hub the way it was
  originally launched instead: bare `uvicorn` from `hub/`, **no** `DATABASE_URL`.
- **The Bash tool takes bash syntax, not PowerShell.** `git commit -m @'...'@` leaked a literal `@`
  into a commit subject. Use `-m` repeated, or a heredoc.
- **Heredoc eats backslashes.** `replace(/\\/g, '/')` became `replace(/\/g, '/')` and broke the
  file. Use the `Edit` tool for strings containing escapes. (Same dead end as handoff 0059.)
- **`node:fs` in a vitest test breaks `npm run build`.** The production build type-checks tests
  against the app tsconfig, which has no node types — and the failing build silently left a **stale
  `dist/`** that then got stamped. Use `import.meta.glob` instead.
- **`openspec status --change <name>` rejects names starting with a digit** ("must start with a
  letter"). `openspec list --json` handles them fine.
- **`openspec validate --strict` wants SHALL/MUST early in a requirement**, not merely somewhere in
  it. Two requirements failed until the modal verb moved into the first sentence.
- **`pip install --no-index` blocks transitive deps.** Use `--find-links` *with* the index.
- **The UI build stamp can be stale while the bundle is correct.** `AW_CHECK_UI_BUNDLE=1` failed on
  master although the assets were byte-identical; only the fingerprint was wrong, which would have
  made `/health` report `ui_stale` on a correct bundle. Re-run `scripts/refresh_ui_bundle.py`
  **from the repo root** (it is not under `hub/ui/`).

## Verification

**Ran and passed:**

- `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` → **2467 passed, 12 skipped,
  1 xpassed** (~12–13 min), run twice.
- `py -3.11 -m pytest tests/ -q` → **397 passed, 3 skipped**.
- `cd hub/ui && npx vitest run` → **1152 passed / 115 files**.
- `npm run lint`, `npx tsc --noEmit`, `py -3.11 -m ruff check hub/ src/ tests/`, `black` → clean.
- `AW_CHECK_UI_BUNDLE=1 py -3.11 -m pytest hub/tests/test_ui_build_stamp.py` → **11 passed**.
- `npx openspec validate --specs --strict` → **33 passed, 0 failed**.
- `py -3.11 -m mkdocs build --strict` → clean.
- **CI green on every push**, on both merge commits, and on the `v1.1.0` tag.
- **Published artefact verified from real PyPI** in a clean venv (see Current state).

**Driven live against the trial Hub (port 8010), not just unit-tested:**

- The loop marker on **271 real conversations**: loop-fired ones named their loop, plain-job ones
  returned `null`, identical `origin`.
- Grouping: runs of 2 and 3 collapsed; the expander went `Show 256 more` → `Show 250 more`, i.e. 15
  rows standing for 21 conversations.
- The pending-edit panel with a real staged edit on `loop-57f2f62c` — captures in
  `testbed/scratch/shots/pending-0{2,3}-loop-tab-*.png` (both themes).
- The context-usage fix on agent `verifier`: **18.56 / 16.6 / 15.9**, each on its own, where all
  three previously showed 15.9.
- 13.2 re-verified **from the database**, not from handoff 0059's quotes: firing 2 (`conv-cb509508`)
  had no `## Prior checkpoint` and the agent said so; firing 3 (`conv-070a6040`) carried
  `ckpt-83a85807` written in **`conv-3aa665d1`** and the agent quoted content existing only there.

**NOT tested / not done:**

- **The browser suite has NOT been run since the merge.** It is opt-in (`AW_HUB_URL`) so CI never
  covers it. Last known: 63 passed, before this session's changes.
- `mypy` not run. Baseline is 361 pre-existing errors in 86 files
  (`.claude/autonomous/mypy-baseline.txt`); the bar is "no NEW errors". CI does not gate on it.
- **A6.1's `firing_active` wording was never read by a human on a live run** — the fixture was
  staged while the loop was idle. Unit-tested only.
- **13.2's proportionality was not judged** — only the mechanism.
- The **13.2 scratch project is half-built**: `proj-d0e4027e` ("13.2 briefing check",
  `testbed/ckpt-13-2`) exists and correctly inherited `checkpoint_mode='offered'`, but has
  `checkpoint_runner_id = NULL`, no agent, and no loop. It was never needed.

## Git state

- **Branch: `master`**, **HEAD `8c26610`**, clean, **0 unpushed**.
- **Tag `v1.1.0` pushed**; GitHub release created; PyPI and GHCR published.
- PRs **#5** (121 commits) and **#6** (release) both **merged**; both branches deleted.
- `dist/` contains locally built 1.1.0 wheels + `RELEASE_NOTES_1.1.0.md`. **Gitignored.**
- Trial Hub **running on port 8010**, serving `hub/data/agentweave.db` (3 projects + the new
  `proj-d0e4027e` = 4). Launched bare, from `hub/`, no `DATABASE_URL`.

## Next steps

There is **no in-flight work.** Pick one:

1. **Finish the operator's own install** (see Open questions — this is the only live thread). Run,
   from a directory that is **not** this repo:
   `py -3.11 -m venv $env:LOCALAPPDATA\AgentWeave\venv`, then
   `& $env:LOCALAPPDATA\AgentWeave\venv\Scripts\pip.exe install agentweave-ai`, then
   `& $env:LOCALAPPDATA\AgentWeave\venv\Scripts\pythonw.exe -m agentweave`.
2. **Run the browser suite** to close the one untested gap:
   `AW_HUB_URL=http://127.0.0.1:8010 AW_HUB_API_KEY=<key from operator_credentials> py -3.11 -m pytest hub/tests/browser -q`.
3. **Propose the serialisation-boundary fix** as a new openspec change — a `TypeDecorator` on the
   datetime columns so a naive datetime never leaves the API.
4. **Propose the `checkpoint_runner_id` default** — "checkpointing on by default" currently only
   defaults the mode, not the runner.

## Open questions for the user

- **The operator's install is unfinished.** `pip install --user agentweave-ai` failed with
  *"Can not perform a '--user' install. User site-packages are not visible in this virtualenv."*
  Diagnosed: their `python`/`pip` on PATH resolve into
  `C:\Users\huida\AppData\Local\hermes\hermes-agent\venv` — an unrelated tool's venv — so a plain
  `pip install` would have polluted it. Real interpreter is `py -3.11`; **no pipx**; user Scripts
  dir (`%APPDATA%\Python\Python311\Scripts`) is **not on PATH**. A dedicated venv was recommended
  (verified: venvs do ship `pythonw.exe`, which the Desktop shortcut needs). **They have not run it
  yet.**
- **Whether to fix timestamps at the serialisation boundary.** Recorded as the better fix.
- **A1.3's routed extension-request path** — whether the Hub should carry an agent's "please add
  this task" request and hand the operator a one-click accept. Open since the message-fix decision.
- **The D15 name-reuse hole** — a new agent taking an archived agent's name inherits its creator
  privilege. A5.3 *records* it deliberately rather than fixing it.
- **Two naming explorations** (`openspec/explorations/2026-08-18-candidate-names.md`,
  `2026-08-18-does-the-name-still-fit.md`) still unresolved, with far more UI now built on the
  current name.

## Read on resume

- `CHANGELOG.md` — the `[1.1.0]` entry is the most compact statement of what shipped.
- `openspec/specs/agent-loops/spec.md` — the loop contract as it now stands, 25 requirements.
- `hub/ui/src/lib/hubTime.ts` — the timestamp rule, its two exemptions, and why the server-side
  fix is still open.
- `hub/ui/src/lib/loopGrouping.ts` — why grouping is consecutive-only and why caps bound rows.
- `hub/hub/api/v1/agent_chat.py` — `_loops_by_conversation` and `_context_by_conversation`, the
  two batched lookups added this session.
- `hub/tests/browser/conftest.py` — how to run the one suite that has not been run since the merge.
